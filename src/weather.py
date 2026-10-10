"""Sourced city-grid weather and provisional event-calendar context."""

import calendar
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date as Date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GEOCODING_API = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_API = "https://archive-api.open-meteo.com/v1/archive"
HOLIDAY_API = "https://date.nager.at/api/v3/PublicHolidays"
RESEARCH_PATH = Path(__file__).resolve().parents[1] / "data" / "research.json"
RAIN_MM = 1.0
HEAVY_RAIN_MM = 20.0
_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()
_NETWORK_LIMIT = threading.BoundedSemaphore(4)
_CACHE_LIMIT = 256


class WeatherSourceError(Exception):
    pass


def _today():
    return datetime.now(timezone(timedelta(hours=8))).date()


def _emit(emit, status, tool, message, data=None):
    if emit:
        emit("Weather & Logistics", status, tool, message, data)


def _url(endpoint, **params):
    return endpoint + "?" + urlencode(params)


def _fetch_json(url, emit=None, tool="HTTP JSON"):
    """Retry transport failures once; never retry HTTP/quota failures."""
    for attempt in range(2):
        try:
            request = Request(url, headers={"User-Agent": "EventPilot/1.0", "Accept": "application/json"})
            with _NETWORK_LIMIT:
                _emit(emit, "running", tool, "Send actual source API request", {"url": url, "attempt": attempt + 1, "networkRequest": True})
                with urlopen(request, timeout=12) as response:
                    status = getattr(response, "status", None)
                    content = response.read()
            if not content:
                prefix = f"HTTP {status}: " if status else ""
                raise WeatherSourceError(prefix + "API returned an empty response (possibly unsupported country)")
            payload = json.loads(content)
            if isinstance(payload, dict) and payload.get("error"):
                raise WeatherSourceError(str(payload.get("reason", "API reported an error")))
            _emit(emit, "completed", tool, "Source API response received", {"url": url, "httpStatus": status})
            return payload
        except HTTPError as exc:
            _emit(emit, "warning", tool, f"HTTP {exc.code}; not retried", {"url": url, "httpStatus": exc.code})
            raise WeatherSourceError(f"HTTP {exc.code}; not retried") from exc
        except (URLError, TimeoutError, OSError) as exc:
            _emit(emit, "warning", tool, "Transport failed; retry once" if not attempt else "Transport failed after retry", {"url": url, "attempt": attempt + 1})
            if attempt:
                raise WeatherSourceError(f"Network request failed after one retry: {exc}") from exc
        except (ValueError, UnicodeError) as exc:
            _emit(emit, "warning", tool, "Invalid source JSON", {"url": url})
            raise WeatherSourceError(f"Invalid API JSON: {exc}") from exc
        except WeatherSourceError as exc:
            _emit(emit, "warning", tool, str(exc), {"url": url})
            raise


def _cached(key, ttl, loader, emit=None, tool="Source cache", data=None):
    """A shared Future coalesces concurrent requests, including failures."""
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry and entry[0] > time.monotonic():
            _CACHE.move_to_end(key)
            future, owner = entry[1], False
        else:
            future, owner = Future(), True
            _CACHE[key] = (time.monotonic() + ttl, future)
            for old_key in list(_CACHE):
                if len(_CACHE) <= _CACHE_LIMIT:
                    break
                if _CACHE[old_key][1].done():
                    del _CACHE[old_key]
    if not owner:
        _emit(emit, "cached", tool, "Reuse cached source data" if future.done() else "Share in-flight source request", data)
    if owner:
        try:
            future.set_result(loader())
        except Exception as exc:
            with _CACHE_LOCK:
                _CACHE[key] = (time.monotonic() + 60, future)
            future.set_exception(exc)
    return future.result()


def _number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _daily_value(daily, field, index):
    values = daily.get(field, [])
    if not isinstance(values, list) or index >= len(values):
        return None
    value = values[index]
    return value if _number(value) else None


def _geocode(emit):
    # The campus is in Subang Jaya; no unsourced campus coordinates are used.
    url = _url(GEOCODING_API, name="Subang Jaya", count=5, language="en", format="json", countryCode="MY")
    def load():
        payload = _fetch_json(url, emit, "Open-Meteo geocoding")
        if not isinstance(payload, dict):
            raise WeatherSourceError("Invalid geocoder response")
        rows = payload.get("results")
        if not isinstance(rows, list):
            raise WeatherSourceError("Geocoder results are missing or malformed")
        candidates = [r for r in rows if isinstance(r, dict) and r.get("country_code") == "MY" and str(r.get("name", "")).casefold() == "subang jaya"]
        if not candidates:
            raise WeatherSourceError("No verified Subang Jaya geocoding result; no coordinate fallback")
        result = candidates[0]
        if not _number(result.get("latitude")) or not _number(result.get("longitude")):
            raise WeatherSourceError("Geocoding coordinates are missing")
        return result

    return _cached(("geocode", "Subang Jaya"), 86400, load, emit, "Open-Meteo geocoding", {"url": url}), url


