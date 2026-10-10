# EventPilot — C-First

**Taylor's University · English · RM / MYR**

EventPilot turns a short campus-event brief into a conditional Event Pack: proposed dates and backups, an integer-cent budget, weather-informed Plan B, people requirements, cited venue and sponsor options, a run sheet, outreach drafts, promotion copy and downloadable exports.

**Published prototype — feature-frozen.** Source and public evidence: https://github.com/1ch7/C-First/tree/eventpilot-dormathon (`main` untouched).

**Live application:** https://c86afee1a0774dd7bb03f964cabaf5d1.sg2.agentos-app.run

Released 10 October 2026. One public `/api/health` check returned HTTP 200 and `status: ok`, with SQLite available. Per the user's credit-saving instruction, no deployed event runs, browser testing or new screenshots were performed. The detailed verification below is existing local evidence. Run local commands from this branch's checkout.

## Local updates after the published release

The published release record above is unchanged. This local checkout now adds a collapsed full-weather-evidence view, a budget `.xlsx` snapshot with a category chart, and a written draft proposal PDF. These changes are not yet deployed. Install `requirements.txt` in an isolated Python environment to enable the two new downloads (`openpyxl`, `reportlab` and `Pillow`); core planning and the original PDF/email exports still use the standard library. New exports read the saved pack without AI or network calls, preserve proposed/unconfirmed statuses, and never send mail. Budget snapshots keep each run's actual figures; RM2,000 ceiling, RM240 contingency and RM600 gap apply to the canonical recorded example, not every event.

The request UI is now brief-only: hidden legacy assumption/roster controls are disabled and cannot override the textbox. Missing-information caveats still appear in the Event Pack. Specialist tools and traces sit under an optional collapsed disclosure. New plans exclude today/past dates using the Malaysia planning date; wholly past windows are rejected with instructions to edit the request, and overlapping windows are clipped with an explicit recorded reason. Saved/replayed records are not rewritten and are labelled as historical when appropriate. Relative phrases (`next month`, `this month`, `tomorrow`) and common named date formats are supported.

Budget chart compatibility: the first `Budget summary` sheet now contains a portable static chart preview. A `Budget charts` tab contains two native charts (category allocations and the recorded budget/funding position), with explicit string/value caches and the monetary scale on the numeric axis. The category scale is no longer stretched to the whole-event ceiling. Missing values remain blank in chart caches, never invented zeros. Workbook data stays a static saved-pack snapshot; native charts can reflect cell edits in capable spreadsheet applications, but the labelled image is a static preview and some lightweight viewers may omit both images and charts.

## What actually runs

- Python 3.10+ standard-library HTTP service, SQLite storage and vanilla responsive JavaScript frontend. No runtime package installation is required.
- A real dependency-aware thread-pool workflow of deterministic, tool-driven specialists—not a deployed language-model system. WorkBuddy keyless activation was dismissed; recorded runs report `llmCalls: 0`.
- Actual timestamped execution events streamed with Server-Sent Events (SSE), including source fetches, cache reuse, dependency handoffs, weather replanning and validation.
- Nine result tabs: Overview, Date Decision, Timeline, Budget, Risk / Weather, People / MCs, Sponsors / Gmail, Promo and Export.
- Persistent saved-run retrieval, read-only capability links, multi-page PDF and unsent `.eml` exports.
- Optional browser Gmail draft creation when Google OAuth is configured. The verified local build uses compose/copy/`.eml` fallback instead.

This prototype does **not** book venues, confirm calendars or people, secure sponsor commitments, collect donations, send email or publish promotion. Passing planning checks is not real-world approval: completed evidence packs have `validation.passed: true` and `validation.ready: false`.

## Run locally

From the application root containing `server.py`, `src/`, `public/` and `data/research.json`:

```bash
python --version
python server.py
```

Open `http://127.0.0.1:3000`. The default listener is loopback only. Health is available at `http://127.0.0.1:3000/api/health`.

Change the environment in the shell that starts the service:

```bash
# Bash / Git Bash
HOST=127.0.0.1 PORT=3000 python server.py
```

