import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import weather


class WeatherTests(unittest.TestCase):
    def setUp(self):
        with weather._CACHE_LOCK:
            weather._CACHE.clear()
        self.today = patch.object(weather, "_today", return_value=date(2026, 10, 10))
        self.today.start()
        self.addCleanup(self.today.stop)
        self.requests = []
        self.request_lock = threading.Lock()

    def fake_api(self, url, *args):
        with self.request_lock:
            self.requests.append(url)
        query = parse_qs(urlsplit(url).query)
        if url.startswith(weather.GEOCODING_API):
            return {"results": [{"name": "Subang Jaya", "country_code": "MY", "admin1": "Selangor", "latitude": 3.04384, "longitude": 101.58062}]}
        if url.startswith(weather.ARCHIVE_API):
            start = date.fromisoformat(query["start_date"][0])
            days = calendar.monthrange(start.year, start.month)[1]
            rain = [0.0, 0.5, 1.0, 2.0, 10.0, 20.0, 25.0, 0.0, 1.0, 30.0][start.year - 2016]
            return {"daily": {"time": [date(start.year, start.month, day).isoformat() for day in range(1, days + 1)],
                              "precipitation_sum": [rain] * days, "temperature_2m_max": [32.0] * days,
                              "temperature_2m_mean": [27.0] * days}}
        if url.startswith(weather.FORECAST_API):
            return {"daily": {"time": ["2026-10-10", "2026-10-25"], "precipitation_probability_max": [70, 40],
                              "precipitation_sum": [12.0, 1.0], "temperature_2m_max": [31.0, 32.0]}}
        raise AssertionError("Unexpected URL: " + url)

    def test_historical_thresholds_samples_and_sources(self):
        events = []
        with patch.object(weather, "_fetch_json", side_effect=self.fake_api):
            result = weather.date_weather("2027-03-17", "Sunway campus, Subang Jaya", lambda *event: events.append(event))
        self.assertTrue(result["available"])
        self.assertEqual(result["mode"], "historical climatology, not a forecast")
        self.assertEqual(result["sampleCount"], 10)
        self.assertEqual(result["years"], list(range(2016, 2026)))
        self.assertEqual(result["rainProbability"], 70.0)
        self.assertEqual(result["rainDays"], 7)
        self.assertEqual(result["heavyRainDays"], 3)
        self.assertEqual(result["avgTempMax"], 32.0)
        self.assertEqual(result["avgTempMean"], 27.0)
        self.assertEqual(len(result["sourceUrls"]), 11)
        self.assertEqual(len(result["samples"]), 10)
        self.assertIn("not a forecast", result["uncertainty"])
        for url in result["sourceUrls"][1:]:
            query = parse_qs(urlsplit(url).query)
            self.assertEqual(query["timezone"], ["Asia/Kuala_Lumpur"])
            self.assertTrue(query["start_date"][0].endswith("03-01"))
            self.assertTrue(query["end_date"][0].endswith("03-31"))
        self.assertTrue(events)

    def test_concurrent_date_scout_does_only_ten_archive_requests(self):
        def slow_api(url, *args):
            time.sleep(0.005)
            return self.fake_api(url)
        with patch.object(weather, "_fetch_json", side_effect=slow_api):
            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(lambda day: weather.date_weather(f"2027-03-{day:02d}", "Sunway, Subang Jaya"), [5, 10, 15, 20, 25]))
        self.assertTrue(all(result["available"] for result in results))
        self.assertEqual(sum(url.startswith(weather.GEOCODING_API) for url in self.requests), 1)
        self.assertEqual(sum(url.startswith(weather.ARCHIVE_API) for url in self.requests), 10)

    def test_non_subang_location_never_substitutes_city_weather(self):
        for location in ("Kuala Lumpur", "Penang", "Sunway", ""):
            with self.subTest(location=location):
                with patch.object(weather, "_fetch_json") as fetch:
                    result = weather.date_weather("2027-03-17", location)
                self.assertFalse(result["available"])
                self.assertEqual(result["sourceUrls"], [])
                self.assertIsNone(result["rainProbability"])
                fetch.assert_not_called()

    def test_network_trace_matches_actual_calls_and_cache_hits(self):
        from io import BytesIO
        events = []
        def transport(request, timeout):
            return BytesIO(json.dumps(self.fake_api(request.full_url)).encode())
        with patch.object(weather, "urlopen", side_effect=transport) as opened:
            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(lambda day: weather.date_weather(f"2027-03-{day:02d}", "Subang Jaya", lambda *e: events.append(e)), [5, 10, 15, 20, 25]))
        self.assertTrue(all(result["available"] for result in results))
        calls = [event for event in events if event[1] == "running" and event[4].get("networkRequest")]
        self.assertEqual(opened.call_count, 11)
        self.assertEqual(len(calls), opened.call_count)
        self.assertEqual(sum(event[2] == "Open-Meteo archive" for event in calls), 10)
        self.assertEqual(sum(event[1] == "cached" for event in events), 8)
        self.assertTrue(all("url" in event[4] for event in calls))

    def test_forecast_and_holiday_trace_cache_does_not_overcount(self):
        from io import BytesIO
        events = []
        def transport(request, timeout):
            if request.full_url.startswith(weather.HOLIDAY_API):
                response = BytesIO(b"")
                response.status = 204
                return response
            return BytesIO(json.dumps(self.fake_api(request.full_url)).encode())
        with patch.object(weather, "urlopen", side_effect=transport) as opened, patch.object(weather, "_research", return_value={}):
            emit = lambda *e: events.append(e)
            weather.date_weather("2026-10-10", "Subang Jaya", emit)
            weather.date_weather("2026-10-25", "Subang Jaya", emit)
            weather.calendar_context(2027, 3, emit)
            result = weather.calendar_context(2027, 3, emit)
        calls = [event for event in events if event[1] == "running" and event[4].get("networkRequest")]
        self.assertEqual(opened.call_count, 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sum(event[1] == "cached" for event in events), 3)
        self.assertIn("204", " ".join(result["warnings"]))

    def test_forecast_boundary_no_inferred_heavy_count_or_mean(self):
        with patch.object(weather, "_fetch_json", side_effect=self.fake_api):
            result = weather.date_weather("2026-10-25", "Sunway, Subang Jaya")
            beyond = weather.date_weather("2026-10-26", "Sunway, Subang Jaya")
        self.assertEqual(result["mode"], "forecast")
        self.assertEqual(result["rainProbability"], 40)
        self.assertEqual(result["sampleCount"], 1)
        self.assertIsNone(result["heavyRainDays"])
        self.assertIsNone(result["avgTempMean"])
        self.assertEqual(beyond["mode"], "historical climatology, not a forecast")
        forecast = next(url for url in self.requests if url.startswith(weather.FORECAST_API))
        self.assertEqual(parse_qs(urlsplit(forecast).query)["forecast_days"], ["16"])

    def test_forecast_missing_date_is_unavailable(self):
        with patch.object(weather, "_fetch_json", side_effect=self.fake_api):
            result = weather.date_weather("2026-10-12", "Sunway, Subang Jaya")
        self.assertFalse(result["available"])
        self.assertEqual(result["sampleCount"], 0)
        self.assertIsNone(result["rainProbability"])
        self.assertIn("no sample manufactured", " ".join(result["warnings"]))

    def test_missing_forecast_metric_stays_null(self):
        def missing(url, *args):
            result = self.fake_api(url)
            if url.startswith(weather.FORECAST_API):
                result["daily"]["precipitation_probability_max"] = [None, None]
            return result
        with patch.object(weather, "_fetch_json", side_effect=missing):
            result = weather.date_weather("2026-10-10", "Sunway, Subang Jaya")
        self.assertTrue(result["available"])
        self.assertIsNone(result["rainProbability"])
        self.assertIn("remain null", " ".join(result["warnings"]))

    def test_failed_archive_does_not_manufacture_partial_statistics(self):
        def failed(url, *args):
            if url.startswith(weather.ARCHIVE_API) and "2019" in url:
                raise weather.WeatherSourceError("HTTP 429; not retried")
            return self.fake_api(url)
        with patch.object(weather, "_fetch_json", side_effect=failed):
            result = weather.date_weather("2027-03-17", "Sunway, Subang Jaya")
        self.assertFalse(result["available"])
        self.assertIsNone(result["rainProbability"])
        self.assertIsNone(result["heavyRainDays"])
        self.assertEqual(result["sampleCount"], 0)
        self.assertEqual(len(result["sourceUrls"]), 11)
        self.assertIn("429", " ".join(result["warnings"]))

    def test_missing_observation_excluded_and_denominator_reported(self):
        def missing(url, *args):
            result = self.fake_api(url)
            if url.startswith(weather.ARCHIVE_API) and "2016" in url:
                result["daily"]["precipitation_sum"] = [None] * 31
            return result
        with patch.object(weather, "_fetch_json", side_effect=missing):
            result = weather.date_weather("2027-03-17", "Sunway, Subang Jaya")
        self.assertEqual(result["sampleCount"], 9)
        self.assertEqual(result["rainProbability"], 77.8)
        self.assertNotIn(2016, result["sampleYears"])
        self.assertIn("9/10", " ".join(result["warnings"]))

    def test_leap_day_samples_are_not_filled(self):
        with patch.object(weather, "_fetch_json", side_effect=self.fake_api):
            result = weather.date_weather("2028-02-29", "Sunway, Subang Jaya")
        self.assertEqual(result["sampleCount"], 3)
        self.assertEqual(result["sampleYears"], [2016, 2020, 2024])

    def test_empty_geocoder_has_no_unsourced_coordinate_fallback(self):
        with patch.object(weather, "_fetch_json", return_value={"results": []}) as fetch:
            result = weather.date_weather("2027-03-17", "Sunway, Subang Jaya")
        self.assertFalse(result["available"])
        self.assertEqual(fetch.call_count, 1)
        self.assertNotIn("resolvedLocation", result)
        self.assertEqual(len(result["sourceUrls"]), 1)

    def test_malformed_geocoder_or_forecast_is_unavailable(self):
        with patch.object(weather, "_fetch_json", return_value={"results": None}):
            result = weather.date_weather("2027-03-17", "Sunway, Subang Jaya")
        self.assertFalse(result["available"])
        with weather._CACHE_LOCK:
            weather._CACHE.clear()
        def malformed(url, *args):
            if url.startswith(weather.FORECAST_API):
                return {"daily": None}
            return self.fake_api(url)
        with patch.object(weather, "_fetch_json", side_effect=malformed):
            result = weather.date_weather("2026-10-10", "Sunway, Subang Jaya")
        self.assertFalse(result["available"])
        self.assertIn("malformed", " ".join(result["warnings"]))

    def test_invalid_date_does_not_fetch(self):
        with patch.object(weather, "_fetch_json") as fetch:
            result = weather.date_weather("2027-02-30", "Sunway, Subang Jaya")
        self.assertFalse(result["available"])
        fetch.assert_not_called()

    def test_transport_retry_once(self):
        with patch.object(weather, "urlopen", side_effect=URLError("connection reset")) as opened:
            with self.assertRaises(weather.WeatherSourceError):
                weather._fetch_json("https://example.test/data")
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(opened.call_args.kwargs["timeout"], 12)

    def test_quota_and_other_http_errors_never_retried(self):
        for status in (404, 429, 503):
            with self.subTest(status=status):
                error = HTTPError("https://example.test/data", status, "failure", {}, None)
                with patch.object(weather, "urlopen", side_effect=error) as opened:
                    with self.assertRaises(weather.WeatherSourceError):
                        weather._fetch_json("https://example.test/data")
                self.assertEqual(opened.call_count, 1)

    def test_empty_api_body_unavailable(self):
        from io import BytesIO
        with patch.object(weather, "urlopen", return_value=BytesIO(b"")) as opened:
            with self.assertRaises(weather.WeatherSourceError):
                weather._fetch_json("https://example.test/data")
        self.assertEqual(opened.call_count, 1)

    def test_holidays_filter_selangor_and_preserve_unknown_exams(self):
        holidays = [
            {"date": "2027-03-10", "name": "Hari Raya Aidilfitri", "global": True, "counties": None},
            {"date": "2027-03-11", "name": "Other-state only", "global": False, "counties": ["MY-01"]},
            {"date": "2027-03-12", "name": "Selangor holiday", "global": False, "counties": ["MY-10"]},
            {"date": "2027-04-01", "name": "Different month", "global": True},
        ]
        with patch.object(weather, "_fetch_json", return_value=holidays), patch.object(weather, "_research", return_value={}):
            result = weather.calendar_context(2027, 3)
        self.assertEqual(len(result["holidays"]), 2)
        self.assertEqual(len(result["religiousConflicts"]), 1)
        self.assertEqual(result["examCalendar"], "unknown, campus confirmation needed")
        self.assertFalse(result["holidays"][0]["provisional"])

    def test_cited_research_fallback_and_ramadan_range(self):
        research = {"holidays": [
            {"date": "2027-03-10", "name": "Hari Raya Aidilfitri", "source": "https://example.test/calendar", "provisional": True, "global": True},
            {"date": "2027-03-11", "name": "Uncited entry"},
            {"date": "2027-03-12", "name": "Other-state only", "source": "https://example.test/calendar", "counties": ["MY-01"]}],
            "ramadanRanges": [{"start": "2027-02-08", "end": "2027-03-09", "source": "https://example.test/ramadan", "provisional": True}]}
        with patch.object(weather, "_fetch_json", side_effect=weather.WeatherSourceError("HTTP 204 empty response")), patch.object(weather, "_research", return_value=research):
            result = weather.calendar_context(2027, 3)
        self.assertEqual(len(result["holidays"]), 1)
        self.assertTrue(result["holidays"][0]["provisional"])
        self.assertEqual(len(result["ramadanRanges"]), 1)
        self.assertIn("204", " ".join(result["warnings"]))
        self.assertIn("https://example.test/ramadan", result["sourceUrls"])

    def test_research_jurisdiction_and_inferred_ramadan_note_preserved(self):
        research = {"holidays": [
            {"date": "2027-03-10", "name": "Hari Raya Aidilfitri", "source": "https://example.test/calendar", "jurisdiction": "Selangor", "provisional": True},
            {"date": "2027-03-12", "name": "Other state", "source": "https://example.test/calendar", "jurisdiction": "Johor"}],
            "ramadanRanges": [{"start": "2027-03-01", "end": "2027-03-09", "source": "https://example.test/ramadan", "provisional": True,
                               "notes": "Inferred provisional planning window; not a verified complete calendar."}]}
        with patch.object(weather, "_fetch_json", return_value=[]), patch.object(weather, "_research", return_value=research):
            result = weather.calendar_context(2027, 3)
        self.assertEqual(len(result["holidays"]), 1)
        self.assertTrue(result["holidays"][0]["provisional"])
        self.assertIn("Inferred", result["ramadanRanges"][0]["sourceNote"])
        self.assertIn("not a verified", " ".join(result["warnings"]))
        self.assertNotIn("applicability not supplied", " ".join(result["warnings"]))

    def test_unknown_calendar_is_not_marked_holiday_free(self):
        with patch.object(weather, "_fetch_json", return_value=[]), patch.object(weather, "_research", return_value={}):
            result = weather.calendar_context(2027, 3)
        self.assertEqual(result["holidays"], [])
        self.assertEqual(result["ramadanRanges"], [])
        self.assertIn("does not establish", " ".join(result["warnings"]))
        self.assertIn("unknown", result["examCalendar"])


@unittest.skipUnless(os.environ.get("EVENTPILOT_LIVE_WEATHER") == "1", "Optional real-network evidence; set EVENTPILOT_LIVE_WEATHER=1")
class WeatherLiveTests(unittest.TestCase):
    def test_real_march_2027_archive(self):
        with weather._CACHE_LOCK:
            weather._CACHE.clear()
        result = weather.date_weather("2027-03-17", "Sunway University, Subang Jaya")
        print("LIVE_WEATHER_EVIDENCE " + json.dumps(result, sort_keys=True))
        self.assertTrue(result["available"], result["warnings"])
        self.assertEqual(result["sampleCount"], 10)
        self.assertEqual(result["mode"], "historical climatology, not a forecast")
        self.assertTrue(all("open-meteo.com" in url for url in result["sourceUrls"]))


if __name__ == "__main__":
    unittest.main()
