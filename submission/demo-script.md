# EventPilot demo script — C-First

**Campus:** Taylor's University  
**Language/currency:** English, RM / MYR  
**Demonstration mode:** actual local service unless a public deployment is later verified  
**Delivery:** public source https://github.com/1ch7/C-First/tree/eventpilot-dormathon; live app https://d4b9a8c30a6544259346fcec7549ee20.sg2.agentos-app.run; ten-page pitch PDF in outputs/EventPilot-Pitch.pdf. One public health check passed. The evidence narrated below was captured locally; no deployed end-to-end tests or new screenshots were performed.

## Before presenting

1. Open the application root containing `server.py`, `src/`, `public/` and `data/research.json` and run `python server.py`. Open `http://127.0.0.1:3000` and check `/api/health`. The current repository clone is not runnable until source packaging is completed.
2. Keep the roster empty. Do not enter private people, mailbox information or sensitive prompt content. If you opt into example people, say they are fictional demonstration availability.
3. Have the two actual evidence JSON files, exported PDF/`.eml` and screenshots available. They are recorded evidence, not proof of public deployment.
4. Do not display private owner Gmail receipts, mailbox identity or draft/message/thread IDs. No send action belongs in this demonstration.
5. Use current measurements from the run being shown. The previous canonical 3.03-second result was a warm-cache local run, not a promised speed or hours-saved benchmark.

## Opening: problem and honest architecture

**Show:** EventPilot home and execution disclosure.

**Say:**

> We are C-First from Taylor's University. EventPilot turns a short campus-event brief into a coordinated, source-aware plan instead of separate budget sheets, date guesses and inconsistent outreach drafts. This prototype runs real independent tool-driven specialists with a parallel dependency workflow. WorkBuddy keyless activation was not completed, so these are deterministic Python specialists—not live LLM calls. The interface says so, and the measured LLM counter is zero.

## Canonical brief: actual execution

**Show:** Clear editable overrides and roster; use the canonical example button or submit this exact prompt:

> I want to organize a charity event at my university in March with a budget of RM2k.

**Say:**

> This exact brief omits a year, audience, beneficiary and organiser funding. EventPilot exposes those assumptions instead of pretending the user supplied them. At our October 2026 verification, the next March is March 2027, the audience target is assumed to be 100, the campus defaults to Taylor's Lakeside, and organiser funding defaults to RM1,400. The beneficiary still needs confirmation.

**Show:** Live timestamped trace and specialist DAG while execution is active.

> Date, budget and venue tools run concurrently. Later tools wait for their real prerequisites: dates and budget feed people, sponsorship, programme and risk; then outreach and promotion receive those outputs. Weather source requests, cache hits and dependency handoffs are actual recorded events, not an animation. A cache hit can make this live run reuse real earlier source data without issuing another network request.

If the run fails, do not narrate success. Say the service reports a failure and use the labelled evidence/replay fallback below.

## Overview and Date Decision: proposal, not permission

**Show:** Overview assumptions, readiness and Date Decision candidates/backups.

**Say:**

> The verified canonical run proposed 20 March 2027, with backups and stated scoring assumptions. This is not a booked or exam-cleared date. The university exam timetable and exact venue availability remain unknown. Passing the consistency checks does not grant permission: the pack is still a conditional plan and `ready` is false.

Use the newly generated date if it differs; explain that the actual clock and source evidence affect the result. Do not force the UI to match recorded evidence.

## Budget and Risk / Weather: coherent Plan B

**Show:** Budget totals and Risk / Weather evidence, samples, warnings and contingency.

**Say:**

> The canonical ceiling is RM2,000. The recorded plan reconciles to it in integer cents, protects RM240 contingency and displays an unconfirmed RM600 sponsorship gap. These are planning allocations, not supplier quotes, and sponsor asks do not count as promised money.
>
> March 2027 was outside the provider's forecast window. The weather shown is ten-year same-calendar-day historical climatology, not a forecast for our event. The sourced Subang Jaya city grid is not a campus weather station. Over 40% rain risk—or missing evidence—triggers a proposed indoor programme and budget rebalance within the same ceiling. Wet-day and heavy-rain thresholds are disclosed planning rules, not official alerts.

**Show:** Actual `replan` trace event and matching programme/budget modes.

> This is evidence-driven replanning. The recorded run used zero validator repair loops; we are not claiming it repaired failed validation. Separate tests exercise those repair paths.

**Show:** T-14/T-7/T-1 jobs.

> Weather rechecks are durable SQLite jobs executed while the service is running. A sleeping or stopped host cannot meet their timing guarantees, and this is not an external notification service. Venue, people and funding confirmations remain human tasks.

## People, venues and timeline: do not invent readiness

**Show:** People / MCs, venue options and Timeline.