```powershell
# Windows PowerShell
$env:HOST = '127.0.0.1'
$env:PORT = '3000'
python server.py
```

| Variable | Default / meaning |
|---|---|
| `PORT` | `3000`; single HTTP port |
| `HOST` | `127.0.0.1`; a hosting provider may require `0.0.0.0`, which exposes the service beyond loopback |
| `EVENTPILOT_DB` | `data/eventpilot.sqlite` beside `server.py`; use a writable persistent path and ensure its parent exists |
| `GOOGLE_CLIENT_ID` | Empty; optional Google OAuth web client identifier, not a secret |

`.env.example` documents these settings. The server does **not** automatically load `.env`; export variables or configure them in the hosting environment. Never put OAuth tokens or secret credentials in source control.

SQLite stores runs, traces, recheck jobs and app-created draft receipts. WAL files may exist beside the database. The database is local persistence, not a promise of backup or survival across host redeploys. Weather caches are in memory and disappear on restart. `data/recording.json` is a recording of the exact canonical demonstration prompt and enables explicitly labelled replay; no successful recording exists until that prompt completes.

## Specialist workflow and real parallelism

`src/pipeline.py:661` implements the workflow; these are independent functions/tool actors, not autonomous LLM agents.

```text
Goal Interpreter -> Source Librarian
                         |
             +-----------+-----------+
             |           |           |
         Date Scout   Budget       Venue
             |       Architect     Liaison
             +-----------+-----------+
                         |
               Weather threshold check
             / unknown or >40% rain risk
        indoor programme + budget rebalance
                         |
      +------------------+-------------------+
      |                  |                   |
   Talent             Sponsor            Programme + Risk
Coordinator           Matcher             Director   Sentinel
      +------------------+-------------------+
                         |
              Outreach Drafter || Promo Studio
                         |
                  Validator -> Integrator
```

The executor concurrently dispatches date/budget/venue tools, then people/sponsor/programme/risk tools, then outreach/promotion after prerequisites complete. Date Scout also checks candidate dates concurrently; monthly archive requests are shared through a Future cache rather than fetched once per candidate. This is actual bounded thread-pool execution, not an animated sequence. Trace events are stored by `server.py:78` and streamed by `server.py:298`.

Weather-triggered replanning is separate from the validator's bounded repair loop. The two recorded runs show weather replanning but `repairLoops: 0`; do not describe them as demonstrations of repairing a failed validator check. Tests exercise genuine repair paths; the validator allows at most two repair attempts.

## Sources, weather and assumptions

- Sponsor and campus facts come from `data/research.json`, researched on **10 October 2026**. This is a curated, cited source snapshot read at runtime—not a fresh internet search on every run. Contacts and eligibility must be rechecked before outreach.
- Weather uses sourced Open-Meteo Subang Jaya geocoding, archive and forecast data. Only explicitly identified Subang Jaya locations are supported; another location produces unavailable weather rather than silently substituting city data. The city grid is a proxy, not campus station measurements.
- Forecast is used only for today through day 15 of the provider's 16-day window. Later dates use same-calendar-day observations from ten prior complete years, labelled **historical climatology, not a forecast**. Missing metrics remain unavailable; sample counts and years are exposed.
- A wet day is at least 1 mm rain; a heavy-rain day is at least 20 mm. These are disclosed planning thresholds, not official alert classifications. Rain risk over 40%, or unknown evidence, triggers an indoor contingency and within-ceiling budget rebalance.
- Cache reuse is reported. Geocoding/archive data is cached for up to 24 hours, forecasts for 10 minutes, and calendar results for up to 6 hours; failures are shared briefly. No new HTTP attempt is counted for a cache hit.
- Calendar context combines provider data with cited fallback research. Unknown or incomplete holidays do not mean a clash-free date; university exam and blackout dates remain unconfirmed.
- March without a year resolves to the next March relative to the actual MYT planning date. The canonical October 2026 run therefore uses March 2027. Date recommendations can change with clock, input and source evidence.
- Canonical defaults are 100 attendees, Taylor's Lakeside Campus, Subang Jaya and organiser funds equal to 70% of the ceiling. These are editable assumptions, not user-supplied or verified facts. An unspecified charity beneficiary remains unconfirmed.
- Budget values are planning allocations, not supplier quotes. A 12% contingency is protected; validation requires at least 10%. Sponsor asks are alternatives toward an unconfirmed gap and never count as committed revenue.
- Non-charity workshops infer an editable learning objective rather than inventing a charity beneficiary. Attendance is an audience target, not evidence that that many beneficiaries exist.

