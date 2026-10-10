import copy
from datetime import date
import json
import threading
import unittest
from unittest.mock import patch

from src import pipeline


RESEARCH = {
    "sponsors": [
        {"name": f"Verified Test Prospect {i}", "url": f"https://example.org/sponsor/{i}", "email": f"partnership{i}@example.org" if i != 5 else None, "emailSource": f"https://example.org/contact/{i}" if i != 5 else None, "contactType": "Test fixture official contact", "category": "Test fixture", "fit": "Hypothetical fit assessment"}
        for i in range(1, 7)
    ],
    "campus": {"venues": [{"name": "Test Indoor Hall", "source": "https://example.org/venue", "capacity": None, "notes": "Test fixture only", "indoor": True}], "calendarSources": []},
    "holidays": [],
}


def weather(day, location, emit=None):
    return {"date": day, "probability": .65, "mode": "historical-climatology", "confidence": "low", "sources": ["https://example.org/weather"], "forecastAvailable": False}


def context(year, month, emit=None):
    return {"holidays": [], "examStatus": "unknown", "sources": []}


class PinnedClockTest(unittest.TestCase):
    def setUp(self):
        clock = patch.object(pipeline, "_today", return_value=date(2026, 10, 10))
        clock.start()
        self.addCleanup(clock.stop)