**Say:**

> No roster was supplied, so real people and MC availability remain unconfirmed. Opted-in demo people are explicitly fictional. User-uploaded free dates are assertions, not connected calendar free/busy. Public sharing replaces names and emails with role labels, but prompts and supplied availability dates can remain visible.
>
> Venue options are cited campus facilities, not reservations. The timeline has owners and checkpoints; it is a planning run sheet, not evidence that anyone has accepted a role.

## Sponsors / Gmail: suitable contacts, unsent drafts

**Show:** Cited sponsor options, verified-recipient versus blank-recipient drafts, conditional asks and follow-ups.

**Say:**

> Sponsor and campus facts come from a curated source snapshot researched on 10 October 2026, not a fresh web search on every run. Each eligible recipient is tied to a suitable public sponsorship, event or marketing source. Where no suitable email was verified, the draft stays blank rather than guessing an address. Support and monetary asks remain proposals, not commitments.

**Show:** Select initial drafts and click the Gmail draft action in the unconfigured local build.

> Browser Google OAuth is not configured in this verified build. The app visibly offers Gmail compose, copy and unsent `.eml` downloads without claiming mailbox drafts were created. The optional implementation requests `gmail.compose`; that scope technically permits sending, but EventPilot exposes no send endpoint. We have not live-tested visitor browser authorisation.

**Optional owner evidence statement, without opening private receipts:**

> Separately, the authorised WorkBuddy owner connector created five real initial enquiry drafts and five conditional follow-up drafts. All ten were independently found with DRAFT labels. Zero emails were sent. Those are owner-connector results, not browser OAuth results, and the public run's app-created Gmail draft count correctly stays zero. Follow-ups must not be sent before an initial enquiry and a suitable waiting period.

Do not sign in to an unknown account, create additional drafts, open a Send action or display private mailbox details during this narration.

## Export and saved-run sharing

**Show:** Export tab; download PDF and an `.eml`. Reload the current saved run.

**Say:**

> The PDF is generated by the service from every Event Pack section. The `.eml` is an unsent draft artifact, not a sent message. Saved runs and traces are stored in SQLite and can reload. The random share link is read-only but not account-private: anyone holding it can read the public pack and trace. Do not place sensitive information in the prompt or publish private receipts.

## Distinct workshop: avoid charity assumptions

**Show:** Submit this second exact prompt with empty roster and no stale overrides:

> Plan a career skills workshop at Taylor's Lakeside Campus for 80 students in November 2026 with a budget of RM3000.

**Say:**

> This is not a charity request. The system uses an editable career-skills learning objective, retains `charityPurpose: false`, parses 80 attendees, and changes the programme, responsibilities, risks and outreach accordingly. It does not describe the headcount as charity beneficiaries.

**Show:** Actual workshop result, budget and changed programme. If needed, show the prior evidence as explicitly recorded evidence.

> Our verified distinct run proposed 29 November 2026, with RM3,000 total allocation, RM360 reserve and an unconfirmed RM900 gap. The latest repaired-service run took 7.87 seconds locally and made 11 weather/calendar HTTP fetch attempts. That is a single measured run, not a universal performance guarantee. Both recorded runs made zero LLM calls and sent zero email.

## Close: value and remaining gates

**Show:** Summary validation, counters and submission gate table.

**Say:**

> EventPilot's value is coherence and provenance: date evidence, budget, Plan B, people requirements and drafts agree, and unknowns are visible. The recorded local canonical browser test covered all nine tabs, saved-run reload, mobile rendering and PDF/`.eml` exports. Current source passed 76 tests with one optional live-weather skip. A concurrent SQLite lifecycle failure was reproduced, repaired and regression-tested; fresh canonical browser and workshop runs passed. The separate older transient POST500 cause remains unknown. Public deployment and public source push remain open. The ten-page pitch PDF is generated and visually reviewed. Browser OAuth and keyless LLM execution are not completed. We do not claim otherwise.

Update a pending status only after actual evidence is obtained. The branch is `eventpilot-dormathon`; `main` is not to be changed.

## Honest fallback when live tools or hosting fail

1. Keep the failure visible; do not hide it or relabel a failed run complete.
2. If available, choose **replay of a real recorded run**. The recording is created only after a genuine successful exact canonical run. Its replay badge and provenance timestamp must stay visible.
3. Say: **“This is replay of an actual earlier run, not live research or fresh source fetching.”** Original metrics describe that recording, not current elapsed/network activity.
4. Alternatively, open the existing JSON/PDF/screenshots and explicitly call them recorded local verification evidence. Do not simulate Gmail success or fabricate a public URL.
5. If neither live execution nor an actual recording is available, show the implementation and mark that demo step not complete. Honest incomplete evidence is preferable to invented success.
