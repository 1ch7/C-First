"""EventPilot's local, deterministic tool-driven specialist runtime (no LLM)."""
from __future__ import annotations

import calendar
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlparse

try:
    from src.weather import date_weather, calendar_context
except ImportError:
    def date_weather(day, location, emit=None):
        return {"date": day, "probability": None, "mode": "unavailable", "confidence": "unknown", "sources": [], "warning": "Weather module unavailable; no weather assertion made."}

    def calendar_context(year, month, emit=None):
        return {"holidays": [], "examStatus": "unknown", "sources": [], "warning": "Calendar module unavailable; holidays and exams unconfirmed."}

ROOT = Path(__file__).resolve().parents[1]
def _today():
    return datetime.now(timezone(timedelta(hours=8))).date()


ENGINE = "tool-driven agents; LLM unavailable (keyless activation dismissed)"
MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
OVERRIDE_FIELDS = {"eventType", "cause", "month", "year", "dateStart", "dateEnd", "budgetRM", "location", "campus", "attendance", "organiserFundsRM"}


def _url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.hostname) and not parsed.username


def _money(value, field="budgetRM"):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a nonnegative amount in RM.")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > Decimal("100000000"):
            raise ValueError(f"{field} must be finite and between 0 and RM100,000,000.")
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError):
        raise ValueError(f"{field} must be a valid amount in RM.") from None


def _integer(value, field, low, high):
    if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field} must be an integer between {low} and {high}.")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an integer between {low} and {high}.") from None
    if str(value).strip() not in (str(number), f"{number}.0") or not low <= number <= high:
        raise ValueError(f"{field} must be an integer between {low} and {high}.")
    return number


def _iso(value, field):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field} must be a valid ISO date (YYYY-MM-DD).") from None


def parse_goal(prompt, overrides=None):
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 12000:
        raise ValueError("Provide an event brief of 1 to 12,000 characters.")
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("overrides must be an object.")
    overrides = overrides or {}
    unknown = set(overrides) - OVERRIDE_FIELDS
    if unknown:
        raise ValueError("Unknown override fields: " + ", ".join(sorted(unknown)))
    text = prompt.strip()
    lower = text.lower()
    today = _today()
    assumptions = []

    def assume(field, value, reason):
        assumptions.append({"field": field, "value": value, "reason": reason, "editable": True, "explicit": True})
        return value

    event_type = next((kind for kind in ("charity concert", "charity gala", "fundraising concert", "concert", "gala", "fundraiser", "workshop", "bazaar", "showcase", "festival", "charity event") if kind in lower), None)
    if not event_type:
        event_type = assume("eventType", "charity concert", "No event type was specified; planning assumption, not a confirmed booking.")
    cause = None
    explicit_purpose = False
    for marker in (r"raising (?:money|funds) for|supporting|benefiting|benefitting|to support", r"for"):
        for match in re.finditer(r"(?=\b(?:" + marker + r")\s+([^.;\n]+))", text, re.I):
            candidate = re.split(r"\s+(?:with\b|in\b|at\b|on\b|during\b|budget\b|for\s+\d|supporting\b|benefiting\b|benefitting\b|to support\b)|,\s*(?:with|in|at|on|for)\b", match.group(1), maxsplit=1, flags=re.I)[0].strip(" ,")
            excluded = re.match(r"^(?:\d|RM(?=\s|\d|$)|(?:a |the )?budget\b|(?:a |the )?campus\b|(?:" + "|".join(MONTHS) + r")\b)", candidate, re.I)
            audience = re.fullmatch(r"(?:attendees|people|pax|guests|students|participants)", candidate, re.I)
            location_phrase = re.search(r"\b(?:campus|subang jaya|kuala lumpur|selangor|malaysia)\b", candidate, re.I)
            if candidate and not (excluded or audience or location_phrase):
                cause = candidate
                explicit_purpose = marker != "for"
                break
        if cause:
            break
    charity_purpose = bool(re.search(r"\b(?:charity|fundrais\w*|raising (?:money|funds)|donations?|beneficiar\w*)\b", lower)) or explicit_purpose
    if not cause:
        if charity_purpose:
            cause = assume("cause", "a student-selected charity (beneficiary unconfirmed)", "No beneficiary or cause was named; organiser must confirm before outreach.")
        else:
            topic_match = re.search(r"([^.;\n]*?)\b(?:workshop|showcase|bazaar|concert|festival|gala)\b", text, re.I)
            topic = re.sub(r"^(?:(?:please|plan|organise|organize|create|host|a|an|the|student|campus)\s+)+", "", topic_match.group(1).strip(), flags=re.I).strip() if topic_match else ""
            purpose = f"{topic} learning and practice" if event_type == "workshop" and topic else "participant learning and practice" if event_type == "workshop" else f"{topic or 'student'} project presentation and peer exchange" if event_type == "showcase" else "student stall participation and community engagement" if event_type == "bazaar" else "student participation and shared activities"
            cause = assume("cause", purpose, "No separate purpose was specified; inferred editable planning objective from event type/topic, not a charity beneficiary or confirmed outcome.")
    month_match = re.search(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b(?:\s+(20\d{2}))?", lower)
    if month_match:
        month = MONTHS[month_match.group(1)]
        year = int(month_match.group(2)) if month_match.group(2) else today.year + (month <= today.month)
        if not month_match.group(2):
            assume("year", year, f"Month without year resolves to its next occurrence after the MYT planning date {today.isoformat()}.")
    else:
        month, year = 3, today.year + (3 <= today.month)
        assume("month", month, "No month specified; March is an editable planning assumption.")
        assume("year", year, f"MYT planning date is {today.isoformat()}; next March is {year}.")
    money_match = re.search(r"\bRM\s*([\d,]+(?:\.\d{1,2})?)\s*([kK])?", text, re.I)
    budget = float(Decimal(money_match.group(1).replace(",", "")) * (1000 if money_match.group(2) else 1)) if money_match else assume("budgetRM", 5000, "No budget specified; RM5,000 is an estimated spending ceiling, not a quotation.")
    attendance_match = re.search(r"\b(\d+)\s*(?:attendees|people|pax|guests|students|participants)\b", lower)
    attendance = int(attendance_match.group(1)) if attendance_match else assume("attendance", 100, "100 attendees is a planning assumption, not a confirmed audience.")
    campus_match = re.search(r"\b(?:at|on)\s+([^.;\n]+?\bcampus)\b", text, re.I)
    location_matches = re.finditer(r"\b(?:location\s*[:=]|located in|in)\s+([^.;\n]+?)(?=\s+(?:with|for|in|during|at|budget)\b|[.;\n]|$)", text, re.I)
    parsed_location = None
    for location_match in location_matches:
        candidate_location = location_match.group(1).strip(" ,")
        first_word = candidate_location.lower().split()[0] if candidate_location else ""
        if first_word not in MONTHS and not first_word.isdigit() and candidate_location:
            parsed_location = candidate_location
    if "taylor" in lower or "lakeside" in lower:
        campus = "Taylor's Lakeside Campus"
        location = parsed_location or "Subang Jaya, Selangor, Malaysia"
    else:
        campus = campus_match.group(1).strip() if campus_match else assume("campus", "Taylor's Lakeside Campus", "Campus was not specified; confirm the campus before seeking permission.")
        location = parsed_location or assume("location", "Subang Jaya, Selangor, Malaysia", "Location was not specified; location affects weather and campus relevance.")
    goal = {"eventType": event_type, "cause": cause, "month": month, "year": year, "budgetRM": budget, "location": location, "campus": campus, "attendance": attendance, "prompt": text, "scenarioDate": today.isoformat(), "charityPurpose": charity_purpose}
    if "year" not in overrides and "month" in overrides and not (month_match and month_match.group(2)):
        next_month = _integer(overrides["month"], "month", 1, 12)
        goal["year"] = today.year + (next_month <= today.month)
        for item in assumptions:
            if item["field"] == "year":
                item["value"] = goal["year"]
    goal.update(overrides)
    if re.search(r"\b(?:charity|fundrais\w*|donations?)\b", str(overrides.get("eventType", "")), re.I):
        goal["charityPurpose"] = True
    for field in ("eventType", "cause", "location", "campus"):
        if not isinstance(goal[field], str) or not goal[field].strip() or len(goal[field]) > 500:
            raise ValueError(f"{field} must be a nonempty string up to 500 characters.")
        goal[field] = goal[field].strip()
    goal["month"] = _integer(goal["month"], "month", 1, 12)
    goal["year"] = _integer(goal["year"], "year", today.year, 2100)
    goal["attendance"] = _integer(goal["attendance"], "attendance", 1, 100000)
    goal["budgetCents"] = _money(goal["budgetRM"])
    if goal["budgetCents"] < 100:
        raise ValueError("budgetRM must be at least RM1.00.")
    goal["budgetRM"] = goal["budgetCents"] / 100
    explicit_dates = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)
    use_prompt_dates = bool(explicit_dates) and not ({"month", "year"} & set(overrides))
    start = _iso(overrides["dateStart"], "dateStart") if "dateStart" in overrides else _iso(explicit_dates[0], "prompt dateStart") if use_prompt_dates else date(goal["year"], goal["month"], 1)
    end = _iso(overrides["dateEnd"], "dateEnd") if "dateEnd" in overrides else _iso(explicit_dates[1], "prompt dateEnd") if use_prompt_dates and len(explicit_dates) > 1 else start if use_prompt_dates else date(goal["year"], goal["month"], calendar.monthrange(goal["year"], goal["month"])[1])
    if use_prompt_dates:
        assumptions = [item for item in assumptions if item["field"] not in ("month", "year")]
    if start > end or end < today or (end - start).days > 366:
        raise ValueError("Date range must be ordered, future-facing, and at most 367 days.")
    goal.update(dateStart=start.isoformat(), dateEnd=end.isoformat(), month=start.month, year=start.year)
    funds = _money(overrides["organiserFundsRM"], "organiserFundsRM") if "organiserFundsRM" in overrides else goal["budgetCents"] * 70 // 100
    if funds > goal["budgetCents"]:
        raise ValueError("organiserFundsRM cannot exceed budgetRM.")
    goal["organiserFundsRM"] = funds / 100
    if "organiserFundsRM" not in overrides:
        assume("organiserFundsRM", funds / 100, "Assume organiser covers 70% of the ceiling; the remaining 30% is an unconfirmed funding gap.")
    assumptions = [item for item in assumptions if item["field"] not in overrides]
    for field, value in overrides.items():
        assumptions.append({"field": field, "value": value, "reason": "Explicit organiser override; a plan input, not external confirmation.", "editable": True, "explicit": True, "overridden": True})
    goal["attendanceAssumed"] = attendance_match is None and "attendance" not in overrides
    return goal, assumptions