T-14, T-7 and T-1 weather checks are persisted in SQLite and polled by the running service. They update the proposed date's weather, programme, budget, risks and unsent drafts. These are **not** an external scheduler or automatic email notification. A stopped/sleeping host cannot execute them on time; campus, funding and people confirmations still require human review. Alternatives are not automatically booked or rechecked.

## Privacy and Gmail boundaries

- `/run/<id>` is a random capability link, not an authenticated private workspace. Anyone holding it can retrieve the public pack and trace. Prompts are included; do not enter sensitive information.
- Roster names and emails are replaced with role-based labels before persistence/public sharing. Roles and supplied free dates remain visible. Availability is a user assertion, not verified calendar free/busy. The default roster is empty; fictional examples require explicit demo opt-in and remain labelled.
- A Gmail access token is used for the request only and is not persisted. App-created receipts contain account hashes and draft identifiers in the private database; keep databases and private receipts out of the public repository.
- Optional browser OAuth requests **`gmail.compose` only**. That scope technically also permits sending; EventPilot restricts its own implementation to Gmail draft creation and exposes no send endpoint. Do not claim the scope itself is draft-only.
- Without `GOOGLE_CLIENT_ID`, the app visibly offers Open Gmail compose, copy and `.eml` downloads and does not claim mailbox drafts were created. Saving a compose window or importing `.eml` remains a user action.
- The owner-authorized WorkBuddy Gmail connector is a **separate path**, not available to visitors. Ten real owner drafts—five initial enquiries and five conditional follow-ups—were independently verified with DRAFT labels on 10 October 2026. **Zero emails were sent.** This does not validate browser OAuth, and does not inflate the recorded per-run `gmailDraftsCreated: 0` counter.
- Only source-verified suitable partnership/event/marketing recipients are eligible. Blank-recipient drafts are deliberate where routing is unverified. Draft retries are deduplicated; uncertain outcomes require manual mailbox review.

Private mailbox identity, draft/message/thread IDs, private roster data, tokens, `.env` and SQLite files must never be included in public submission artifacts. Private connector receipts are intentionally excluded from public evidence.

## API surface

All write requests require JSON; cross-origin browser writes are rejected. The demo limits run creation per client IP and request sizes, but is not a full authenticated multi-tenant service.

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | Service/database health and execution disclosure |
| GET | `/api/config` | Public OAuth identifier, scope and replay availability |
| POST | `/api/runs` | `{ "prompt": "...", "overrides": {}, "roster": [] }`; starts a run |
| POST | `/api/runs` | `{ "mode": "replay" }`; loads labelled actual recording if available |
| GET | `/api/runs/<id>` | Saved public pack, trace, status and jobs |
| GET | `/api/runs/<id>/stream` | SSE trace/completion/failure events |
| GET | `/api/runs/<id>/pdf` | Event Pack PDF |
| GET | `/api/runs/<id>/eml/<index>` | Unsent draft export; zero-based index |
| POST | `/api/runs/<id>/gmail-drafts` | Optional token-authorized draft creation for selected indices |
| GET | `/run/<id>` | Saved-run frontend capability page |

There is no email-send route. A runtime failure, restart interruption or unavailable execution queue is marked failed rather than reported as successful. Replay has a persistent provenance label and recording timestamp; it must never be presented as live research.

## Tests and bounded evidence

```bash
python -m unittest discover -s tests -v
```