def _history(location, month, years, emit):
    urls = [_url(ARCHIVE_API, latitude=location["latitude"], longitude=location["longitude"],
                 start_date=f"{year}-{month:02d}-01", end_date=f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}",
                 daily="precipitation_sum,temperature_2m_max,temperature_2m_mean", timezone="Asia/Kuala_Lumpur")
            for year in years]
    key = ("history", location["latitude"], location["longitude"], month, tuple(years))
    def load():
        def year_data(item):
            year, url = item
            try:
                payload = _fetch_json(url, emit, "Open-Meteo archive")
                if not isinstance(payload, dict) or not isinstance(payload.get("daily"), dict):
                    raise WeatherSourceError("Missing archive daily data")
                if not isinstance(payload["daily"].get("time"), list):
                    raise WeatherSourceError("Archive dates are missing or malformed")
                return year, payload["daily"], None
            except WeatherSourceError as exc:
                return year, None, f"{year}: {exc}"
        with ThreadPoolExecutor(max_workers=4) as executor:
            return list(executor.map(year_data, zip(years, urls)))

    records = _cached(key, 86400, load, emit, "Open-Meteo archive", {"urls": urls, "years": years})
    if any(error for _, _, error in records):
        # Keep successful data briefly, but do not hide a failed historical year.
        with _CACHE_LOCK:
            entry = _CACHE.get(key)
            if entry:
                expiry, future = entry
                _CACHE[key] = (min(expiry, time.monotonic() + 60), future)
    return records, urls


def _base_weather(date, location):
    return {
        "date": date, "location": location, "available": False, "mode": "unavailable",
        "rainProbability": None, "rainProbabilityKind": None, "rainDays": None,
        "heavyRainDays": None, "precipitationMm": None, "avgTempMax": None, "avgTempMean": None,
        "sampleCount": 0, "years": [], "sampleYears": [], "samples": [], "sourceUrls": [], "warnings": [],
        "uncertainty": None,
        "assumptions": {"rainDayThresholdMm": RAIN_MM, "heavyRainThresholdMm": HEAVY_RAIN_MM,
                        "heavyRainDefinition": "Planning assumption: daily precipitation >=20 mm, not an official warning classification"},
    }