class GoalTests(PinnedClockTest):
    def test_next_march_and_defaults_are_explicit(self):
        goal, assumptions = pipeline.parse_goal("Plan a charity concert in March with RM5,000 for animal welfare.")
        self.assertEqual((goal["month"], goal["year"]), (3, 2027))
        self.assertEqual(goal["dateStart"], "2027-03-01")
        self.assertEqual(goal["dateEnd"], "2027-03-31")
        self.assertEqual(goal["attendance"], 100)
        self.assertTrue(goal["attendanceAssumed"])
        self.assertTrue(any(item["field"] == "attendance" and item["explicit"] and item["editable"] for item in assumptions))
        self.assertEqual(goal["budgetCents"], 500000)
        self.assertEqual(goal["organiserFundsRM"], 3500)

    def test_overrides_recompute_dates_and_money(self):
        goal, assumptions = pipeline.parse_goal("Concert in March with RM5k", {"month": 4, "year": 2028, "attendance": 180, "budgetRM": "3333.33", "organiserFundsRM": "2000"})
        self.assertEqual(goal["dateStart"], "2028-04-01")
        self.assertEqual(goal["dateEnd"], "2028-04-30")
        self.assertEqual(goal["budgetCents"], 333333)
        self.assertFalse(goal["attendanceAssumed"])
        self.assertTrue(any(item.get("overridden") for item in assumptions))

    def test_parses_prompt_date_range_and_next_month_override(self):
        goal, assumptions = pipeline.parse_goal("Concert between 2027-04-03 and 2027-04-18 with RM5000")
        self.assertEqual((goal["dateStart"], goal["dateEnd"]), ("2027-04-03", "2027-04-18"))
        self.assertEqual((goal["month"], goal["year"]), (4, 2027))
        self.assertFalse(any(item["field"] in ("month", "year") for item in assumptions))
        goal, _ = pipeline.parse_goal("Concert in March", {"month": 12})
        self.assertEqual((goal["month"], goal["year"]), (12, 2026))

    def test_dynamic_clock_and_goal_snapshot(self):
        with patch.object(pipeline, "_today", return_value=date(2030, 4, 15)):
            goal, assumptions = pipeline.parse_goal("Workshop in March with RM5000")
        self.assertEqual(goal["scenarioDate"], "2030-04-15")
        self.assertEqual(goal["year"], 2031)
        self.assertTrue(any("2030-04-15" in item["reason"] for item in assumptions))
        with patch.object(pipeline, "_today", return_value=date(2035, 1, 1)), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=context):
            dates = pipeline.scout_dates(goal, RESEARCH, pipeline.Trace(None))
        self.assertEqual(len(dates["candidates"]), 5)
        self.assertTrue(all(item["date"].startswith("2031") for item in dates["candidates"]))

    def test_parses_explicit_campus_and_location(self):
        goal, _ = pipeline.parse_goal("Concert in March at Example Campus in Kuala Lumpur with RM5000")
        self.assertEqual(goal["campus"], "Example Campus")
        self.assertEqual(goal["location"], "Kuala Lumpur")

    def test_weather_percentage_normalization_includes_one_percent(self):
        self.assertEqual(pipeline._probability({"rainProbability": 1, "rainProbabilityKind": "rainy frequency (%)"}), .01)
        self.assertEqual(pipeline._probability({"rainProbability": 1}), .01)
        self.assertEqual(pipeline._probability({"rainProbability": 65, "rainProbabilityKind": "rainy frequency (%)"}), .65)
        self.assertEqual(pipeline._probability({"probability": .65}), .65)

    def test_dates_strictly_after_today_and_partial_window(self):
        for prompt in ('Concert today with RM2000', 'Concert on 2026-10-10 with RM2000', 'Concert in September 2026 with RM2000', 'Concert in March 2025 with RM2000'):
            with self.subTest(prompt=prompt), self.assertRaisesRegex(ValueError, 'strictly after today'):
                pipeline.parse_goal(prompt)
        goal, assumptions = pipeline.parse_goal('Concert between 2026-10-01 and 2026-10-31 with RM2000')
        self.assertEqual(goal['dateStart'], '2026-10-11')
        self.assertTrue(any(item['field'] == 'dateStart' and 'exclude today' in item['reason'] for item in assumptions))
        with patch.object(pipeline, 'date_weather', side_effect=weather), patch.object(pipeline, 'calendar_context', side_effect=context):
            dates = pipeline.scout_dates(goal, RESEARCH, pipeline.Trace(None))
        self.assertTrue(all(item['date'] > '2026-10-10' for item in dates['candidates']))
        self.assertGreater(dates['chosen']['date'], '2026-10-10')

    def test_named_dates_and_ranges_from_textbox(self):
        with self.assertRaisesRegex(ValueError, 'strictly after today'):
            pipeline.parse_goal('Concert on 5 October 2026 with RM2000')
        with self.assertRaisesRegex(ValueError, 'strictly after today'):
            pipeline.parse_goal('Concert on 10 October 2026 with RM2000')
        with self.assertRaisesRegex(ValueError, 'strictly after today'):
            pipeline.parse_goal('Concert on October 5, 2026 with RM2000')
        goal, _ = pipeline.parse_goal('Concert on 18 October 2026 with RM2000')
        self.assertEqual((goal['dateStart'], goal['dateEnd']), ('2026-10-18', '2026-10-18'))
        goal, _ = pipeline.parse_goal('Workshop between 1 and 30 November 2026 with RM3000')
        self.assertEqual((goal['dateStart'], goal['dateEnd']), ('2026-11-01', '2026-11-30'))
        with self.assertRaisesRegex(ValueError, 'invalid'):
            pipeline.parse_goal('Workshop on 31 November 2026 with RM3000')

    def test_relative_months_and_tomorrow(self):
        goal, _ = pipeline.parse_goal('Workshop next month with RM2000')
        self.assertEqual((goal['dateStart'], goal['dateEnd']), ('2026-11-01', '2026-11-30'))
        goal, _ = pipeline.parse_goal('Workshop this month with RM2000')
        self.assertEqual((goal['dateStart'], goal['dateEnd']), ('2026-10-11', '2026-10-31'))
        goal, _ = pipeline.parse_goal('Workshop tomorrow with RM2000')
        self.assertEqual((goal['dateStart'], goal['dateEnd']), ('2026-10-11', '2026-10-11'))
        with patch.object(pipeline, '_today', return_value=date(2026, 12, 31)):
            goal, _ = pipeline.parse_goal('Workshop next month with RM2000')
            self.assertEqual((goal['dateStart'], goal['dateEnd']), ('2027-01-01', '2027-01-31'))
            with self.assertRaisesRegex(ValueError, 'strictly after today'):
                pipeline.parse_goal('Workshop this month with RM2000')

    def test_rejects_invalid_overrides(self):
        for override in ({"bogus": 1}, {"attendance": True}, {"attendance": 0}, {"month": 13}, {"budgetRM": "NaN"}, {"budgetRM": -1}, {"budgetRM": "Infinity"}, {"dateStart": "not a date"}, {"dateStart": "2027-04-01", "dateEnd": "2027-03-01"}, {"organiserFundsRM": 6000}, {"location": ""}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                pipeline.parse_goal("Concert in March with RM5000", override)

    def test_exact_career_workshop_audience_is_not_cause(self):
        prompt = "Plan a career skills workshop at Taylor's Lakeside Campus for 80 students in November 2026 with a budget of RM3000."
        goal, assumptions = pipeline.parse_goal(prompt)
        self.assertEqual(goal["attendance"], 80)
        self.assertEqual(goal["cause"], "career skills learning and practice")
        self.assertFalse(goal["charityPurpose"])
        self.assertEqual((goal["month"], goal["year"]), (11, 2026))
        self.assertEqual(goal["budgetRM"], 3000)
        self.assertTrue(any(item["field"] == "cause" and item["editable"] and item["explicit"] for item in assumptions))

    def test_charity_audience_then_explicit_cause_prefers_beneficiary(self):
        for phrase in ("supporting animal welfare", "benefiting animal welfare", "raising funds for animal welfare", "for animal welfare"):
            with self.subTest(phrase=phrase):
                goal, _ = pipeline.parse_goal(f"Charity concert for 80 students at Taylor's Lakeside Campus {phrase} in March 2027 with RM3000")
                self.assertEqual(goal["cause"], "animal welfare")
                self.assertEqual(goal["attendance"], 80)
                self.assertTrue(goal["charityPurpose"])

    def test_nonpurpose_for_phrases_are_excluded(self):
        for phrase in ("80 students", "November 2026", "RM3000", "Taylor's Lakeside Campus"):
            with self.subTest(phrase=phrase):
                goal, _ = pipeline.parse_goal(f"Plan a career skills workshop for {phrase} in November 2026 with RM3000")
                self.assertEqual(goal["cause"], "career skills learning and practice")
                self.assertFalse(goal["charityPurpose"])

    def test_parses_type_cause_and_attendance(self):
        goal, _ = pipeline.parse_goal("A charity concert for animal welfare in March 2027 at Taylor's Lakeside with RM8000 for 150 attendees")
        self.assertEqual(goal["cause"], "animal welfare")
        self.assertEqual(goal["attendance"], 150)
        self.assertFalse(goal["attendanceAssumed"])
        self.assertEqual(goal["campus"], "Taylor's Lakeside Campus")

    def test_exact_basketball_competition_preserves_intent(self):
        prompt = "basketball competition"
        goal, assumptions = pipeline.parse_goal(prompt)
        self.assertEqual(goal["prompt"], prompt)
        self.assertEqual(goal["eventType"], prompt)
        self.assertEqual(goal["activityKind"], "basketball")
        self.assertFalse(goal["charityPurpose"])
        self.assertIsNone(goal["sportsDetails"]["teamCount"])
        self.assertIsNone(goal["sportsDetails"]["format"])
        self.assertFalse(any(item["field"] == "eventType" for item in assumptions))
        self.assertNotRegex(goal["cause"].lower(), r"charity|beneficiary|concert")

    def test_richer_basketball_preserves_money_dates_attendance_and_teams(self):
        for format_text, expected_format in (("3x3 ", "3x3"), ("5v5 ", "5v5"), ("", None)):
            prompt = f"Plan a {format_text}basketball tournament for 120 participants with 8 teams between 2027-04-03 and 2027-04-18 at Taylor's Lakeside Campus with RM3333.33."
            with self.subTest(format=expected_format):
                goal, _ = pipeline.parse_goal(prompt)
                self.assertEqual(goal["prompt"], prompt)
                self.assertIn("basketball tournament", goal["eventType"].lower())
                self.assertEqual(goal["activityKind"], "basketball")
                self.assertFalse(goal["charityPurpose"])
                self.assertEqual(goal["budgetRM"], 3333.33)
                self.assertEqual(goal["budgetCents"], 333333)
                self.assertEqual((goal["dateStart"], goal["dateEnd"]), ("2027-04-03", "2027-04-18"))
                self.assertEqual(goal["attendance"], 120)
                self.assertFalse(goal["attendanceAssumed"])
                self.assertEqual(goal["sportsDetails"]["teamCount"], 8)
                self.assertEqual(goal["sportsDetails"]["format"], expected_format)

    def test_explicit_basketball_tournament_is_retained(self):
        goal, _ = pipeline.parse_goal("basketball tournament")
        self.assertEqual(goal["eventType"], "basketball tournament")
        self.assertEqual(goal["activityKind"], "basketball")
        self.assertFalse(goal["charityPurpose"])

    def test_basketball_remains_primary_for_charity_and_fundraising(self):
        for prompt in (
            "Plan a charity basketball tournament supporting animal welfare in March 2027 with RM3000",
            "Plan a basketball tournament fundraiser raising funds for animal welfare in March 2027 with RM3000",
        ):
            with self.subTest(prompt=prompt):
                goal, _ = pipeline.parse_goal(prompt)
                self.assertEqual(goal["prompt"], prompt)
                self.assertEqual(goal["activityKind"], "basketball")
                self.assertIn("basketball tournament", goal["eventType"].lower())
                self.assertNotIn("concert", goal["eventType"].lower())
                self.assertTrue(goal["charityPurpose"])
                self.assertEqual(goal["cause"], "animal welfare")

    def test_negated_charity_concert_does_not_override_basketball(self):
        prompt = "Plan a basketball competition, not a charity concert, in March 2027 with RM3000"
        goal, _ = pipeline.parse_goal(prompt)
        self.assertEqual(goal["prompt"], prompt)
        self.assertEqual(goal["eventType"], "basketball competition")
        self.assertEqual(goal["activityKind"], "basketball")
        self.assertFalse(goal["charityPurpose"])
        self.assertNotRegex(goal["cause"].lower(), r"charity|beneficiary|concert")

    def test_unsupported_competitions_preserve_custom_noun_phrase(self):
        for noun_phrase in ("chess tournament", "debate competition"):
            prompt = f"Plan a {noun_phrase} for 80 students in November 2026 with RM3000"
            with self.subTest(activity=noun_phrase):
                goal, assumptions = pipeline.parse_goal(prompt)
                self.assertEqual(goal["prompt"], prompt)
                self.assertEqual(goal["eventType"], noun_phrase)
                self.assertEqual(goal["activityKind"], "general")
                self.assertFalse(goal["charityPurpose"])
                self.assertFalse(any(item["field"] == "eventType" for item in assumptions))

    def test_football_is_sports_not_basketball(self):
        goal, _ = pipeline.parse_goal("football tournament")
        self.assertEqual(goal["eventType"], "football tournament")
        self.assertEqual(goal["activityKind"], "sports")
        self.assertFalse(goal["charityPurpose"])

    def test_topics_negation_and_running_do_not_become_court_competitions(self):
        for prompt, kind, charity in (("Workshop for basketball coaches", "workshop", False),
            ("Plan a concert, not a basketball tournament", "concert", False),
            ("Basketball competition with no donations", "basketball", False),
            ("Basketball competition without fundraising", "basketball", False),
            ("Plan a marathon next month", "general", False)):
            with self.subTest(prompt=prompt):
                goal, _ = pipeline.parse_goal(prompt)
                self.assertEqual(goal["activityKind"], kind)
                self.assertEqual(goal["charityPurpose"], charity)

    def test_unspecified_event_is_general_not_charity_concert(self):
        prompt = "Plan an event"
        goal, _ = pipeline.parse_goal(prompt)
        self.assertEqual(goal["prompt"], prompt)
        self.assertEqual(goal["activityKind"], "general")
        self.assertFalse(goal["charityPurpose"])
        self.assertNotRegex(goal["eventType"].lower(), r"charity|concert|basketball")


class BudgetTests(PinnedClockTest):
    def test_integer_cents_contingency_and_no_overrun(self):
        for amount in ("1", "10.01", "3333.33", "5000", "99999.99"):
            goal, _ = pipeline.parse_goal("Concert in March", {"budgetRM": amount})
            for indoor in (False, True):
                with self.subTest(amount=amount, indoor=indoor):
                    budget = pipeline.build_budget(goal, indoor)
                    self.assertEqual(sum(item["amountCents"] for item in budget["items"]), goal["budgetCents"])
                    self.assertLessEqual(budget["totalCents"], budget["limitCents"])
                    self.assertGreaterEqual(budget["contingencyCents"] * 10, budget["totalCents"])
                    self.assertTrue(all(item["estimated"] for item in budget["items"]))
                    self.assertEqual(budget["gapCents"], budget["totalCents"] - budget["organiserFundsCents"])

    def test_indoor_rebalance_changes_actual_allocations(self):
        goal, _ = pipeline.parse_goal("Concert in March with RM5000")
        base = pipeline.build_budget(goal)
        indoor = pipeline.build_budget(goal, True)
        self.assertNotEqual(base["items"][0]["amountCents"], indoor["items"][0]["amountCents"])
        self.assertEqual(base["totalCents"], indoor["totalCents"])

    def test_basketball_budget_uses_sports_allocations(self):
        goal, _ = pipeline.parse_goal("basketball competition with RM5000")
        for indoor in (False, True):
            with self.subTest(indoor=indoor):
                budget = pipeline.build_budget(goal, indoor)
                categories = " ".join(item["category"] for item in budget["items"]).lower()
                for category in (r"court", r"equipment", r"official|referee", r"hydration|water", r"operations", r"first[ -]aid", r"reserve"):
                    self.assertRegex(categories, category)
                self.assertNotRegex(categories, r"\b(?:av|talent|performers?|music|charity)\b")
                self.assertTrue(all(item["estimated"] for item in budget["items"]))

    def test_basketball_budget_reconciles_integer_cents_in_both_modes(self):
        for amount in ("1", "10.01", "3333.33", "5000", "99999.99"):
            goal, _ = pipeline.parse_goal("basketball competition", {"budgetRM": amount})
            for indoor in (False, True):
                with self.subTest(amount=amount, indoor=indoor):
                    budget = pipeline.build_budget(goal, indoor)
                    self.assertTrue(all(type(item["amountCents"]) is int and item["amountCents"] >= 0 for item in budget["items"]))
                    self.assertEqual(sum(item["amountCents"] for item in budget["items"]), goal["budgetCents"])
                    self.assertEqual(budget["totalCents"], goal["budgetCents"])
                    self.assertEqual(budget["limitCents"], goal["budgetCents"])
                    self.assertGreaterEqual(budget["contingencyCents"] * 10, budget["totalCents"])
                    reserves = [item for item in budget["items"] if item["category"] == "Contingency reserve"]
                    self.assertEqual(len(reserves), 1)
                    self.assertEqual(reserves[0]["amountCents"], budget["contingencyCents"])
                    self.assertEqual(budget["gapCents"], budget["totalCents"] - budget["organiserFundsCents"])
                    for item in budget["items"]:
                        self.assertEqual(round(item["amountRM"] * 100), item["amountCents"])


class RuntimeTests(PinnedClockTest):
    def run_pack(self, **kwargs):
        with patch.object(pipeline, "load_research", return_value=copy.deepcopy(RESEARCH)), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=context):
            return pipeline.run_pipeline("Charity concert for animal welfare in March with RM5000 at Taylor's Lakeside", **kwargs)

    def test_all_tabs_real_trace_and_honest_readiness(self):
        emitted = []
        pack = self.run_pack(emit=lambda *args: emitted.append(args))
        self.assertEqual(set(pack), {"goal", "assumptions", "dateDecision", "budget", "weather", "risks", "people", "venues", "programme", "sponsors", "drafts", "promo", "validation", "summary", "rechecks", "engine", "metrics"})
        self.assertEqual(len(pack["dateDecision"]["candidates"]), 5)
        self.assertEqual(len(pack["dateDecision"]["backups"]), 2)
        self.assertEqual(len(pack["risks"]["register"]), 8)
        self.assertEqual(len(pack["risks"]["planB"]), 3)
        self.assertEqual(len(pack["promo"]["captions"]), 3)
        self.assertEqual([check["daysBefore"] for check in pack["rechecks"]], [14, 7, 1])
        self.assertTrue(pack["validation"]["passed"])
        self.assertFalse(pack["validation"]["ready"])
        self.assertEqual(pack["validation"]["status"], "Conditional plan—approvals required")
        self.assertEqual(pack["metrics"]["llmCalls"], 0)
        self.assertEqual(pack["metrics"]["emailsSent"], 0)
        self.assertEqual(pack["metrics"]["repairLoops"], 0)
        self.assertIn("LLM unavailable", pack["engine"])
        self.assertEqual(len(emitted), len(pack["metrics"]["trace"]))
        self.assertTrue(any(event[1] == "tool_call" for event in emitted))
        json.dumps(pack, allow_nan=False)

    def test_dynamic_weather_replan_changes_schedule_and_budget(self):
        pack = self.run_pack()
        self.assertTrue(pack["weather"]["indoorRequired"])
        self.assertEqual(pack["programme"]["mode"], "Indoor contingency")
        self.assertEqual(pack["programme"]["startTime"], "16:30")
        self.assertEqual(pack["budget"]["scenario"], "Indoor weather contingency")
        self.assertTrue(any(event["status"] == "replan" for event in pack["metrics"]["trace"]))
        base = pipeline.build_budget(pack["goal"])
        self.assertNotEqual(base["items"][0]["amountCents"], pack["budget"]["items"][0]["amountCents"])

    def test_dry_weather_does_not_fake_replan(self):
        def dry(day, location, emit=None):
            return {"date": day, "probability": .4, "mode": "test fixture"}
        with patch.object(pipeline, "load_research", return_value=RESEARCH), patch.object(pipeline, "date_weather", side_effect=dry), patch.object(pipeline, "calendar_context", side_effect=context):
            pack = pipeline.run_pipeline("Concert in March with RM5000")
        self.assertFalse(pack["weather"]["indoorRequired"])
        self.assertFalse(any(event["status"] == "replan" for event in pack["metrics"]["trace"]))
        self.assertEqual(pack["programme"]["startTime"], "17:00")

    def test_weather_and_calendar_exceptions_are_visible(self):
        with patch.object(pipeline, "load_research", return_value=RESEARCH), patch.object(pipeline, "date_weather", side_effect=OSError("offline")), patch.object(pipeline, "calendar_context", side_effect=OSError("offline")):
            pack = pipeline.run_pipeline("Concert in March with RM5000")
        self.assertIsNone(pack["weather"]["probability"])
        self.assertTrue(pack["weather"]["indoorRequired"])
        self.assertTrue(any("unavailable" in warning.lower() for warning in pack["validation"]["warnings"]))
        self.assertEqual(pack["dateDecision"]["chosen"]["examStatus"], "unknown")

    def test_cited_holiday_clash_is_excluded(self):
        def holidays(year, month, emit=None):
            return {"holidays": [{"date": "2027-03-06", "name": "Test fixture holiday", "source": "https://example.org/calendar"}], "exams": [{"date": "2027-03-13", "source": "https://example.org/exams"}]}
        with patch.object(pipeline, "load_research", return_value=RESEARCH), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=holidays):
            pack = pipeline.run_pipeline("Concert in March with RM5000")
        self.assertNotIn(pack["dateDecision"]["chosen"]["date"], {"2027-03-06", "2027-03-13"})
        self.assertTrue(next(item for item in pack["dateDecision"]["candidates"] if item["date"] == "2027-03-06")["blocked"])

    def test_no_eligible_date_is_a_genuine_unrepaired_failure(self):
        with patch.object(pipeline, "load_research", return_value=RESEARCH), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=context):
            pack = pipeline.run_pipeline("Concert in March with RM5000", {"dateStart": "2027-03-01", "dateEnd": "2027-03-05"})
        self.assertIsNone(pack["dateDecision"]["chosen"])
        self.assertFalse(pack["validation"]["passed"])
        self.assertEqual(pack["validation"]["status"], "Blocked—resolve failed checks")
        self.assertEqual(pack["validation"]["repairLoops"], 0)

    def test_real_empty_roster_stays_unknown_and_demo_has_no_contacts(self):
        default = self.run_pack()
        self.assertEqual(default["people"]["roster"], [])
        self.assertFalse(default["people"]["demo"])
        self.assertIsNone(default["people"]["topMC"])
        self.assertEqual(default["drafts"]["mc"], [])
        demo = self.run_pack(roster=[{"name": "Fictional Demo MC", "role": "MC", "demo": True, "freeDates": ["2027-03-06"]}])
        self.assertTrue(demo["people"]["demo"])
        self.assertTrue(all(item["demo"] for item in demo["people"]["roster"]))
        self.assertTrue(all(item["to"] is None for item in demo["drafts"]["mc"]))
        real = self.run_pack(roster=[])
        self.assertFalse(real["people"]["demo"])
        self.assertIsNone(real["people"]["topMC"])
        self.assertFalse(real["people"]["bookingConfirmed"])

    def test_user_roster_ranking_and_contact_boundary(self):
        pack = self.run_pack(roster=[{"name": "User Role A", "role": "MC", "experienceScore": 3, "freeDates": ["2027-03-06"], "email": "role-a@example.org"}, {"name": "User Role B", "role": "MC", "experienceScore": 5, "freeDates": ["2027-03-06"]}])
        self.assertEqual(pack["people"]["topMC"]["name"], "User Role B")
        self.assertEqual(pack["drafts"]["mc"][1]["to"], "role-a@example.org")
        self.assertFalse(pack["people"]["bookingConfirmed"])

    def test_unverified_contacts_and_venues_are_never_invented(self):
        data = copy.deepcopy(RESEARCH)
        data["sponsors"][0]["emailSource"] = None
        data["sponsors"].append({"name": "Uncited fixture", "email": "invented@example.org"})
        data["campus"]["venues"].append({"name": "Uncited hall", "capacity": 1000})
        with patch.object(pipeline, "load_research", return_value=data), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=context):
            pack = pipeline.run_pipeline("Concert in March with RM5000")
        self.assertIsNone(pack["sponsors"][0]["email"])
        self.assertFalse(any(item["name"] == "Uncited fixture" for item in pack["sponsors"]))
        self.assertFalse(any(item["name"] == "Uncited hall" for item in pack["venues"]["options"]))
        self.assertIsNone(pack["venues"]["options"][0]["capacity"])

    def test_researched_sponsor_constraints_and_contact_routes_survive(self):
        data = copy.deepcopy(RESEARCH)
        data["sponsors"][0].update(constraints=["Proposal at least 30 days before event", "No cash programme established"], suggestedHypotheticalAsk="100 in-kind fixture badges subject to approval", countsTowardVerifiedSuitableEmailMinimum=False, contactUrl="https://example.org/official-form")
        with patch.object(pipeline, "load_research", return_value=data), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=context):
            pack = pipeline.run_pipeline("Concert in March with RM5000")
        self.assertEqual(pack["sponsors"][0]["contactUrl"], "https://example.org/official-form")
        self.assertIn("Proposal at least 30 days", pack["drafts"]["sponsorEmails"][0]["body"])
        self.assertIn("100 in-kind fixture badges", pack["drafts"]["sponsorEmails"][0]["body"])
        self.assertIn("not a verified dedicated sponsorship route", pack["drafts"]["sponsorEmails"][0]["body"])

    def test_five_or_more_unsent_source_bound_emails_and_followups(self):
        pack = self.run_pack()
        self.assertGreaterEqual(len(pack["drafts"]["sponsorEmails"]), 5)
        self.assertEqual(len(pack["drafts"]["followups"]), 12)
        self.assertEqual(sum(item["askCents"] for item in pack["sponsors"][:5]), pack["budget"]["gapCents"])
        self.assertTrue(all(item["promisedRM"] == 0 for item in pack["sponsors"]))
        for draft in pack["drafts"]["sponsorEmails"]:
            self.assertIn("EventPilot", draft["subject"])
            self.assertIn("planning assumption", draft["body"])
            self.assertIn(pack["dateDecision"]["chosen"]["date"], draft["body"])
            self.assertIn("unconfirmed", draft["body"])
            self.assertEqual(draft["status"], "Draft—unsent")
            self.assertTrue(draft["source"])

    def test_validator_detects_real_budget_and_draft_failures(self):
        pack = self.run_pack()
        pack["budget"]["items"][0]["amountCents"] += 1
        pack["drafts"]["sponsorEmails"][0]["attendance"] += 1
        result = pipeline.validate_pack(pack)
        self.assertFalse(result["passed"])
        self.assertEqual({error["code"] for error in result["errors"]}, {"budget", "funding", "drafts"})

    def test_real_repair_loop_runs_only_after_failure(self):
        original = pipeline.build_budget
        calls = 0

        def corrupt_once(goal, indoor=False):
            nonlocal calls
            result = original(goal, indoor)
            calls += 1
            if calls == 2:
                result["items"][0]["amountCents"] += 1
            return result

        with patch.object(pipeline, "load_research", return_value=RESEARCH), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=context), patch.object(pipeline, "build_budget", side_effect=corrupt_once):
            pack = pipeline.run_pipeline("Concert in March with RM5000")
        self.assertTrue(pack["validation"]["passed"])
        self.assertEqual(pack["validation"]["repairLoops"], 1)
        self.assertTrue(any(event["tool"] == "repair_pack" for event in pack["metrics"]["trace"]))

    def test_weather_checks_execute_in_parallel(self):
        barrier = threading.Barrier(5)
        threads = set()
        lock = threading.Lock()

        def parallel_weather(day, location, emit=None):
            with lock:
                threads.add(threading.current_thread().name)
            barrier.wait(timeout=5)
            return weather(day, location)

        with patch.object(pipeline, "load_research", return_value=RESEARCH), patch.object(pipeline, "date_weather", side_effect=parallel_weather), patch.object(pipeline, "calendar_context", side_effect=context):
            pack = pipeline.run_pipeline("Concert in March with RM5000")
        self.assertEqual(len(threads), 5)
        self.assertTrue(pack["validation"]["passed"])

    def test_unsuitable_sponsor_email_and_followups_are_blank(self):
        data = copy.deepcopy(RESEARCH)
        data["sponsors"][0]["countsTowardVerifiedSuitableEmailMinimum"] = False
        with patch.object(pipeline, "load_research", return_value=data), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=context):
            pack = pipeline.run_pipeline("Concert in March with RM5000")
        self.assertIsNone(pack["sponsors"][0]["email"])
        self.assertIsNone(pack["drafts"]["sponsorEmails"][0]["to"])
        self.assertTrue(all(entry["to"] is None for entry in pack["drafts"]["followups"] if entry["recipient"] == data["sponsors"][0]["name"]))
        pack["sponsors"][0]["email"] = data["sponsors"][0]["email"]
        pack["sponsors"][0]["emailSource"] = data["sponsors"][0]["emailSource"]
        pack["drafts"]["sponsorEmails"][0]["to"] = data["sponsors"][0]["email"]
        errors = {entry["code"] for entry in pipeline.validate_pack(pack)["errors"]}
        self.assertIn("contacts", errors)
        self.assertIn("draft_contacts", errors)

    def test_exact_career_workshop_has_learning_operations_not_charity(self):
        with patch.object(pipeline, "load_research", return_value=RESEARCH), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=context):
            pack = pipeline.run_pipeline("Plan a career skills workshop at Taylor's Lakeside Campus for 80 students in November 2026 with a budget of RM3000.")
        operations = json.dumps(pack["programme"]).lower()
        for leakage in ("charity", "beneficiary", "donation", "confirm acts", "talent lead", "mc drafts"):
            self.assertNotIn(leakage, operations)
        self.assertIn("career skills", operations)
        self.assertIn("confirm facilitators", operations)
        self.assertIn("session materials", operations)
        self.assertTrue(pack["validation"]["passed"])
        self.assertNotIn("charity permission", json.dumps(pack["promo"]).lower())
        self.assertTrue(all("proposed student activity partnership" in entry["subject"] for entry in pack["drafts"]["followups"]))
        self.assertTrue(all("direct net proceeds" not in entry["body"] for entry in pack["drafts"]["sponsorEmails"]))
        refreshed = pipeline.apply_weather_update(pack, {"probability": .2, "mode": "forecast"})
        self.assertNotIn("charity", json.dumps(refreshed["programme"]).lower())

    def test_explicit_charity_workshop_retains_beneficiary_operations(self):
        with patch.object(pipeline, "load_research", return_value=RESEARCH), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=context):
            pack = pipeline.run_pipeline("Charity workshop for 80 students supporting animal welfare in March 2027 with RM3000")
        self.assertEqual(pack["goal"]["cause"], "animal welfare")
        self.assertTrue(pack["goal"]["charityPurpose"])
        self.assertIn("Charity Liaison", json.dumps(pack["programme"]["runOfShow"]))
        self.assertIn("beneficiary", json.dumps(pack["programme"]["countdown"]))

    def test_workshop_bazaar_showcase_are_activity_specific(self):
        for variant, expected in (("workshop", "hands-on practice"), ("bazaar", "student stalls"), ("showcase", "project demonstrations")):
            with self.subTest(variant=variant), patch.object(pipeline, "load_research", return_value=RESEARCH), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=context):
                pack = pipeline.run_pipeline(f"{variant} for animal welfare in March with RM5000")
            self.assertEqual(pack["goal"]["eventType"], variant)
            self.assertEqual(pack["programme"]["variant"], variant)
            self.assertIn(expected, " ".join(item["activity"] for item in pack["programme"]["runOfShow"]))
            self.assertNotIn("Student performance set", " ".join(item["activity"] for item in pack["programme"]["runOfShow"]))
            self.assertNotIn("music", pack["promo"]["poster"]["headline"].lower())
            self.assertTrue(pack["validation"]["passed"])

    def test_weather_updates_low_high_unavailable_are_coherent(self):
        pack = self.run_pack()
        original = copy.deepcopy(pack)
        day = pack["dateDecision"]["chosen"]["date"]
        emitted = []
        low = pipeline.apply_weather_update(pack, {"date": day, "probability": .2, "available": True, "mode": "forecast", "sourceUrls": ["https://example.org/new-weather"]}, emit=lambda *args: emitted.append(args))
        self.assertEqual(pack, original)
        self.assertEqual(low["programme"]["startTime"], "17:00")
        self.assertEqual(low["budget"]["scenario"], "Base proposed plan")
        self.assertFalse(low["weather"]["indoorRequired"])
        self.assertEqual(low["dateDecision"]["chosen"]["weather"]["probability"], .2)
        self.assertTrue(any("17:00" in entry["body"] for entry in low["drafts"]["sponsorEmails"]))
        high = pipeline.apply_weather_update(low, {"date": day, "rainProbability": 80, "rainProbabilityKind": "forecast (%)", "available": True, "mode": "forecast"})
        self.assertEqual(high["weather"]["probability"], .8)
        self.assertEqual(high["programme"]["startTime"], "16:30")
        self.assertEqual(high["budget"]["scenario"], "Indoor weather contingency")
        self.assertIn("Indoor contingency required", high["summary"]["narrative"])
        unavailable = pipeline.apply_weather_update(low, {"date": day, "probability": .1, "available": False, "mode": "unavailable"})
        self.assertIsNone(unavailable["weather"]["probability"])
        self.assertTrue(unavailable["weather"]["indoorRequired"])
        for updated in (low, high, unavailable):
            self.assertTrue(updated["validation"]["passed"])
            self.assertFalse(updated["validation"]["ready"])
            self.assertEqual(updated["budget"]["totalCents"], pack["goal"]["budgetCents"])
            self.assertGreaterEqual(updated["budget"]["contingencyCents"] * 10, updated["budget"]["totalCents"])
        self.assertTrue(any(entry[1] == "replan" for entry in emitted))

    def test_weather_update_preserves_flat_drafts_private_run_metadata(self):
        pack = self.run_pack()
        pack.update(mode="private", runId="private-test-run", privacy={"ownerOnly": True}, generatedAt="original-time")
        pack["metrics"].pop("trace")
        pack["metrics"].update(networkRequests=11, gmailDraftsCreated=0, customMetric="retain")
        pack["drafts"] = [{**entry, "type": kind} for key, kind in (("sponsorEmails", "sponsor"), ("followups", "followup"), ("mc", "mc")) for entry in pack["drafts"][key]]
        pack["drafts"][0]["localDraftId"] = "retain-id"
        updated = pipeline.apply_weather_update(pack, {"date": pack["dateDecision"]["chosen"]["date"], "probability": .1, "mode": "forecast"})
        self.assertIsInstance(updated["drafts"], list)
        self.assertEqual(updated["drafts"][0]["type"], "sponsor")
        self.assertEqual(updated["drafts"][0]["localDraftId"], "retain-id")
        for field in ("mode", "runId", "privacy", "generatedAt"):
            self.assertEqual(updated[field], pack[field])
        self.assertEqual(updated["metrics"]["networkRequests"], 11)
        self.assertEqual(updated["metrics"]["customMetric"], "retain")
        self.assertNotIn("trace", updated["metrics"])
        self.assertTrue(pipeline.validate_pack(updated)["passed"])

    def test_weather_update_rejects_other_date(self):
        pack = self.run_pack()
        with self.assertRaises(ValueError):
            pipeline.apply_weather_update(pack, {"date": "2027-12-01", "probability": .2})

    def test_weather_update_real_repairs_are_bounded(self):
        pack = self.run_pack()
        real_validate = pipeline.validate_pack
        calls = 0

        def fail_budget(current):
            nonlocal calls
            calls += 1
            result = real_validate(current)
            result["errors"].append({"code": "budget", "message": "Injected genuine test failure"})
            result["passed"] = False
            return result

        with patch.object(pipeline, "validate_pack", side_effect=fail_budget):
            updated = pipeline.apply_weather_update(pack, {"probability": .9, "mode": "forecast"})
        self.assertEqual(updated["validation"]["repairLoops"], 2)
        self.assertEqual(calls, 3)
        self.assertFalse(updated["validation"]["passed"])

    def test_custom_campus_does_not_reuse_unrelated_cited_venues(self):
        pack = self.run_pack(overrides={"campus": "Custom Campus", "location": "Custom location"})
        self.assertEqual(pack["venues"]["options"], [])
        self.assertIsNone(pack["venues"]["selected"])
        self.assertFalse(pack["validation"]["ready"])