Deterministic tests mock external weather/Gmail boundaries and exercise arithmetic, validation, actual parallel handoffs, replanning, public roster redaction, request handling, export generation, draft deduplication and scheduled updates. They are not proof of a deployed OAuth flow. An optional live-weather test is skipped unless explicitly enabled.

The latest lead-executed integrated suite ran **77 tests: 76 passed, 1 optional live-weather test skipped**, in **19.725 seconds**. It includes three loopback queue/request regressions and three SQLite connection-lifetime regressions. A restarted run exposed SQLITE_READONLY under concurrent connections; the connection-lifetime race was reproduced, repaired and stress-tested with 1,000 operations without errors. The repaired service passed a fresh canonical browser run and a distinct workshop run. Managed Node syntax passed. The older transient POST HTTP 500 has an unconfirmed cause and is not retroactively explained by this separate database repair.

`tests/browser_verify.cjs` is the actual local browser harness. Install `playwright-core` in your test environment or set `EVENTPILOT_PLAYWRIGHT_PATH`; set `EVENTPILOT_CHROME_PATH` to your Chrome executable and optionally `EVENTPILOT_TEST_URL` to the tested service. Build-machine paths remain fallback defaults. Failures are surfaced and saved rather than waiting only for successful results. Browser tooling is test-only, not a runtime dependency.

Two **actual local runs**, not universal performance benchmarks:

| Evidence | Canonical charity event | Career workshop |
|---|---|---|
| Prompt | `I want to organize a charity event at my university in March with a budget of RM2k.` | `Plan a career skills workshop at Taylor's Lakeside Campus for 80 students in November 2026 with a budget of RM3000.` |
| Proposed date | 20 March 2027 | 29 November 2026 |
| Ceiling / reserve / unconfirmed gap | RM2,000 / RM240 / RM600 | RM3,000 / RM360 / RM900 |
| Measured server elapsed | 10.89 s, after service restart | 7.87 s |
| HTTP weather/calendar fetch attempts | 12 | 11 |
| Specialist tool-call counter | 31 | 30 |
| Candidate weather checks | 5 | 5 |
| LLM calls / app Gmail drafts / emails sent | 0 / 0 / 0 | 0 / 0 / 0 |
| Weather meaning | Historical climatology, not forecast | Historical climatology, not forecast |
| Validation | Passed; still conditional, not ready | Passed; still conditional, not ready |
| Artifact | `outputs/canonical-run-evidence.json` | `outputs/workshop-run-evidence.json` |

The tool-call counter includes specialist execution/tool events; it is not interchangeable with network requests. Elapsed time is measured server execution, not a claim of hours saved. Canonical browser evidence covers an actual button click/POST/SSE, all nine tabs, saved-run reload, 390 px mobile rendering, no JavaScript errors, PDF/`.eml` exports and visible unconfigured-OAuth fallback. Browser OAuth authorization and public-host execution are **not verified**.

## Submission artifacts and remaining gates

- Public evidence: the two run JSON files; `outputs/EventPilot-Canonical-Event-Pack.pdf`; `outputs/EventPilot-Printcious-Draft.eml`; seven desktop/mobile screenshots.
- Release record: `submission/SUBMISSION.md`.
- Presentation narration: `submission/demo-script.md`.
- Ten-page pitch: `outputs/EventPilot-Pitch.pdf`; editable PPTX: `submission/EventPilot-Pitch/EventPilot-Pitch.pptx`. Native PowerPoint PDF export and all-page visual review completed locally.
- **Public release scope:** publish the existing Python service and perform one health check only, per the user's credit-saving instruction. Source and existing artifacts are packaged on `eventpilot-dormathon`. Earlier local browser/workshop checks passed; they do not establish deployed end-to-end verification. Pitch PDF is already generated.
- **NOT CONFIGURED / NOT VERIFIED:** visitor browser Google OAuth. WorkBuddy keyless LLM activation was not completed; the deterministic fallback is explicitly disclosed rather than represented as LLM execution.

Internal feature freeze: **11 October 2026, 08:30 MYT**. Submission target: **09:00 MYT**. No public URL or completion claim should be inserted without actual evidence.