def date_weather(date, location, emit=None):
    """Forecast within 0..15 days; otherwise same-day, ten-year climatology.

    rainProbability is a percentage. Historical years are complete calendar
    years before today, not fabricated observations for the target event year.
    """
    result = _base_weather(date, location)
    try:
        target = Date.fromisoformat(date)
        if not isinstance(location, str) or not location.strip():
            raise ValueError("A location label is required")
        if "subang jaya" not in location.casefold():
            raise ValueError("Unsupported location: weather currently supports only explicitly identified Subang Jaya locations; no city data substituted for another location")
        today = _today()
        delta = (target - today).days
        geocode_url = _url(GEOCODING_API, name="Subang Jaya", count=5, language="en", format="json", countryCode="MY")
        result["sourceUrls"].append(geocode_url)
        city, _ = _geocode(emit)
        result["resolvedLocation"] = {"name": city["name"], "region": city.get("admin1"),
                                      "latitude": city["latitude"], "longitude": city["longitude"],
                                      "source": geocode_url, "scope": "Subang Jaya city-grid proxy; not campus coordinates"}
        result["warnings"].append("Weather represents the sourced Subang Jaya city grid, not a campus microclimate.")
        if 0 <= delta <= 15:
            url = _url(FORECAST_API, latitude=city["latitude"], longitude=city["longitude"],
                       daily="precipitation_probability_max,precipitation_sum,temperature_2m_max",
                       timezone="Asia/Kuala_Lumpur", forecast_days=16)
            result["sourceUrls"].append(url)
            payload = _cached(("forecast", city["latitude"], city["longitude"], today.isoformat()), 600,
                              lambda: _fetch_json(url, emit, "Open-Meteo forecast"), emit, "Open-Meteo forecast", {"url": url})
            daily = payload.get("daily") if isinstance(payload, dict) else None
            if not isinstance(daily, dict) or not isinstance(daily.get("time"), list):
                raise WeatherSourceError("Forecast daily data or dates are malformed")
            times = daily["time"]
            if date not in times:
                raise WeatherSourceError("Target date is absent from the returned forecast; no sample manufactured")
            index = times.index(date)
            probability = _daily_value(daily, "precipitation_probability_max", index)
            precipitation = _daily_value(daily, "precipitation_sum", index)
            maximum = _daily_value(daily, "temperature_2m_max", index)
            if probability is None and precipitation is None and maximum is None:
                raise WeatherSourceError("Forecast returned no numeric metrics for the target date")
            if probability is not None and not 0 <= probability <= 100:
                raise WeatherSourceError("Forecast precipitation probability is outside 0..100")
            result.update(available=True, mode="forecast", rainProbability=probability,
                          rainProbabilityKind="forecast daily maximum precipitation probability (%)",
                          precipitationMm=precipitation, avgTempMax=maximum, sampleCount=1,
                          uncertainty="Model forecast; confidence decreases with lead time. No historical heavy-rain count or mean temperature is inferred.")
            result["samples"] = [{"date": date, "precipitationMm": precipitation, "tempMaxC": maximum, "rainProbability": probability}]
            if probability is None or precipitation is None or maximum is None:
                result["warnings"].append("Some requested forecast metrics are missing; absent values remain null.")
        else:
            years = list(range(today.year - 10, today.year))
            result["years"] = years
            records, urls = _history(city, target.month, years, emit)
            result["sourceUrls"].extend(urls)
            errors = [error for _, _, error in records if error]
            if errors:
                raise WeatherSourceError("Archive requests failed; weather metrics unavailable: " + "; ".join(errors))
            samples = []
            for year, daily, _ in records:
                try:
                    observed = target.replace(year=year).isoformat()
                except ValueError:
                    continue  # February 29 has no observation in non-leap years.
                times = daily.get("time", [])
                if observed not in times:
                    continue
                index = times.index(observed)
                rain = _daily_value(daily, "precipitation_sum", index)
                maximum = _daily_value(daily, "temperature_2m_max", index)
                mean = _daily_value(daily, "temperature_2m_mean", index)
                if rain is not None and rain >= 0 and maximum is not None and mean is not None:
                    samples.append({"date": observed, "precipitationMm": rain, "tempMaxC": maximum, "tempMeanC": mean})
            if not samples:
                raise WeatherSourceError("No complete observed samples for this calendar day")
            count = len(samples)
            rainy = sum(s["precipitationMm"] >= RAIN_MM for s in samples)
            result.update(available=True, mode="historical climatology, not a forecast",
                          rainProbability=round(100 * rainy / count, 1),
                          rainProbabilityKind="historical same-calendar-day rainy frequency (%), not forecast probability",
                          rainDays=rainy, heavyRainDays=sum(s["precipitationMm"] >= HEAVY_RAIN_MM for s in samples),
                          precipitationMm=round(sum(s["precipitationMm"] for s in samples) / count, 2),
                          avgTempMax=round(sum(s["tempMaxC"] for s in samples) / count, 2),
                          avgTempMean=round(sum(s["tempMeanC"] for s in samples) / count, 2),
                          sampleCount=count, sampleYears=[Date.fromisoformat(s["date"]).year for s in samples], samples=samples,
                          uncertainty=f"Only {count} same-calendar-day samples from ten complete years; coarse reanalysis grid, not campus measurements. Frequency is not a forecast for the event date.")
            if count < 10:
                result["warnings"].append(f"Only {count}/10 complete samples available; missing/non-leap days excluded, never filled.")
        _emit(emit, "completed", "Weather calculation", result["mode"], {"date": date, "sampleCount": result["sampleCount"], "available": True})
    except (WeatherSourceError, ValueError, TypeError) as exc:
        result["warnings"].append(str(exc))
        result["uncertainty"] = "Weather unavailable; do not use missing data as evidence of dry or safe conditions."
        _emit(emit, "warning", "Weather sources", str(exc), {"date": date, "available": False, "sourceUrls": result["sourceUrls"]})
    return result