class ActivityIntentTests(PinnedClockTest):
    def run_pack(self, prompt, weather_effect=weather):
        data = copy.deepcopy(RESEARCH)
        with patch.object(pipeline, "load_research", return_value=data), patch.object(pipeline, "date_weather", side_effect=weather_effect), patch.object(pipeline, "calendar_context", side_effect=context):
            return pipeline.run_pipeline(prompt)

    def assert_basketball_operations(self, pack, charity=False):
        self.assertEqual(pack["goal"]["activityKind"], "basketball")
        self.assertEqual(pack["goal"]["charityPurpose"], charity)
        self.assertEqual(pack["programme"]["variant"], "basketball")
        activities = " ".join(item["activity"] for item in pack["programme"]["runOfShow"]).lower()
        self.assertRegex(activities, r"\bmatch(?:es)?\b")
        self.assertRegex(activities, r"(?:referee|official).*brief|brief.*(?:referee|official)")
        operations = json.dumps(pack["programme"]).lower()
        self.assertNotRegex(operations, r"performances?|performers?|facilitators?|sound[ -]?check|acoustic|talent lead")
        if not charity:
            self.assertNotRegex(operations, r"charity|beneficiar\w*|donations?")
        self.assertEqual(pack["promo"]["variant"], "basketball")
        promo = json.dumps(pack["promo"]).lower()
        self.assertIn("basketball", promo)
        self.assertNotRegex(promo, r"\b(?:music|concert|performances?|performers?|acoustic)\b")
        self.assertTrue(pack["validation"]["passed"])
        self.assertFalse(pack["validation"]["ready"])

    def test_exact_basketball_pack_has_matches_and_sports_promotion(self):
        pack = self.run_pack("basketball competition")
        self.assertEqual(pack["goal"]["eventType"], "basketball competition")
        self.assertEqual(pack["goal"]["prompt"], "basketball competition")
        self.assert_basketball_operations(pack)
        self.assertEqual(pack["metrics"]["llmCalls"], 0)
        self.assertEqual(pack["metrics"]["emailsSent"], 0)

    def test_richer_basketball_pack_retains_explicit_inputs(self):
        prompt = "Plan a 3x3 basketball tournament with 8 teams for 120 participants between 2027-04-03 and 2027-04-18 at Taylor's Lakeside Campus with RM3333.33."
        pack = self.run_pack(prompt)
        self.assert_basketball_operations(pack)
        self.assertEqual(pack["goal"]["prompt"], prompt)
        self.assertEqual(pack["goal"]["budgetCents"], 333333)
        self.assertEqual(pack["budget"]["totalCents"], 333333)
        self.assertEqual(pack["goal"]["attendance"], 120)
        self.assertEqual((pack["goal"]["dateStart"], pack["goal"]["dateEnd"]), ("2027-04-03", "2027-04-18"))
        self.assertEqual(pack["goal"]["sportsDetails"]["teamCount"], 8)
        self.assertEqual(pack["goal"]["sportsDetails"]["format"], "3x3")
        self.assertTrue(all("2027-04-03" <= item["date"] <= "2027-04-18" for item in pack["dateDecision"]["candidates"]))
        self.assertTrue(all(item["attendance"] == 120 for item in pack["drafts"]["sponsorEmails"]))

    def test_explicit_charity_basketball_keeps_sport_and_beneficiary_operations(self):
        for prefix in ("charity basketball tournament", "basketball tournament fundraiser"):
            with self.subTest(event=prefix):
                pack = self.run_pack(f"Plan a {prefix} for 80 students supporting animal welfare in March 2027 with RM3000")
                self.assert_basketball_operations(pack, charity=True)
                self.assertEqual(pack["goal"]["cause"], "animal welfare")
                self.assertRegex(json.dumps(pack["programme"]).lower(), r"charity|beneficiar\w*|donations?")
                self.assertIn("animal welfare", json.dumps(pack["promo"]).lower())
                self.assertNotRegex(json.dumps(pack["risks"]).lower(), r"acoustic|sound[ -]?check|performances?|performers?")

    def test_negated_charity_concert_has_no_charity_operations(self):
        pack = self.run_pack("Plan a basketball competition, not a charity concert, in March 2027 with RM3000")
        self.assert_basketball_operations(pack)
        self.assertEqual(pack["goal"]["eventType"], "basketball competition")

    def test_custom_and_unspecified_events_have_neutral_general_stages(self):
        for prompt, event_type in (
            ("Plan a chess tournament for 80 students in November 2026 with RM3000", "chess tournament"),
            ("Plan a debate competition for 80 students in November 2026 with RM3000", "debate competition"),
            ("Plan an event", None),
        ):
            with self.subTest(prompt=prompt):
                pack = self.run_pack(prompt)
                self.assertEqual(pack["goal"]["prompt"], prompt)
                self.assertEqual(pack["goal"]["activityKind"], "general")
                self.assertFalse(pack["goal"]["charityPurpose"])
                if event_type:
                    self.assertEqual(pack["goal"]["eventType"], event_type)
                self.assertEqual(pack["programme"]["variant"], "general")
                self.assertEqual(pack["promo"]["variant"], "general")
                self.assertTrue(pack["programme"]["runOfShow"])
                activities = " ".join(item["activity"] for item in pack["programme"]["runOfShow"]).lower()
                self.assertRegex(activities, r"check[ -]?in|registration|briefing")
                self.assertNotRegex(json.dumps(pack["programme"]).lower(), r"performances?|performers?|facilitators?|sound[ -]?check|charity|beneficiar\w*|donations?")
                self.assertNotRegex(json.dumps(pack["promo"]).lower(), r"\b(?:music|concert|performances?|basketball)\b")
                self.assertTrue(pack["validation"]["passed"])

    def test_football_pack_uses_sports_not_basketball_or_music(self):
        pack = self.run_pack("Plan a football tournament in March 2027 with RM5000")
        self.assertEqual(pack["goal"]["eventType"], "football tournament")
        self.assertEqual(pack["goal"]["activityKind"], "sports")
        self.assertFalse(pack["goal"]["charityPurpose"])
        self.assertEqual(pack["programme"]["variant"], "sports")
        self.assertEqual(pack["promo"]["variant"], "sports")
        self.assertIn("football", json.dumps(pack["promo"]).lower())
        for section in ("programme", "promo", "risks"):
            self.assertNotRegex(json.dumps(pack[section]).lower(), r"\b(?:basketball|music|concert|acoustic|performances?|performers?)\b")
        self.assertTrue(pack["validation"]["passed"])

    def test_basketball_required_roles_do_not_invent_people_or_availability(self):
        pack = self.run_pack("basketball competition")
        people = pack["people"]
        roles = json.dumps(people["requiredRoles"]).lower()
        self.assertIn("referee", roles)
        self.assertRegex(roles, r"scorer|scorekeeper|score[ -]?keeper")
        self.assertEqual(people["roster"], [])
        self.assertFalse(people["demo"])
        self.assertFalse(people["bookingConfirmed"])
        self.assertIsNone(people["topMC"])
        self.assertIsNone(people["backupMC"])
        self.assertRegex(people["availabilityStatus"].lower(), r"unknown|unconfirmed")
        self.assertEqual(pack["drafts"]["mc"], [])

    def test_basketball_venue_selection_requires_cited_explicit_activity_list(self):
        data = copy.deepcopy(RESEARCH)
        hall = data["campus"]["venues"][0]
        unrelated = {**hall, "name": "Cited Football Facility", "activities": ["football"], "capacity": 300}
        court = {**hall, "name": "Cited Basketball Court", "activities": ["basketball", "volleyball"], "capacity": 180}
        uncited = {**court, "name": "Uncited Basketball Court", "source": None}
        too_small = {**court, "name": "Small Basketball Court", "capacity": 10}
        data["campus"]["venues"] = [hall, unrelated, uncited, too_small, court]
        original = copy.deepcopy(data)
        goal, _ = pipeline.parse_goal("basketball competition for 120 participants")
        venues = pipeline.build_venues(goal, data)
        self.assertEqual(data, original)
        self.assertEqual(venues["selected"]["name"], court["name"])
        self.assertEqual(venues["selected"]["source"], court["source"])
        self.assertIn("basketball", venues["selected"]["activities"])
        self.assertEqual({item["name"] for item in venues["options"]}, {item["name"] for item in (hall, unrelated, too_small, court)})
        for option in venues["options"]:
            original_option = next(item for item in original["campus"]["venues"] if item["name"] == option["name"])
            for field in ("name", "source", "capacity", "notes", "indoor"):
                self.assertEqual(option[field], original_option[field])

    def test_basketball_venues_without_activity_evidence_remain_pending_options(self):
        for evidence in ({}, {"activities": []}, {"activities": ["football"]}, {"activities": "basketball"}, {"notes": "Basketball court mentioned in unstructured notes"}):
            with self.subTest(evidence=evidence):
                data = copy.deepcopy(RESEARCH)
                data["campus"]["venues"][0].update(evidence)
                goal, _ = pipeline.parse_goal("basketball competition")
                venues = pipeline.build_venues(goal, data)
                self.assertIsNone(venues["selected"])
                self.assertEqual(len(venues["options"]), 1)
                option = venues["options"][0]
                self.assertEqual(option["name"], data["campus"]["venues"][0]["name"])
                self.assertEqual(option["source"], data["campus"]["venues"][0]["source"])
                self.assertEqual(option["notes"], data["campus"]["venues"][0]["notes"])
                self.assertRegex(json.dumps(option).lower(), r'"[^"]*compatib[^"]*"\s*:\s*"[^"]*(?:pending|unknown|unconfirmed|not confirmed)')

    def test_wet_weather_clears_outdoor_court_selection(self):
        data = copy.deepcopy(RESEARCH)
        data["campus"]["venues"][0].update(activities=["basketball"], indoor=False, capacity=200)
        def dry(day, location, emit=None):
            return {"date": day, "probability": .2, "mode": "test fixture"}
        with patch.object(pipeline, "load_research", return_value=data), patch.object(pipeline, "date_weather", side_effect=dry), patch.object(pipeline, "calendar_context", side_effect=context):
            pack = pipeline.run_pipeline("basketball competition")
        self.assertIsNotNone(pack["venues"]["selected"])
        updated = pipeline.apply_weather_update(pack, {"probability": .8, "mode": "test fixture"})
        self.assertIsNone(updated["venues"]["selected"])
        self.assertEqual(len(updated["venues"]["options"]), 1)
        self.assertTrue(updated["validation"]["passed"])
        self.assertIn("campus-approved venue to be confirmed", updated["drafts"]["sponsorEmails"][0]["body"])
        self.assertIsNotNone(pack["venues"]["selected"])

    def test_multiword_sport_uses_explicit_facility_activity(self):
        goal, _ = pipeline.parse_goal("table tennis tournament")
        data = copy.deepcopy(RESEARCH)
        data["campus"]["venues"][0]["activities"] = ["table tennis"]
        self.assertEqual(goal["sportsDetails"]["sport"], "table tennis")
        self.assertIsNotNone(pipeline.build_venues(goal, data)["selected"])

    def test_role_enquiries_survive_public_normalization_and_recheck(self):
        import server
        with patch.object(pipeline, "load_research", return_value=RESEARCH), patch.object(pipeline, "date_weather", side_effect=weather), patch.object(pipeline, "calendar_context", side_effect=context):
            pack = pipeline.run_pipeline("basketball competition", roster=[{"name": "Supplied official", "role": "referee", "email": "official@example.org"}])
        self.assertEqual(len(pack["drafts"]["roles"]), 1)
        flat = server.normalize_public_pack(copy.deepcopy(pack))
        self.assertIn("role", [draft["type"] for draft in flat["drafts"]])
        updated = pipeline.apply_weather_update(flat, {"probability": .2, "mode": "test fixture"})
        role = next(draft for draft in updated["drafts"] if draft["type"] == "role")
        self.assertEqual(role["to"], "official@example.org")
        self.assertIn("basketball competition", role["body"])
        self.assertEqual(role["status"], "Draft—unsent")

    def test_basketball_risks_require_compatible_approved_facility_or_postponement(self):
        goal, _ = pipeline.parse_goal("basketball competition")
        for evidence in ({"probability": .2}, {"probability": .8}, {"probability": None, "mode": "unavailable"}):
            with self.subTest(weather=evidence):
                risks = pipeline.build_risks(goal, evidence)
                actions = " ".join(item["action"] for item in risks["planB"]).lower()
                self.assertRegex(actions, r"approved|approval")
                self.assertRegex(actions, r"basketball|sport[ -]?compatible|compatible.*(?:court|facility)")
                self.assertRegex(actions, r"court|facility")
                self.assertRegex(actions, r"postpon\w*")
                self.assertNotRegex(json.dumps(risks).lower(), r"acoustic|sound[ -]?check|performances?|performers?|facilitators?")

    def test_basketball_initial_low_high_and_unavailable_weather_preserves_intent(self):
        for probability, indoor in ((.2, False), (.8, True), (None, True)):
            def supplied_weather(day, location, emit=None):
                return {**weather(day, location, emit), "probability": probability, "mode": "test fixture" if probability is not None else "unavailable", "available": probability is not None}

            with self.subTest(probability=probability):
                pack = self.run_pack("basketball competition", weather_effect=supplied_weather)
                self.assert_basketball_operations(pack)
                self.assertEqual(pack["weather"]["probability"], probability)
                self.assertEqual(pack["weather"]["indoorRequired"], indoor)
                self.assertEqual(pack["programme"]["mode"], "Indoor contingency" if indoor else "Base proposed plan")
                self.assertEqual(pack["budget"]["scenario"], "Indoor weather contingency" if indoor else "Base proposed plan")
                self.assertEqual(sum(item["amountCents"] for item in pack["budget"]["items"]), pack["goal"]["budgetCents"])
                self.assertIsNone(pack["venues"]["selected"])
                self.assertEqual(len(pack["venues"]["options"]), 1)
                self.assertEqual(any(event["status"] == "replan" for event in pack["metrics"]["trace"]), indoor)

    def test_basketball_weather_updates_preserve_sport_details_and_original_pack(self):
        prompt = "Plan a 5v5 basketball tournament with 8 teams for 120 participants between 2027-04-03 and 2027-04-18 with RM3333.33"
        pack = self.run_pack(prompt)
        original = copy.deepcopy(pack)
        day = pack["dateDecision"]["chosen"]["date"]
        for probability, available, indoor in ((.2, True, False), (.8, True, True), (.1, False, True)):
            with self.subTest(probability=probability, available=available), patch.object(pipeline, "load_research") as research, patch.object(pipeline, "date_weather") as forecast, patch.object(pipeline, "calendar_context") as calendar:
                updated = pipeline.apply_weather_update(pack, {"date": day, "probability": probability, "available": available, "mode": "forecast" if available else "unavailable"})
                research.assert_not_called()
                forecast.assert_not_called()
                calendar.assert_not_called()
                self.assertEqual(pack, original)
                self.assertEqual(updated["goal"], original["goal"])
                self.assertEqual(updated["goal"]["sportsDetails"]["format"], "5v5")
                self.assertEqual(updated["goal"]["sportsDetails"]["teamCount"], 8)
                self.assert_basketball_operations(updated)
                self.assertEqual(updated["weather"]["indoorRequired"], indoor)
                expected_probability = probability if available else None
                self.assertEqual(updated["weather"]["probability"], expected_probability)
                self.assertEqual(updated["dateDecision"]["chosen"]["weather"]["probability"], expected_probability)
                self.assertEqual(updated["programme"]["mode"], "Indoor contingency" if indoor else "Base proposed plan")
                self.assertEqual(updated["budget"]["scenario"], "Indoor weather contingency" if indoor else "Base proposed plan")
                self.assertEqual(sum(item["amountCents"] for item in updated["budget"]["items"]), 333333)
                self.assertGreaterEqual(updated["budget"]["contingencyCents"] * 10, updated["budget"]["totalCents"])
                self.assertNotRegex(json.dumps(updated["risks"]).lower(), r"acoustic|sound[ -]?check|performances?|performers?")
                self.assertFalse(updated["people"]["bookingConfirmed"])
                self.assertIsNone(updated["venues"]["selected"])

    def test_activity_intent_validator_rejects_mismatched_programme_or_promo(self):
        for prompt, expected_variant in (("basketball competition", "basketball"), ("football tournament", "sports"), ("chess tournament", "general")):
            pack = self.run_pack(prompt)
            self.assertEqual(pack["goal"]["activityKind"], expected_variant)
            baseline = pipeline.validate_pack(pack)
            self.assertTrue(baseline["passed"])
            for section in ("programme", "promo"):
                for mismatched_variant in {"concert", "basketball", "sports", "general"} - {expected_variant}:
                    with self.subTest(prompt=prompt, section=section, variant=mismatched_variant):
                        mismatched = copy.deepcopy(pack)
                        mismatched[section]["variant"] = mismatched_variant
                        result = pipeline.validate_pack(mismatched)
                        self.assertFalse(result["passed"])
                        self.assertEqual({error["code"] for error in result["errors"]}, {"activity_intent"})
                        self.assertTrue(any(not check["passed"] for check in result["checks"]))
            self.assertEqual(pack["programme"]["variant"], expected_variant)
            self.assertEqual(pack["promo"]["variant"], expected_variant)

    def test_activity_intent_validation_does_not_reclassify_legacy_pack(self):
        pack = self.run_pack("Charity concert for animal welfare in March with RM5000")
        pack["goal"].pop("activityKind", None)
        original = copy.deepcopy(pack)
        result = pipeline.validate_pack(pack)
        self.assertTrue(result["passed"])
        self.assertNotIn("activity_intent", {error["code"] for error in result["errors"]})
        self.assertEqual(pack, original)


if __name__ == "__main__":
    unittest.main()