class Trace:
    def __init__(self, emit):
        self.emit_callback = emit
        self.events = []
        self.lock = threading.RLock()
        self.started = time.perf_counter()
        self.tool_calls = 0

    def emit(self, agent, status, tool, message, data=None):
        with self.lock:
            event = {"agent": agent, "status": status, "tool": tool, "message": message, "data": data, "timestamp": datetime.now().isoformat(timespec="milliseconds")}
            self.events.append(event)
            if status in ("tool_call", "running"):
                self.tool_calls += 1
            if self.emit_callback:
                self.emit_callback(agent, status, tool, message, data)

    def actor(self, agent, tool, operation, *args):
        self.emit(agent, "running", tool, "Executing specialist tool; no language model or simulated progress.")
        result = operation(*args)
        self.emit(agent, "completed", tool, "Tool result produced.", {"resultType": type(result).__name__})
        return result


def load_research():
    path = ROOT / "data" / "research.json"
    try:
        with path.open(encoding="utf-8") as handle:
            content = json.load(handle)
        if not isinstance(content, dict):
            raise ValueError("Research data must be an object.")
        return content
    except (OSError, ValueError) as exc:
        return {"sponsors": [], "campus": {"venues": [], "calendarSources": []}, "warnings": [f"Research unavailable: {exc}; no sponsor contacts or venues invented."]}