def _research():
    try:
        data = json.loads(RESEARCH_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _selangor(item):
    if item.get("global") is True:
        return True
    jurisdiction = item.get("jurisdiction")
    if jurisdiction and str(jurisdiction).casefold() not in {"selangor", "malaysia", "national", "global"}:
        return False
    counties = item.get("counties")
    if not counties:
        return True
    if isinstance(counties, str):
        counties = [counties]
    return any(str(county).casefold().replace(" ", "") in {"my-10", "my10", "10", "selangor"} for county in counties)


def calendar_context(year, month, emit=None):
    """Cited Selangor holidays/fasting windows; campus exams remain unknown."""
    year, month = int(year), int(month)
    Date(year, month, 1)
    result = {"year": year, "month": month, "holidays": [], "ramadanRanges": [],
              "ramadanStatus": "unknown; verify published local dates", "religiousConflicts": [],
              "examCalendar": "unknown, campus confirmation needed", "warnings": [], "sourceUrls": []}
    research = _research()
    url = f"{HOLIDAY_API}/{year}/MY"
    result["sourceUrls"].append(url)
    try:
        holidays = _cached(("holidays", year), 21600, lambda: _fetch_json(url, emit, "Nager.Date holidays"),
                           emit, "Nager.Date holidays", {"url": url})
        if not isinstance(holidays, list) or not holidays:
            raise WeatherSourceError("No supported Malaysian holiday data returned")
        holiday_source = url
    except WeatherSourceError as exc:
        result["warnings"].append(f"Nager.Date unavailable: {exc}. Only cited research fallback entries are used.")
        holidays = research.get("holidays", [])
        holiday_source = None
    if not isinstance(holidays, list):
        holidays = []
    for item in holidays:
        if not isinstance(item, dict) or not _selangor(item):
            continue
        try:
            holiday = Date.fromisoformat(item.get("date", ""))
        except (TypeError, ValueError):
            continue
        if (holiday.year, holiday.month) != (year, month):
            continue
        source = item.get("source") or holiday_source
        name = item.get("name") or item.get("localName")
        if not source or not name:
            continue
        unknown_scope = not item.get("global") and not item.get("counties") and not item.get("jurisdiction")
        entry = {"date": holiday.isoformat(), "name": name, "source": source,
                 "provisional": bool(item.get("provisional", True if not holiday_source else False)) or unknown_scope}
        result["holidays"].append(entry)
        result["sourceUrls"].append(source)
        if unknown_scope:
            result["warnings"].append(f"Selangor applicability not supplied for {name}; confirm before booking.")
        if any(term in name.casefold() for term in ("fitri", "adha", "thaipusam", "wesak", "deepavali", "christmas", "prophet", "maulidur", "nuzul", "ramadan")):
            result["religiousConflicts"].append({"date": holiday.isoformat(), "name": name, "source": source,
                                               "provisional": entry["provisional"], "note": "Religious observance may affect availability; confirm locally."})
    result["holidays"].sort(key=lambda item: item["date"])
    ranges = research.get("ramadanRanges", [])
    if isinstance(ranges, list):
        first = Date(year, month, 1)
        last = Date(year, month, calendar.monthrange(year, month)[1])
        for item in ranges:
            if not isinstance(item, dict) or not item.get("source"):
                continue
            try:
                start, end = Date.fromisoformat(item.get("start", "")), Date.fromisoformat(item.get("end", ""))
            except (TypeError, ValueError):
                continue
            if start <= last and end >= first and start <= end:
                source_note = str(item.get("notes") or item.get("note") or "")
                result["ramadanRanges"].append({"start": start.isoformat(), "end": end.isoformat(), "source": item["source"],
                                                "provisional": bool(item.get("provisional", True)),
                                                "sourceNote": source_note,
                                                "note": "Fasting-period logistics: avoid daytime food-centered programming; local dates require confirmation."})
                if source_note:
                    result["warnings"].append("Ramadan source caveat: " + source_note)
                result["sourceUrls"].append(item["source"])
        if result["ramadanRanges"]:
            result["ramadanStatus"] = "sourced provisional dates; local confirmation required"
    if not result["holidays"]:
        result["warnings"].append("No verified holidays supplied for this month; this does not establish that the month is holiday-free.")
    if not result["ramadanRanges"]:
        result["warnings"].append("No sourced Ramadan range supplied for this month; religious-calendar constraints remain unverified.")
    result["warnings"].append("Campus examination and blackout dates are unknown, campus confirmation needed; school calendars do not establish university exam dates.")
    result["sourceUrls"] = list(dict.fromkeys(result["sourceUrls"]))
    _emit(emit, "completed", "Calendar context", "Return cited holidays with explicit campus-calendar uncertainty", {"holidays": len(result["holidays"]), "examCalendar": result["examCalendar"]})
    return result