def _probability(weather):
    if weather.get("available") is False or weather.get("mode") == "unavailable":
        return None
    key = next((key for key in ("probability", "rainProbability", "rain_probability", "rainProbabilityMax", "precipitationProbability", "wetProbability") if weather.get(key) is not None), None)
    value = weather.get(key) if key else None
    percentage = key == "rainProbability"
    if isinstance(value, (int, float)) and not isinstance(value, bool) and percentage and 0 <= value <= 100:
        return float(value) / 100
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
        return float(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 1 < value <= 100:
        return float(value) / 100
    return None


def _safe_weather(day, location, trace):
    trace.emit("Date Scout", "tool_call", "date_weather", f"Checking real weather evidence for {day} in {location}.", {"date": day})
    try:
        result = date_weather(day, location, emit=trace.emit)
        if not isinstance(result, dict):
            raise ValueError("Weather result is not an object.")
    except Exception as exc:
        result = {"date": day, "mode": "unavailable", "probability": None, "confidence": "unknown", "sources": [], "warning": f"Weather check failed: {type(exc).__name__}; no forecast assumed."}
    result = dict(result)
    result.setdefault("date", day)
    result["probability"] = _probability(result)
    return result


def _calendar(year, month, trace):
    trace.emit("Date Scout", "tool_call", "calendar_context", f"Checking calendar evidence for {year}-{month:02d}.")
    try:
        result = calendar_context(year, month, emit=trace.emit)
        return result if isinstance(result, dict) else {"holidays": [], "warning": "Calendar returned invalid data; clashes unknown."}
    except Exception as exc:
        return {"holidays": [], "examStatus": "unknown", "sources": [], "warning": f"Calendar check failed: {type(exc).__name__}; clashes unknown."}


def scout_dates(goal, research, trace):
    today = _iso(goal["scenarioDate"], "scenarioDate")
    start, end = _iso(goal["dateStart"], "dateStart"), _iso(goal["dateEnd"], "dateEnd")
    weekends = [start + timedelta(days=i) for i in range((end - start).days + 1) if (start + timedelta(days=i)).weekday() >= 5 and start + timedelta(days=i) >= today]
    indices = sorted({round(i * (len(weekends) - 1) / 4) for i in range(5)}) if weekends else []
    selected = [weekends[i].isoformat() for i in indices]
    months = sorted({(date.fromisoformat(day).year, date.fromisoformat(day).month) for day in selected})
    contexts = [_calendar(year, month, trace) for year, month in months]
    holidays, known_exams, fasting_ranges = {}, set(), []
    for context in contexts + [research]:
        for window in context.get("ramadanRanges", []):
            if isinstance(window, dict) and _url(window.get("source")) and window.get("start") and window.get("end") and window not in fasting_ranges:
                fasting_ranges.append(window)
        entries = context.get("holidays", [])
        if isinstance(entries, dict):
            entries = [{"date": key, "name": value} for key, value in entries.items()]
        for item in entries if isinstance(entries, list) else []:
            if isinstance(item, dict) and _url(item.get("source") or item.get("url")):
                for key in ("date", "observedDate"):
                    if item.get(key):
                        holidays[str(item[key])] = item
        for exam in context.get("exams", []):
            if isinstance(exam, dict) and _url(exam.get("source")) and exam.get("date"):
                known_exams.add(exam["date"])
    weather_by_day = {}
    with ThreadPoolExecutor(max_workers=max(1, len(selected)), thread_name_prefix="date-weather") as pool:
        futures = {pool.submit(_safe_weather, day, goal["location"], trace): day for day in selected}
        for future in as_completed(futures):
            weather_by_day[futures[future]] = future.result()
    candidates = []
    weights = {"weather": 45, "holiday": 25, "weekend": 20, "leadTime": 10, "examUnknownPenalty": 5, "fastingOverlapPenalty": 10}
    for day in selected:
        weather = weather_by_day[day]
        probability = weather["probability"]
        confidence = weather.get("confidence", "unknown")
        sample_count = weather.get("sampleCount")
        if weather.get("available") is False or probability is None:
            weather_confidence = "unknown"
            confidence_penalty = 8
        elif "historical" in str(weather.get("mode", "")).lower() or "climatology" in str(weather.get("mode", "")).lower():
            weather_confidence = "low—historical frequency is not an event-date forecast"
            confidence_penalty = max(0, 10 - sample_count) if isinstance(sample_count, int) else 5
        else:
            weather_confidence = str(confidence)
            confidence_penalty = 2 if confidence == "low" else 0
        holiday = holidays.get(day)
        exam = day in known_exams
        fasting = [window for window in fasting_ranges if window["start"] <= day <= window["end"]]
        score = round((1 - probability if probability is not None else 0.35) * 45 + (0 if holiday else 25) + 20 + min(10, (date.fromisoformat(day) - today).days / 7) - 5 - (10 if fasting else 0) - confidence_penalty, 2)
        reasons = ["Weekend candidate.", "Campus exam timetable is unconfirmed; do not interpret as clear."]
        reasons.append("Cited holiday clash; excluded." if holiday else "No cited holiday clash found; holiday completeness remains unconfirmed.")
        reasons.append("Weather evidence unavailable; conservative indoor plan required." if probability is None else f"Weather rain-risk estimate {probability:.0%}; mode: {weather.get('mode', 'evidence')}.")
        if exam:
            reasons.append("Cited examination clash; excluded.")
        if fasting:
            reasons.append("Cited provisional fasting-period overlap; avoid food-centred or performance scheduling without local approval.")
        candidates.append({"date": day, "weekday": date.fromisoformat(day).strftime("%A"), "score": score, "weather": weather, "weatherConfidence": weather_confidence, "holidayClash": holiday, "examStatus": "known clash" if exam else "unknown", "fastingContext": fasting, "blocked": bool(holiday or exam), "reasons": reasons})
    eligible = sorted((item for item in candidates if not item["blocked"]), key=lambda item: (-item["score"], item["date"]))
    chosen = eligible[0] if eligible else None
    trace.emit("Date Scout", "tool_result", "weighted_date_rank", "Ranked real weather/calendar tool results; known clashes excluded.", {"chosen": chosen["date"] if chosen else None, "candidateCount": len(candidates)})
    return {"candidates": candidates, "chosen": chosen, "backups": eligible[1:3], "weights": weights, "calendar": contexts, "status": "Proposed—exam and venue approval required" if chosen else "Blocked—no eligible weekend", "assumptions": ["Holiday calendars may be incomplete.", "Campus examination timetable is unknown."]}


def build_budget(goal, indoor=False):
    cents = goal["budgetCents"]
    allocations = [("Venue / indoor cover", 22 if indoor else 18), ("AV and production", 14 if indoor else 15), ("Refreshments", 20), ("Promotion and print", 6 if indoor else 8), ("Talent and MC", 9 if indoor else 10), ("Operations and first aid", 7), ("Accessibility and charity logistics", 10), ("Contingency reserve", 12)]
    contingency = (cents * 12 + 99) // 100
    remaining = cents - contingency
    non_reserve = allocations[:-1]
    amounts = [remaining * percent // 88 for _, percent in non_reserve]
    amounts[0] += remaining - sum(amounts)
    amounts.append(contingency)
    items = [{"category": name, "amountRM": amount / 100, "amountCents": amount, "estimated": True, "status": "Estimated allocation—not a vendor quote", "owner": "Finance Lead"} for (name, _), amount in zip(allocations, amounts)]
    funds = _money(goal["organiserFundsRM"], "organiserFundsRM")
    gap = max(0, cents - funds)
    return {"items": items, "total": cents / 100, "limit": cents / 100, "totalCents": cents, "limitCents": cents, "contingency": contingency / 100, "contingencyCents": contingency, "contingencyPercent": round(contingency / cents * 100, 2), "gap": gap / 100, "gapCents": gap, "organiserFunds": funds / 100, "organiserFundsCents": funds, "fundingStatus": "Organiser funds assumed; sponsor commitments not received", "pricingBasis": "All amounts are estimated allocations, not researched quotes or contracted prices.", "scenario": "Indoor weather contingency" if indoor else "Base proposed plan", "sponsorAccounting": "Prospect asks are hypothetical alternatives, not additive promised revenue."}


def build_venues(goal, research):
    options = []
    relevant = "taylor" in goal["campus"].lower() or "lakeside" in goal["campus"].lower()
    for item in research.get("campus", {}).get("venues", []) if relevant else []:
        if not isinstance(item, dict) or not item.get("name") or not _url(item.get("source") or item.get("url")):
            continue
        capacity = item.get("capacity")
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            capacity = None
        options.append({"name": item["name"], "source": item.get("source") or item.get("url"), "capacity": capacity, "notes": item.get("notes", ""), "indoor": item.get("indoor") if isinstance(item.get("indoor"), bool) else None, "approvalStatus": "Unconfirmed—campus approval required", "approvalLeadTime": "Allow 2–4 weeks (planning estimate, not campus policy)", "capacityStatus": "Cited capacity; confirm event setup" if capacity else "Unknown—request written capacity and safety confirmation"})
    suitable = [item for item in options if item["capacity"] is None or item["capacity"] >= goal["attendance"]]
    selected = next((item for item in suitable if item["indoor"] is True), suitable[0] if suitable else None)
    return {"options": options, "selected": selected, "approvalStatus": "Unconfirmed", "requestedMode": "Indoor-ready option; room and cover not yet confirmed", "approvalChecklist": ["Written permission and exact date", "Certified capacity and fire exits", "AV, power and indoor cover", "Charity collection consent" if goal.get("charityPurpose", True) else "Activity registration and materials permission", "Accessibility and emergency arrangements"], "studentAffairsGuidance": research.get("campus", {}).get("studentAffairsGuidance", {}) if relevant else {}, "calendarSources": research.get("campus", {}).get("calendarSources", []) if relevant else [], "academicCalendar": research.get("campus", {}).get("academicCalendar", {}) if relevant else {}, "warning": None if options else "No cited venues for this campus; ask organiser for verified campus options."}


def build_people(goal, dates, roster):
    roster = [] if roster is None else roster
    demo = isinstance(roster, list) and any(isinstance(item, dict) and item.get("demo") is True for item in roster)
    if not isinstance(roster, list) or len(roster) > 100:
        raise ValueError("roster must be a list with at most 100 entries.")
    members = []
    chosen = dates["chosen"]["date"] if dates["chosen"] else None
    for item in roster:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError("Each roster entry needs a nonempty name.")
        free = item.get("freeDates", [])
        if not isinstance(free, list):
            raise ValueError("Roster freeDates must be an ISO-date list.")
        free = [_iso(day, "freeDates").isoformat() for day in free]
        email = item.get("email")
        if email is not None and (not isinstance(email, str) or not EMAIL.fullmatch(email)):
            raise ValueError("Roster contact email is invalid.")
        score = _integer(item.get("experienceScore", 1), "experienceScore", 1, 5)
        member_demo = item.get("demo") is True
        members.append({"name": item["name"].strip()[:200], "role": str(item.get("role", "MC"))[:100], "experienceScore": score, "freeDates": free, "demo": member_demo, "email": email if not member_demo else None, "contactSource": "User-supplied roster" if email and not member_demo else None, "availableOnProposedDate": chosen in free if chosen and free else None, "availabilityStatus": "Demo-only availability, not real confirmation" if member_demo else "User-listed availability; booking unconfirmed" if chosen in free else "Unknown or unavailable"})
    candidates = sorted((member for member in members if "mc" in member["role"].lower() and member["availableOnProposedDate"] is not False), key=lambda member: (-int(member["availableOnProposedDate"] is True), -member["experienceScore"], member["name"]))
    return {"roster": members, "demo": demo or any(member["demo"] for member in members), "topMC": candidates[0] if candidates else None, "backupMC": candidates[1] if len(candidates) > 1 else None, "availabilityStatus": "Demo only—real MC and performers must be contacted" if demo else "Unconfirmed—user roster is not a signed booking", "selectionRule": "User-listed date availability first, then organiser-provided experience score; demo scores are fictional.", "bookingConfirmed": False}


def build_sponsors(goal, budget, research):
    prospects = []
    for item in research.get("sponsors", []):
        if not isinstance(item, dict) or not item.get("name") or not _url(item.get("url")):
            continue
        source = item.get("emailSource")
        email = item.get("email")
        verified = isinstance(email, str) and bool(EMAIL.fullmatch(email)) and _url(source) and item.get("countsTowardVerifiedSuitableEmailMinimum") is not False
        prospects.append({"name": item["name"], "url": item["url"], "email": email if verified else None, "emailSource": source if verified else None, "contactType": item.get("contactType", "Official website; direct email unverified"), "category": item.get("category", "Prospect"), "fit": item.get("fit", "Proposed fit; sponsorship interest unknown"), "fitStatus": "Planner assessment—not expressed sponsor interest", "contactVerified": verified, "status": "Prospect only—no commitment", "promisedRM": 0, "fitSource": item.get("fitSource") if _url(item.get("fitSource")) else item["url"], "suggestedHypotheticalAsk": item.get("suggestedHypotheticalAsk"), "constraints": item.get("constraints", []), "priority": item.get("priority", "Unranked prospect"), "contactUrl": item.get("contactUrl") if _url(item.get("contactUrl")) else item["url"], "appropriatePartnershipContact": item.get("countsTowardVerifiedSuitableEmailMinimum", verified), "countsTowardVerifiedSuitableEmailMinimum": item.get("countsTowardVerifiedSuitableEmailMinimum", verified), "emailVerificationNote": item.get("verificationMethod", "Source URL supplied in researched record")})
    gap = budget["gapCents"]
    count = min(5, len(prospects))
    for i, item in enumerate(prospects):
        ask = gap // count + (1 if i < gap % count else 0) if count and i < count else gap // max(count, 1)
        item.update(askRM=ask / 100, askCents=ask, askStatus="Hypothetical proposed ask; not promised revenue", tiers=[{"name": "Supporting", "askRM": (gap * 25 // 100) / 100, "benefit": "Proposed acknowledgement; campus and charity approval required"}, {"name": "Partner", "askRM": (gap * 50 // 100) / 100, "benefit": "Proposed poster/logo acknowledgement, subject to approval"}, {"name": "Lead supporter", "askRM": gap / 100, "benefit": "Proposed lead acknowledgement, not exclusivity or guaranteed reach"}], accounting="One exploratory portfolio or alternative tiers; not additive committed funds")
    return prospects


def build_programme(goal, dates, indoor=False):
    chosen = dates["chosen"]["date"] if dates["chosen"] else None
    schedule = [("17:00", "Arrival, accessibility and safety briefing", "Operations Lead", 30), ("17:30", "Doors and check-in", "Front-of-house Lead", 30), ("18:00", "MC welcome, cause and donation transparency", "MC / Charity Liaison", 15), ("18:15", "Student performance set one", "Talent Lead", 40), ("18:55", "Cause talk and opt-in donation break", "Charity Liaison", 20), ("19:15", "Student performance set two", "Talent Lead", 40), ("19:55", "Impact target recap and sponsor acknowledgement", "MC / Finance Lead", 15), ("20:10", "Close, cash reconciliation and safe exit", "Operations / Finance Leads", 20)]
    event_type = goal["eventType"].lower()
    variant = next((kind for kind in ("workshop", "bazaar", "showcase") if kind in event_type), "concert")
    if variant == "workshop":
        schedule = [("09:00", "Facilitator setup, materials and access checks", "Workshop / Operations Leads", 30), ("09:30", "Participant check-in and learning-goal briefing", "Front-of-house Lead", 30), ("10:00", "Cause introduction and facilitator demonstration", "Facilitator / Charity Liaison", 30), ("10:30", "Guided hands-on practice in small groups", "Workshop Lead", 60), ("11:30", "Break and opt-in cause discussion", "Operations / Charity Leads", 20), ("11:50", "Participant project practice and feedback", "Facilitator Lead", 45), ("12:35", "Learning reflection and approved sponsor thanks", "Workshop Lead", 15), ("12:50", "Materials return, reconciliation and safe departure", "Operations / Finance Leads", 20)]
    elif variant == "bazaar":
        schedule = [("09:00", "Stall setup, food permissions and exit checks", "Stall / Operations Leads", 30), ("09:30", "Vendor briefing, allergen signs and cash controls", "Vendor / Finance Leads", 30), ("10:00", "Bazaar opens; visitor check-in and cause introduction", "Front-of-house / Charity Leads", 15), ("10:15", "Approved student stalls and browsing session one", "Stall Lead", 90), ("11:45", "Donation transparency and vendor welfare checks", "Charity / Operations Leads", 30), ("12:15", "Approved stall browsing session two", "Stall Lead", 90), ("13:45", "Final purchases and approved sponsor acknowledgement", "Stall / Finance Leads", 15), ("14:00", "Close stalls, reconcile funds and clean accessible routes", "Operations / Finance Leads", 30)]
    elif variant == "showcase":
        schedule = [("13:00", "Exhibit installation, AV and access checks", "Exhibit / Operations Leads", 30), ("13:30", "Visitor check-in and exhibitor briefing", "Front-of-house Lead", 30), ("14:00", "Showcase welcome and cause introduction", "Host / Charity Liaison", 15), ("14:15", "Student project demonstrations and exhibit walk", "Exhibit Lead", 45), ("15:00", "Audience questions and opt-in cause discussion", "Host / Charity Liaison", 20), ("15:20", "Student project presentations and peer feedback", "Exhibit Lead", 45), ("16:05", "Reflection and approved sponsor acknowledgement", "Host / Finance Lead", 15), ("16:20", "Exhibit pack-down, reconciliation and safe departure", "Operations / Finance Leads", 20)]
    if not goal.get("charityPurpose", True):
        if variant == "workshop":
            schedule[2] = ("10:00", f"Learning objectives for {goal['cause']} and facilitator demonstration", "Facilitator Lead", 30)
            schedule[4] = ("11:30", "Participant break and peer learning discussion", "Workshop / Operations Leads", 20)
        elif variant == "showcase":
            schedule[2] = ("14:00", "Showcase welcome, exhibit objectives and visitor guidance", "Host / Exhibit Lead", 15)
            schedule[4] = ("15:00", "Audience questions and project discussion", "Host / Exhibit Lead", 20)
        elif variant == "bazaar":
            schedule[2] = ("10:00", "Bazaar opens; visitor registration and stall guidance", "Front-of-house / Stall Leads", 15)
            schedule[4] = ("11:45", "Vendor welfare, payments and visitor feedback checks", "Stall / Operations Leads", 30)
        else:
            schedule[2] = ("18:00", "Host welcome and event introduction", "Host / Event Lead", 15)
            schedule[4] = ("18:55", "Audience break and activity discussion", "Operations Lead", 20)
    if indoor:
        start = datetime.strptime(schedule[0][0], "%H:%M") - timedelta(minutes=30)
        setup = {"concert": "Indoor AV check, protected cable routing and rain-safe arrivals", "workshop": "Indoor materials setup, dry workstations and rain-safe arrivals", "bazaar": "Indoor stall layout, covered deliveries and protected food storage", "showcase": "Indoor exhibit installation, protected displays and rain-safe arrivals"}[variant]
        schedule[0] = (start.strftime("%H:%M"), setup, "Operations / Activity Leads", 60)
        schedule[1] = (schedule[1][0], "Covered indoor check-in and activity briefing; keep fire exits clear", "Front-of-house Lead", 30)
    run = [{"time": at, "activity": activity, "owner": owner, "durationMinutes": duration, "mode": "Indoor contingency" if indoor else "Proposed indoor-ready programme", "status": "Proposed—not booked"} for at, activity, owner, duration in schedule]
    milestones = [(56, "T-8 weeks", "Confirm beneficiary, exam dates, campus permission and provisional indoor room", "Event Lead"), (49, "T-7 weeks", "Send reviewed sponsor/MC drafts; obtain written capacity", "Partnerships / Talent Leads"), (42, "T-6 weeks", "Obtain vendor quotes and cost-check all commitments", "Finance Lead"), (35, "T-5 weeks", "Approve charity messaging and promotional permissions", "Charity / Promo Leads"), (28, "T-4 weeks", "Confirm acts and MC; secure backup room and AV", "Talent / Venue Leads"), (21, "T-3 weeks", "Check RSVPs, accessibility requests and volunteer rota", "Operations Lead"), (14, "T-2 weeks", "Recheck weather, exams, approvals and funding; activate Plan B if needed", "Risk Lead"), (7, "T-1 week", "Confirm short-range forecast, final attendance and vendor amounts", "Event Lead"), (1, "T-1 day", "Final weather and safety go/no-go, cash controls and rehearsal", "Operations / Finance Leads"), (0, "Event day", "Execute run sheet, reconcile donations and log incidents", "Event Lead")]
    if not goal.get("charityPurpose", True):
        activity_team = {"workshop": "Facilitator / Workshop Leads", "showcase": "Exhibit / Host Leads", "bazaar": "Stall / Vendor Leads", "concert": "Activity / Host Leads"}[variant]
        preparation = {"workshop": "Confirm facilitators, learning objectives, session materials and practice exercises", "showcase": "Confirm exhibitors, presentation briefs and display setup", "bazaar": "Confirm vendors, stall layouts and permitted products", "concert": "Confirm hosts and activity programme"}[variant]
        milestones[0] = (56, "T-8 weeks", "Confirm activity objectives, exam dates, campus permission and provisional indoor room", "Event Lead")
        milestones[1] = (49, "T-7 weeks", "Review sponsor and activity-team enquiries; obtain written capacity", f"Partnerships / {activity_team}")
        milestones[3] = (35, "T-5 weeks", "Approve session description, participant registration and promotional permissions", "Activity / Promo Leads")
        milestones[4] = (28, "T-4 weeks", preparation + "; secure backup room and equipment", activity_team)
        milestones[8] = (1, "T-1 day", "Final weather and safety go/no-go, registration checks and session preparation", "Operations / Activity Leads")
        milestones[9] = (0, "Event day", "Execute activity run sheet, capture participant feedback, reconcile costs and log incidents", "Event Lead")
    countdown = [{"offsetDays": -days, "label": label, "date": (date.fromisoformat(chosen) - timedelta(days=days)).isoformat() if chosen else None, "action": action, "owner": owner, "status": "Pending"} for days, label, action, owner in milestones]
    end = datetime.strptime(schedule[-1][0], "%H:%M") + timedelta(minutes=schedule[-1][3])
    return {"runOfShow": run, "countdown": countdown, "mode": "Indoor contingency" if indoor else "Base proposed plan", "variant": variant, "startTime": run[0]["time"], "endTime": end.strftime("%H:%M"), "timezone": "Asia/Kuala_Lumpur", "date": chosen}


def build_risks(goal, weather):
    probability = _probability(weather)
    rows = [("Rain / thunderstorms", 4 if probability is None or probability > .4 else 3, 4, "Book an approved indoor room; weather check at T-14/T-7/T-1", "Rain-risk estimate >40%, thunderstorm alert, or missing weather evidence", "Move check-in and performances indoors; reduce exposed setup", "Risk Lead"), ("Campus exam or calendar clash", 3, 5, "Request written exam timetable and campus calendar sign-off", "Exam date unknown at approval deadline or a confirmed clash", "Move to ranked backup date; re-run all specialist tools", "Event Lead"), ("Venue / safety approval withheld", 3, 5, "Obtain written capacity, permission, safety and AV approvals", "No written approval by T-4 weeks", "Use approved alternative room or postpone; do not overfill", "Venue Lead"), ("Sponsor funding shortfall", 4, 4, "Track only confirmed funds; keep 12% contingency protected", "Unconfirmed gap remains at T-2 weeks", "Reduce nonessential spend or postpone; never assume prospect revenue", "Finance Lead"), ("MC / performer cancellation", 3, 3, "Get signed availability; contact backup role without claiming booking", "Talent unconfirmed at T-2 weeks or cancellation received", "Use approved student host and shorter acoustic programme", "Talent Lead"), ("Attendance below planning target", 3, 3, "Use opt-in RSVP tracking and approved student society promotion", "RSVPs below 60% of planning target at T-1 week (planning rule)", "Reduce refreshments and room footprint after cost approval", "Promo Lead"), ("Donation handling / beneficiary uncertainty", 3, 5, "Confirm beneficiary consent, collection permissions and dual-control ledger", "No verified beneficiary or collection approval before publishing", "Pause collection; publish only confirmed charity-approved wording", "Charity / Finance Leads"), ("Safety, access or technical failure", 3, 5, "Check exits, accessible routes, first aid, AV and protected cables", "Failed safety/AV check or emergency during event", "Stop affected activity, follow campus emergency instructions and evacuate if required", "Operations Lead")]
    if not goal.get("charityPurpose", True):
        rows[0] = ("Rain / thunderstorms", rows[0][1], 4, "Confirm an approved indoor activity room and weather rechecks", "Rain-risk >40%, alert, or missing evidence", "Move registration and activity sessions indoors; protect materials", "Risk Lead")
        rows[4] = ("Activity-team cancellation", 3, 3, "Confirm facilitators, exhibitors or vendors and a backup activity lead", "Activity team unconfirmed at T-2 weeks or cancellation received", "Use an approved backup facilitator or simplify the activity scope", "Activity Lead")
        rows[6] = ("Session objectives or registration uncertainty", 3, 4, "Confirm activity objectives, approved registration and session materials", "Learning objectives, required materials or registrations unconfirmed at T-1 week", "Simplify the session and disclose adjusted objectives before participation", "Activity / Operations Leads")
    register = [{"risk": risk, "likelihood": likelihood, "impact": impact, "L": likelihood, "I": impact, "score": likelihood * impact, "mitigation": mitigation, "trigger": trigger, "contingency": contingency, "owner": owner, "basis": "Planner risk assessment; ordinal 1–5, not empirical probability"} for risk, likelihood, impact, mitigation, trigger, contingency, owner in rows]
    plan_b = [{"name": "Wet-weather indoor shift", "trigger": "Rain-risk >40%, alert, or evidence unavailable", "action": "Request approved indoor room, cover arrivals, bring soundcheck forward, rebalance allocations within ceiling", "owner": "Risk / Venue Leads", "status": "Proposed—room approval required"}, {"name": "Date / permission switch", "trigger": "Known exam/holiday clash or venue refused", "action": "Use next eligible ranked date and rerun weather, budget, talent and drafts; no date is confirmed automatically", "owner": "Event Lead", "status": "Conditional"}, {"name": "Funding / talent scale-down", "trigger": "Funding gap unresolved or principal act unavailable", "action": "Shorter approved acoustic show, lower nonessential spend, backup MC; preserve contingency and charity controls", "owner": "Finance / Talent Leads", "status": "Conditional"}]
    if not goal.get("charityPurpose", True):
        plan_b[0]["action"] = "Request approved indoor room, cover registration, bring materials/setup checks forward and rebalance within ceiling"
        plan_b[1]["action"] = "Use next eligible ranked date and rerun weather, budget, activity-team availability and drafts; no automatic booking"
        plan_b[2].update(name="Funding / activity scale-down", trigger="Funding gap unresolved or facilitator/exhibitor unavailable", action="Simplify approved learning or exhibit activities, reduce nonessential spending and use an approved backup activity lead; preserve reserve", owner="Finance / Activity Leads")
    return {"register": register, "planB": plan_b, "scale": "L and I use 1 (low) to 5 (high); score = L × I", "weatherThreshold": .4}


def build_drafts(goal, dates, venues, people, sponsors):
    today = _iso(goal["scenarioDate"], "scenarioDate")
    proposed = dates["chosen"]["date"] if dates["chosen"] else "date pending (no eligible weekend confirmed)"
    selected = venues.get("selected")
    venue = selected["name"] if selected else "campus-approved venue to be confirmed"
    count_phrase = f"{goal['attendance']} attendees ({'planning assumption; not confirmed attendance' if goal['attendanceAssumed'] else 'organiser target; not confirmed attendance'})"
    reply_by = (date.fromisoformat(proposed) - timedelta(days=35)).isoformat() if dates["chosen"] else (today + timedelta(days=14)).isoformat()
    drafts, followups = [], []
    charity = goal.get("charityPurpose", True)
    impact_target = "The proposed impact target is to direct net proceeds to the beneficiary after documented costs; the beneficiary, collection permission and amount raised are not yet confirmed." if charity else f"The proposed activity objective is {goal['cause']}; participant learning and engagement are targets, not confirmed outcomes. No charity beneficiary or donation collection is proposed in this brief."
    approval_details = "approved beneficiary details" if charity else "approved activity objectives and participant arrangements"
    partnership_kind = "charity" if charity else "activity"
    for sponsor in sponsors:
        in_kind = sponsor.get("suggestedHypotheticalAsk") or "an itemised in-kind alternative relevant to your team, subject to approval"
        routing = "Please advise whether this belongs with your partnerships team; this published address is not a verified dedicated sponsorship route. " if not sponsor.get("appropriatePartnershipContact", True) else ""
        conditions = "; ".join(str(item) for item in sponsor.get("constraints", []))
        body = (f"Dear {sponsor['name']} team,\n\nWe are preparing a proposed {goal['eventType']} for {goal['cause']} at {goal['campus']}. "
                f"Proposed date: {proposed}. Proposed venue: {venue} (approval and capacity unconfirmed). Our target is {count_phrase}. "
                f"{impact_target}\n\n"
                f"{routing}Would you consider a hypothetical contribution of up to RM{sponsor['askRM']:.2f} toward our unconfirmed funding gap, without assuming that your programme offers cash? A researched, proposed in-kind discussion could be: {in_kind} Published constraints to review: {conditions or 'No specific public constraints established; confirm programme terms directly'}. Alternative proposed tiers are "
                + ", ".join(f"{tier['name']}: RM{tier['askRM']:.2f}" for tier in sponsor["tiers"])
                + ". These are alternatives, not combined commitments. Any acknowledgement, logo use or student reach requires approval; no reach, tax benefit or exclusivity is guaranteed.\n\n"
                f"Please reply by {reply_by} if the proposal is relevant, or direct us to the appropriate partnerships channel. We will share {approval_details} and final venue confirmation before seeking a commitment.\n\nEvent organising team\nDraft created by EventPilot; not sent.")
        entry = {"id": f"sponsor-{len(drafts)+1}", "recipient": sponsor["name"], "to": sponsor["email"], "contactType": sponsor["contactType"], "contactUrl": sponsor.get("contactUrl", sponsor["url"]), "subject": f"EventPilot | Proposed {goal['eventType']} partnership — {proposed}", "body": body, "status": "Draft—unsent", "source": sponsor["emailSource"] or sponsor["url"], "sourceVerified": sponsor["contactVerified"], "replyBy": reply_by, "askRM": sponsor["askRM"], "proposedDate": proposed, "proposedVenue": venue, "attendance": goal["attendance"], "cause": goal["cause"], "needsReview": True}
        drafts.append(entry)
        for offset, label in ((7, "First follow-up"), (14, "Final polite follow-up")):
            followups.append({"recipient": sponsor["name"], "to": sponsor["email"], "subject": f"EventPilot | {label}: proposed student {partnership_kind} partnership", "body": f"Dear {sponsor['name']} team,\nFollowing our proposed {goal['eventType']} for {goal['cause']} on {proposed}, may we check whether this is relevant to your team? The venue and attendance remain unconfirmed. We would welcome advice on the right channel; no response will be treated as no commitment.\nThank you, event organising team.\nDraft only; not sent.", "status": "Draft—unsent", "label": label, "sendAfterDays": offset, "condition": "Only after initial draft is reviewed and actually sent; do not send if declined", "source": sponsor["emailSource"] or sponsor["url"]})
    mc = []
    for label, person in (("Preferred MC", people["topMC"]), ("Backup MC", people["backupMC"])):
        if person:
            mc.append({"recipient": person["name"], "to": person.get("email"), "subject": f"EventPilot | {label} availability request — {proposed}", "body": f"Hello {person['name']},\nWould you be interested and available to host a proposed {goal['eventType']} for {goal['cause']} on {proposed} at {venue}? We are planning for {count_phrase}. Date, venue, fee and booking remain unconfirmed. Please confirm availability and requirements by {reply_by}; this is an enquiry, not an appointment.\n{'This recipient is a fictional demonstration role; replace with a real consenting contact before outreach.' if person['demo'] else 'Contact was supplied by the organiser; review before sending.'}\nDraft only; not sent.", "status": "Draft—unsent", "label": label, "demo": person["demo"], "source": person.get("contactSource"), "replyBy": reply_by})
    return {"sponsorEmails": drafts, "followups": followups, "mc": mc, "sendStatus": "Nothing sent; no email or messaging service is called", "missingVerifiedEmailCount": sum(entry["to"] is None for entry in drafts)}


def build_promo(goal, dates, venues):
    day = dates["chosen"]["date"] if dates["chosen"] else "date to be confirmed"
    venue = venues["selected"]["name"] if venues["selected"] else "venue to be confirmed"
    notice = "Proposed event; date, venue and charity permission pending. RSVP details not yet published."
    variant = next((kind for kind in ("workshop", "bazaar", "showcase") if kind in goal["eventType"].lower()), "concert")
    headline, opener, participation = {"concert": ("Student music. Shared purpose.", "Music with a purpose", "Student voices"), "workshop": ("Learn together. Support a cause.", "Hands-on learning with a purpose", "Guided practice and shared learning"), "bazaar": ("Student stalls. Shared purpose.", "Browse approved student stalls for a cause", "Student makers and responsible stall browsing"), "showcase": ("Student projects. Shared purpose.", "Discover student projects for a cause", "Student demonstrations and peer inspiration")}[variant]
    captions = [f"{opener}: a proposed {goal['eventType']} supporting {goal['cause']}. Save the tentative date {day}; watch for approved details. {notice}", f"{participation}, shared purpose. Our planning target is {goal['attendance']} attendees—not confirmed attendance. Interested participants can contact the organising team once its approved contact is published. {notice}", f"Help shape a transparent charity event. Proposed location: {venue}, {goal['campus']}. Net-proceeds target and beneficiary will be disclosed after approval, not promised in advance. {notice}"]
    if not goal.get("charityPurpose", True):
        notice = "Proposed event; date, venue and campus activity permission pending. Registration details not yet published."
        if variant == "workshop":
            headline = "Learn together. Practise new skills."
        captions = [f"{participation}: a proposed {goal['eventType']} focused on {goal['cause']}. Tentative date {day}; learning and engagement are planning objectives, not guaranteed results. {notice}", f"Our organiser target is {goal['attendance']} participants—not confirmed attendance. Watch for approved registration and access details. {notice}", f"Join an approved student activity at {venue}, {goal['campus']}, once arrangements are confirmed. Session objectives and facilitator or exhibitor details will be published after review. {notice}"]
    return {"captions": captions, "variant": variant, "poster": {"headline": headline, "eventType": goal["eventType"], "cause": goal["cause"], "date": day, "venue": venue, "campus": goal["campus"], "cta": "Approved RSVP link to be added by organiser", "disclaimer": notice, "status": "Draft copy—not a published poster"}, "channels": ["Campus-approved society channels", "Organiser-approved student newsletter", "Opt-in social posts after consent"], "approvalChecklist": ["Beneficiary permission" if goal.get("charityPurpose", True) else "Activity objectives and participant registration approval", "Campus promotional permission", "No guaranteed funds or reach", "Only consenting images and verified organiser contact"], "calendar": [{"offsetDays": -21, "action": "Publish approved save-the-date"}, {"offsetDays": -14, "action": "Volunteer and RSVP reminder"}, {"offsetDays": -7, "action": "Confirmed access and indoor logistics"}, {"offsetDays": 1, "action": "Publish reconciled outcomes, not planning targets"}]}


def _draft_groups(drafts):
    if isinstance(drafts, dict):
        return drafts
    groups = {"sponsorEmails": [], "followups": [], "mc": []}
    for draft in drafts if isinstance(drafts, list) else []:
        key = {"sponsor": "sponsorEmails", "followup": "followups", "mc": "mc"}.get(draft.get("type"))
        if key:
            groups[key].append(draft)
    groups["missingVerifiedEmailCount"] = sum(not item.get("to") for item in groups["sponsorEmails"])
    return groups


def validate_pack(pack):
    errors, warnings, checks = [], [], []
    drafts = _draft_groups(pack["drafts"])

    def check(name, passed, message, code):
        checks.append({"name": name, "passed": bool(passed), "detail": message})
        if not passed:
            errors.append({"code": code, "message": message})

    budget, goal = pack["budget"], pack["goal"]
    total = sum(item["amountCents"] for item in budget["items"])
    check("Budget ceiling and integer-cent arithmetic", all(isinstance(item["amountCents"], int) and item["amountCents"] >= 0 for item in budget["items"]) and total == budget["totalCents"] and total <= goal["budgetCents"], "Every estimated allocation must reconcile in integer cents within the ceiling.", "budget")
    check("Contingency at least 10%", budget["contingencyCents"] * 10 >= total and any(item["category"] == "Contingency reserve" and item["amountCents"] == budget["contingencyCents"] for item in budget["items"]), "At least 10% of planned spending must be a protected reserve.", "contingency")
    check("Funding gap arithmetic", budget["gapCents"] == max(0, total - budget["organiserFundsCents"]) and all(sponsor["promisedRM"] == 0 for sponsor in pack["sponsors"]), "Gap uses organiser funds only; prospect asks are not committed revenue.", "funding")
    chosen = pack["dateDecision"]["chosen"]
    check("Eligible proposed date", bool(chosen) and not chosen["blocked"] and date.fromisoformat(chosen["date"]).weekday() >= 5 and goal["dateStart"] <= chosen["date"] <= goal["dateEnd"] and chosen["date"] >= goal["scenarioDate"], "Proposed date must be a weekend in range without a known cited clash.", "date")
    check("Cited sponsor / venue facts", all(_url(item["url"]) for item in pack["sponsors"]) and all(_url(item["source"]) for item in pack["venues"]["options"]), "Every named external sponsor and venue requires a source URL.", "sources")
    check("Verified contact boundaries", all(not item["email"] or EMAIL.fullmatch(item["email"]) and _url(item["emailSource"]) and item.get("appropriatePartnershipContact") is not False and item.get("countsTowardVerifiedSuitableEmailMinimum") is not False for item in pack["sponsors"]), "Sponsor emails require an exact researched address, source URL and verified suitable sponsorship purpose; general unsuitable inboxes stay blank.", "contacts")
    sponsor_by_name = {item["name"]: item for item in pack["sponsors"]}
    draft_contacts = all(not entry.get("to") or (entry.get("recipient") in sponsor_by_name and entry["to"] == sponsor_by_name[entry["recipient"]].get("email") and sponsor_by_name[entry["recipient"]].get("appropriatePartnershipContact") is not False and sponsor_by_name[entry["recipient"]].get("countsTowardVerifiedSuitableEmailMinimum") is not False) for entry in drafts.get("sponsorEmails", []) + drafts.get("followups", []))
    check("Draft recipient purpose boundaries", draft_contacts, "Sponsor and follow-up recipients must match an approved researched partnership-purpose contact.", "draft_contacts")
    venue = pack["venues"]["selected"]["name"] if pack["venues"]["selected"] else "campus-approved venue to be confirmed"
    email_consistent = all("EventPilot" in item["subject"] and item["attendance"] == goal["attendance"] and item["cause"] == goal["cause"] and item["proposedVenue"] == venue and (not chosen or item["proposedDate"] == chosen["date"]) and item["status"] == "Draft—unsent" and "unconfirmed" in item["body"] for item in drafts["sponsorEmails"])
    check("Draft factual consistency and unsent status", email_consistent, "Drafts must match date, proposed venue, attendance target and cause, with no implied confirmation.", "drafts")
    probability = _probability(pack["weather"])
    wet = probability is None or probability > .4
    check("Weather contingency propagation", (pack["programme"]["mode"] == "Indoor contingency" and pack["budget"]["scenario"] == "Indoor weather contingency") if wet else (pack["programme"]["mode"] == "Base proposed plan" and pack["budget"]["scenario"] == "Base proposed plan"), "Weather evidence must agree with both the programme mode and within-budget allocations.", "weather_replan")
    check("Chosen-date weather consistency", not chosen or _probability(chosen.get("weather", {})) == probability, "The chosen candidate and pack weather must use the same updated evidence.", "weather_consistency")
    warnings.extend(["Campus examination timetable is unknown; no exam-clear claim is made.", "Venue permission, usable capacity and exact room remain unconfirmed.", "Real MC / performer availability and contracts are unconfirmed.", "Beneficiary and donation collection permission require written confirmation.", "Budget amounts are estimated allocations, not vendor quotes.", "Organiser funding is an assumption unless confirmed separately; sponsor asks are hypothetical.", "No outreach was sent; review all drafts before using verified contacts."])
    if not goal.get("charityPurpose", True):
        warnings = [warning for warning in warnings if not warning.startswith(("Real MC / performer", "Beneficiary and donation"))]
        warnings.append("Activity facilitators, exhibitor or vendor arrangements and session objectives require confirmation.")
    if len(pack["sponsors"]) < 5:
        warnings.append("Fewer than five cited sponsor prospects available; research must be completed, not fabricated.")
    if drafts.get("missingVerifiedEmailCount"):
        warnings.append("Some sponsor drafts have no verified email; use the cited official contact route, not a guessed address.")
    if probability is None:
        warnings.append("Weather evidence unavailable; do not interpret missing data as dry weather.")
    if pack["people"]["demo"]:
        warnings.append("Roster is explicitly fictional demonstration data, not real people or bookings.")
    if not pack["venues"]["selected"]:
        warnings.append("No cited suitable venue selected; venue discovery and approval remain blocking actions.")
    status = "Blocked—resolve failed checks" if errors else "Conditional plan—approvals required"
    return {"status": status, "passed": not errors, "ready": False, "errors": errors, "warnings": warnings, "checks": checks, "repairLoops": 0, "maxRepairLoops": 2, "readiness": status}


def _repair(pack, errors, trace):
    codes = {error["code"] for error in errors}
    repaired = []
    if codes & {"budget", "contingency", "funding", "weather_replan"}:
        wet = _probability(pack["weather"]) is None or _probability(pack["weather"]) > .4
        pack["budget"] = build_budget(pack["goal"], wet)
        pack["programme"] = build_programme(pack["goal"], pack["dateDecision"], wet)
        repaired.append("Recomputed integer-cent budget and weather-consistent programme from goal.")
    if "drafts" in codes:
        pack["drafts"] = build_drafts(pack["goal"], pack["dateDecision"], pack["venues"], pack["people"], pack["sponsors"])
        repaired.append("Regenerated inconsistent draft facts from the current pack.")
    if repaired:
        trace.emit("Validator", "tool_call", "repair_pack", "Repairing genuine failed checks only.", {"actions": repaired})
    return bool(repaired)


def apply_weather_update(pack, weather, emit=None):
    """Recompute dependencies from supplied evidence, without network or outbound calls."""
    if not isinstance(pack, dict) or not isinstance(weather, dict):
        raise ValueError("pack and weather must be objects.")
    result = copy.deepcopy(pack)
    trace = Trace(emit)
    goal, dates = result["goal"], result["dateDecision"]
    chosen = dates.get("chosen")
    proposed_date = chosen.get("date") if chosen else None
    if weather.get("date") is not None and weather["date"] != proposed_date:
        raise ValueError("Weather update must match the pack's proposed date.")
    updated_weather = copy.deepcopy(weather)
    updated_weather["date"] = proposed_date
    probability = _probability(updated_weather)
    indoor = probability is None or probability > .4
    updated_weather.update(probability=probability, indoorRequired=indoor, threshold=.4, decision="Indoor contingency required" if indoor else "Indoor-ready base plan; monitor alerts", rationale="Rain-risk threshold is a planning rule, not a forecast guarantee.")
    result["weather"] = updated_weather
    if chosen:
        old_probability = _probability(chosen.get("weather", {}))
        old_component = (1 - old_probability if old_probability is not None else .35) * 45
        new_component = (1 - probability if probability is not None else .35) * 45
        chosen["score"] = round(chosen.get("score", 0) - old_component + new_component, 2)
        chosen["weather"] = copy.deepcopy(updated_weather)
        chosen["weatherConfidence"] = "unknown" if probability is None else "low—historical frequency is not an event-date forecast" if "historical" in str(updated_weather.get("mode", "")).lower() else str(updated_weather.get("confidence", "unconfirmed"))
        chosen["reasons"] = [reason for reason in chosen.get("reasons", []) if not reason.startswith(("Weather rain-risk", "Weather evidence unavailable", "Weather recheck"))]
        chosen["reasons"].append("Weather recheck evidence unavailable; conservative indoor plan required." if probability is None else f"Weather recheck risk {probability:.0%}; {updated_weather.get('mode', 'supplied evidence')}.")
        for candidate in dates.get("candidates", []):
            if candidate.get("date") == proposed_date:
                candidate.update(copy.deepcopy(chosen))
        dates["selectionRetained"] = "Recheck updates proposed-date logistics only; alternative dates have not been rechecked or automatically booked."
    trace.emit("Risk Sentinel", "replan", "weather_update_dependencies", "Re-plan: recomputing programme, budget, risks and unsent drafts from updated weather evidence.", {"probability": probability, "indoorRequired": indoor, "threshold": .4})
    result["budget"] = trace.actor("Budget Architect", "recheck_integer_cent_allocations", build_budget, goal, indoor)
    result["programme"] = trace.actor("Programme Director", "recheck_activity_run_sheet", build_programme, goal, dates, indoor)
    result["risks"] = trace.actor("Risk Sentinel", "recheck_risk_register", build_risks, goal, updated_weather)
    result["venues"]["requestedMode"] = "Indoor contingency—confirmed cover and room approval required" if indoor else "Indoor-ready base plan—venue approval and capacity remain unconfirmed"
    for sponsor in result["sponsors"]:
        if sponsor.get("appropriatePartnershipContact") is False or sponsor.get("countsTowardVerifiedSuitableEmailMinimum") is False:
            sponsor.update(email=None, emailSource=None, contactVerified=False)
    original_drafts = copy.deepcopy(result["drafts"])
    grouped = _draft_groups(original_drafts)
    result["drafts"] = trace.actor("Outreach Drafter", "recheck_source_bound_drafts", build_drafts, goal, dates, result["venues"], result["people"], result["sponsors"])
    logistics = f"Weather recheck planning: {updated_weather['decision']}. Proposed activity setup starts at {result['programme']['startTime']}; activity ends at {result['programme']['endTime']} MYT. Venue approval remains unconfirmed; weather evidence is not a safety guarantee."
    for key in ("sponsorEmails", "followups", "mc"):
        previous = {(entry.get("recipient"), entry.get("label")): entry for entry in grouped.get(key, [])}
        for entry in result["drafts"][key]:
            prior = previous.get((entry.get("recipient"), entry.get("label")), {})
            for field, value in prior.items():
                if field not in entry and field != "type":
                    entry[field] = value
            entry["body"] += "\n\n" + logistics
    result["promo"] = trace.actor("Promo Studio", "recheck_conditional_promo_copy", build_promo, goal, dates, result["venues"])
    result["promo"]["weatherNotice"] = logistics
    result["promo"]["poster"]["weatherNotice"] = logistics
    validation = trace.actor("Validator", "recheck_cross_specialist_checks", validate_pack, result)
    loops = 0
    while validation["errors"] and loops < 2:
        if not _repair(result, validation["errors"], trace):
            break
        loops += 1
        validation = trace.actor("Validator", "revalidate_weather_repair", validate_pack, result)
    validation["repairLoops"] = loops
    retained_warnings = result.get("validation", {}).get("warnings", [])
    validation["warnings"].extend(warning for warning in retained_warnings if warning not in validation["warnings"] and "weather" not in warning.lower())
    result["validation"] = validation
    result.setdefault("summary", {}).update(readiness=validation["status"], weatherDecision=updated_weather["decision"], narrative=f"Proposed {goal['eventType']} for {goal['cause']} on {proposed_date or 'date pending'} at {goal['campus']}; target {goal['attendance']} attendees, not confirmed attendance. {updated_weather['decision']}. Estimated allocations RM{result['budget']['total']:.2f} within RM{result['budget']['limit']:.2f}; contingency RM{result['budget']['contingency']:.2f}; unconfirmed gap RM{result['budget']['gap']:.2f}. {validation['status']}.")
    if isinstance(original_drafts, list):
        result["drafts"] = [{**entry, "type": kind} for key, kind in (("sponsorEmails", "sponsor"), ("followups", "followup"), ("mc", "mc")) for entry in result["drafts"].get(key, [])]
    trace.emit("Integrator", "completed", "assemble_rechecked_pack", "Updated plan coherently; permission, safety and funding readiness remain conditional.", {"readiness": validation["status"], "repairLoops": loops})
    metrics = result.setdefault("metrics", {})
    metrics["weatherUpdates"] = metrics.get("weatherUpdates", 0) + 1
    metrics["toolCalls"] = metrics.get("toolCalls", 0) + trace.tool_calls
    metrics["traceEvents"] = metrics.get("traceEvents", 0) + len(trace.events)
    metrics["repairLoops"] = metrics.get("repairLoops", 0) + loops
    if isinstance(metrics.get("trace"), list):
        metrics["trace"].extend(trace.events)
    metrics["lastWeatherUpdate"] = {"date": proposed_date, "probability": probability, "indoorRequired": indoor, "repairLoops": loops}
    return result


def run_pipeline(prompt, overrides=None, roster=None, emit=None):
    trace = Trace(emit)
    goal, assumptions = trace.actor("Goal Interpreter", "parse_event_goal", parse_goal, prompt, overrides)
    research = trace.actor("Source Librarian", "read_verified_research", load_research)
    trace.emit("Orchestrator", "handoff", "parallel_dag", "Dispatching independent date, budget and venue tools concurrently.", {"parallel": ["Date Scout", "Budget Architect", "Venue Liaison"], "engine": ENGINE})
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="event-specialist") as pool:
        date_future = pool.submit(trace.actor, "Date Scout", "candidate_weather_calendar_rank", scout_dates, goal, research, trace)
        budget_future = pool.submit(trace.actor, "Budget Architect", "integer_cent_allocations", build_budget, goal)
        venue_future = pool.submit(trace.actor, "Venue Liaison", "cited_venue_filter", build_venues, goal, research)
        dates, budget, venues = date_future.result(), budget_future.result(), venue_future.result()
        weather = dict(dates["chosen"]["weather"]) if dates["chosen"] else {"probability": None, "mode": "unavailable", "date": None, "warning": "No eligible date; weather decision cannot be confirmed.", "sources": []}
        probability = _probability(weather)
        indoor = probability is None or probability > .4
        weather.update(indoorRequired=indoor, threshold=.4, decision="Indoor contingency required" if indoor else "Indoor-ready base plan; monitor alerts", rationale="Rain-risk threshold is a planning rule, not a forecast guarantee.")
        if indoor:
            trace.emit("Risk Sentinel", "replan", "weather_threshold", "Re-plan: wet-risk exceeds 40% or evidence is unknown; move proposed programme indoors and rebalance within the same ceiling.", {"probability": probability, "threshold": .4, "trigger": "unknown evidence" if probability is None else "threshold exceeded"})
            budget = trace.actor("Budget Architect", "rebalance_indoor_allocations", build_budget, goal, True)
            venues["requestedMode"] = "Indoor contingency—confirmed cover and room approval required"
        people_future = pool.submit(trace.actor, "Talent Coordinator", "roster_availability_rank", build_people, goal, dates, roster)
        sponsor_future = pool.submit(trace.actor, "Sponsor Matcher", "verified_contacts_and_hypothetical_asks", build_sponsors, goal, budget, research)
        programme_future = pool.submit(trace.actor, "Programme Director", "owned_run_sheet_and_countdown", build_programme, goal, dates, indoor)
        risk_future = pool.submit(trace.actor, "Risk Sentinel", "risk_register_and_plan_b", build_risks, goal, weather)
        people, sponsors, programme, risks = people_future.result(), sponsor_future.result(), programme_future.result(), risk_future.result()
        trace.emit("Orchestrator", "handoff", "dependency_handoff", "Date, venue, funding gap and roster outputs handed to outreach and promotion tools.")
        draft_future = pool.submit(trace.actor, "Outreach Drafter", "source_bound_unsent_drafts", build_drafts, goal, dates, venues, people, sponsors)
        promo_future = pool.submit(trace.actor, "Promo Studio", "conditional_approved_copy", build_promo, goal, dates, venues)
        drafts, promo = draft_future.result(), promo_future.result()
    pack = {"goal": goal, "assumptions": assumptions, "dateDecision": dates, "budget": budget, "weather": weather, "risks": risks, "people": people, "venues": venues, "programme": programme, "sponsors": sponsors, "drafts": drafts, "promo": promo, "engine": ENGINE}
    validation = trace.actor("Validator", "cross_specialist_checks", validate_pack, pack)
    loops = 0
    while validation["errors"] and loops < 2:
        if not _repair(pack, validation["errors"], trace):
            break
        loops += 1
        validation = trace.actor("Validator", "revalidate_after_real_repair", validate_pack, pack)
    validation["repairLoops"] = loops
    validation["warnings"].extend(research.get("warnings", []))
    pack["validation"] = validation
    chosen = dates["chosen"]["date"] if dates["chosen"] else None
    pack["rechecks"] = [{"label": f"T-{days}", "date": (date.fromisoformat(chosen) - timedelta(days=days)).isoformat() if chosen else None, "daysBefore": days, "checks": ["Weather and thunderstorm alerts", "Campus examinations and holiday clashes", "Venue approval and capacity", "MC / act availability", "Committed funding and actual vendor costs"], "owner": "Event Lead", "status": "Scheduled planning checkpoint—not an automated notification"} for days in (14, 7, 1)]
    pack["summary"] = {"narrative": f"Proposed {goal['eventType']} for {goal['cause']}; {chosen or 'date pending'}, {goal['campus']}. Plan for {goal['attendance']} attendees as an unconfirmed target. Ceiling RM{budget['limit']:.2f}; estimated spending RM{budget['total']:.2f}, protected contingency RM{budget['contingency']:.2f}, unconfirmed funding gap RM{budget['gap']:.2f}. {validation['status']}.", "readiness": validation["status"], "nextActions": ["Confirm beneficiary, exam timetable and date with campus", "Request written indoor venue, capacity and safety approval", "Replace demo talent or confirm real MC and backup", "Confirm organiser funds and obtain vendor quotes", "Review source-verified sponsor drafts; send manually only after approval", "Approve promotional wording and RSVP channel", "Recheck weather and all dependencies at T-14, T-7 and T-1"], "tabCoverage": ["Goal", "Dates", "Budget", "Weather", "Risk", "People", "Venues", "Programme", "Sponsors", "Drafts", "Promotion", "Validation"], "sending": "No emails sent; all outreach is draft-only", "engine": ENGINE}
    if not goal.get("charityPurpose", True):
        pack["summary"]["nextActions"][0] = "Confirm activity objectives, exam timetable and date with campus"
        pack["summary"]["nextActions"][2] = "Confirm facilitators, exhibitors or vendors and an approved backup activity lead"
        for checkpoint in pack["rechecks"]:
            checkpoint["checks"] = ["Activity team and facilitator/exhibitor availability" if entry == "MC / act availability" else entry for entry in checkpoint["checks"]]
    trace.emit("Integrator", "completed", "assemble_event_pack", "Integrated every specialist result; planning checks do not imply campus or talent approval.", {"readiness": validation["status"], "repairLoops": loops})
    pack["metrics"] = {"engine": ENGINE, "llmCalls": 0, "toolCalls": trace.tool_calls, "traceEvents": len(trace.events), "elapsedSeconds": round(time.perf_counter() - trace.started, 3), "parallelDAG": True, "candidateWeatherChecks": len(dates["candidates"]), "repairLoops": loops, "emailsSent": 0, "agents": list(dict.fromkeys(event["agent"] for event in trace.events)), "trace": trace.events}
    return pack
