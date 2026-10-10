# EventPilot submission record

**Group:** C-First  
**Campus:** Taylor's University, Malaysia  
**Language:** English  
**Currency:** RM / MYR  
**Documentation snapshot:** 10 October 2026, MYT  
**Overall status:** **NOT COMPLETE — local evidence exists; public delivery gates remain open.**

This record distinguishes verified results from implemented-but-unverified capabilities and work not completed. It is not a receipt for a successful public submission.

## Intended delivery

- Existing repository: `https://github.com/1ch7/C-First.git`.
- Separate branch: `eventpilot-dormathon`; `main` must remain untouched. No merge or overwrite of `main` is authorised by this record.
- Target campus context: Taylor's Lakeside Campus, Subang Jaya, subject to organiser confirmation.
- Feature freeze: **11 October 2026, 08:30 MYT**.
- Submission target: **11 October 2026, 09:00 MYT**.
- Public application link: **NOT OBTAINED**. No placeholder URL is a deployed result.
- Public source release: **NOT PUSHED** at this snapshot. The existing local repository clone was README-only when this documentation task began; source packaging is a separate pending action.

## What was built

A single-port Python 3.10+ standard-library server (`server.py`), SQLite persistence, responsive HTML/CSS/JavaScript dashboard and independent tool-driven planning specialists. A brief produces proposed dates/backups, budget/reserve/gap, weather evidence and indoor Plan B, roster-based role availability, cited venue/sponsor options, programme/countdown, sponsor and follow-up drafts, promotion copy, validation and exports.

**Execution disclosure:** WorkBuddy keyless activation was dismissed and the local fallback was selected. Specialists are deterministic Python tool actors operating through a real dependency-aware thread-pool DAG. `llmCalls` is zero. Real parallel execution and real external tool evidence exist; a deployed LLM integration does not.

**Planning disclosure:** These are conditional plans, not booked events. `validation.passed` checks arithmetic and cross-section consistency; `validation.ready` remains false because campus approval, examinations, venue capacity/booking, real people, beneficiary/objectives, actual funding and supplier quotes are not confirmed.

## Verified local runs

### 1. Canonical charity prompt

Exact input:

> I want to organize a charity event at my university in March with a budget of RM2k.

Evidence: `outputs/canonical-run-evidence.json`  
Public planning run identifier: `lrEBSyNn1OpxYN2idLatgorL`  
Created: **10 October 2026, 17:43:39 MYT**  
Mode: **live local tool-driven execution**, not replay.

| Measure | Actual result |
|---|---|
| Proposed date | 20 March 2027; not a booking |
| Audience | 100, explicitly assumed |
| Cause | Student-selected charity; beneficiary unconfirmed |
| Campus/location | Taylor's Lakeside Campus / Subang Jaya, disclosed defaults |
| Estimated allocation ceiling and total | RM2,000 |
| Protected contingency | RM240 (12%) |
| Assumed organiser funds | RM1,400 |
| Unconfirmed sponsorship gap | RM600 |
| Measured server duration | 10.89 seconds, after repaired-service restart |
| Candidate weather checks | 5 |
| Weather/calendar HTTP fetch attempts | 12 |
| Specialist execution/tool counter | 31 |
| Weather | Historical same-calendar-day climatology; **not** a March 2027 forecast |
| Weather replanning | Present; indoor contingency and within-ceiling rebalance |
| Validator repair attempts | 0; do not claim the recorded run repaired failed validation |
| Validation | Passed; zero consistency errors; still conditional and not ready |
| LLM calls | 0 |
| Prepared outreach artifacts | 27; not all have eligible recipients |
| Gmail drafts created by this app run | 0 |
| Emails sent | 0 |

The exact March year resolves from the MYT planning date, not a fixed hardcoded March 2027 default. An exact prompt repeated later can resolve to another future March.

### 2. Distinct non-charity workshop prompt

Exact input:

> Plan a career skills workshop at Taylor's Lakeside Campus for 80 students in November 2026 with a budget of RM3000.

Evidence: `outputs/workshop-run-evidence.json`  
Public planning run identifier: `mKWAAbJ_8CKNawgsbWY0IOxd`  
Created: **10 October 2026, 17:44:48 MYT**  
Mode: **live local tool-driven execution**, not replay.

| Measure | Actual result |
|---|---|
| Proposed date | 29 November 2026; not a booking |
| Audience | 80, parsed from input; target rather than confirmed attendance |
| Objective | Career skills learning and practice, disclosed inferred editable objective |
| Charitable purpose | `charityPurpose: false`; no invented charity beneficiary |
| Estimated allocation ceiling and total | RM3,000 |
| Protected contingency | RM360 (12%) |
| Assumed organiser funds / gap | RM2,100 / RM900, both unconfirmed |
| Measured server duration | 7.87 seconds |
| Candidate weather checks | 5 |
| Weather/calendar HTTP fetch attempts | 11 |
| Specialist execution/tool counter | 30 |
| Weather | Historical climatology, not an event-date forecast |
| Validator repair attempts | 0 |
| Validation | Passed; conditional and not ready |
| LLM calls / app Gmail drafts / emails sent | 0 / 0 / 0 |

The second input changes audience, budget, date window, purpose, programme, risks and outreach. It demonstrates bounded scenario adaptation, not arbitrary natural-language understanding or a deployed model.

### Metric interpretation

`elapsedSeconds` measures actual server processing, not browser round-trip or hours saved. `toolCalls` counts specialist running/tool-call events and includes local operations. `networkRequests` counts actual HTTP fetch attempts emitted by weather/calendar tools, excluding cache reuse. Counts are not interchangeable; a warm-cache live run can have zero new HTTP attempts while still executing real specialists.

## Independent local verification

### Automated suite

Latest lead-executed integrated verification ran **77 tests: 76 passed, 1 optional live-weather test skipped**, in **19.725 seconds**. Three queue/request loopback regressions prove failure503/persisted failed/GET and SSE failed, accepted202 and pre-insertion rejection. Three additional SQLite regressions prove lifetime serialization, lock release after failed connect and concurrent read/write safety. The lead reproduced SQLITE_READONLY under 1,000 concurrent operations, repaired connection lifetime locking, then completed 1,000 operations without errors. These are actual local tests, not public deployment certification.

**Running-process boundary:** the repaired service was restarted and fresh canonical browser verification passed (run `lrEBSyNn1OpxYN2idLatgorL`, 10.89 seconds, 12 actual HTTP attempts). All nine tabs, exports, saved reload, 390px mobile and zero JavaScript errors were verified. The distinct workshop also completed (`mKWAAbJ_8CKNawgsbWY0IOxd`, 7.87 seconds, 11 HTTP attempts). The separate older transient POST500 cause remains unknown. One restarted run failed with SQLITE_READONLY before the verified repair; that failure is retained, not relabelled successful.

Reproduction from the application root:

```bash
python -m unittest discover -s tests -v
```

The deterministic suite covers goal parsing, integer-cent allocation/reconciliation and reserves, budget-gap integrity, cited contact boundaries, parallel handoffs, weather source/cache semantics, unknown-weather Plan B, cross-specialist repair, non-charity event content, roster redaction, request validation, Gmail draft deduplication/uncertain outcomes, exports, persistence and weather-update propagation. Mocked Gmail checks do not prove real visitor OAuth.

Newest queue safeguard is implemented at `server.py:350`: executor submission failure marks the stored run failed and returns 503 rather than leaving it running or claiming completion. Current-source loopback verification and fresh repaired-service browser verification passed. Public deployment remains a separate unverified gate.

### Real browser verification

`outputs/canonical-run-evidence.json` contains the actual `browser.checks` array produced by `tests/browser_verify.cjs`:

- Canonical UI button click, actual POST, SSE completion and saved-pack assertions.
- All nine result tabs rendered substantive content without `NaN` or object-string artifacts.
- Google OAuth visibly reported unconfigured and offered fallback without claiming created drafts.
- PDF and a source-bound `.eml` exported successfully.
- Saved run reloaded from SQLite.
- 390 px mobile home had no horizontal overflow; saved pack rendered.
- No browser JavaScript errors.

These are **local** checks, not verification of a public deployment. The browser harness supports EVENTPILOT_PLAYWRIGHT_PATH and EVENTPILOT_CHROME_PATH environment settings, with build-machine fallbacks; compatible local browser tooling is required. Node/browser tooling is needed only for browser tests; application runtime remains dependency-free.

## Gmail evidence without private receipts

The separately owner-authorized WorkBuddy Gmail connector created:

- **5 initial sponsorship enquiry drafts**.
- **5 conditional follow-up drafts**, intended only after an initial message is actually reviewed/sent and an appropriate waiting period.
- All **10** were independently found with **DRAFT** labels on 10 October 2026.
- **0 emails sent**; no outreach send action was used.

Recipient routing was bound to five verified suitable first-party sponsorship/event/marketing contact sources. Other researched prospects may have conditional fit, directory-sourced contacts or no appropriate verified email. Do not fabricate recipients to reach a quota or present sponsor interest as commitment.

This is a verified **owner connector** result, not a visitor/browser OAuth result. The two public run records correctly retain `gmailDraftsCreated: 0`. Private mailbox identity and all Gmail draft/message/thread identifiers are excluded from this record and must not be included in public artifacts. The private connector receipt file is not a public deliverable.

### Browser OAuth capability status

**NOT CONFIGURED / NOT LIVE-VERIFIED.** The optional browser implementation requests `gmail.compose`, verifies the token's mailbox and creates selected drafts only. The scope technically permits sending as well; the application exposes no send route. Without a Google client ID, compose/copy/`.eml` fallback is the accurate demonstration. Do not present connector receipts or mocked tests as a completed browser sign-in test.

## Source, weather, scheduling and privacy limitations

| Area | Honest boundary |
|---|---|
| Sponsors/campus | Curated `data/research.json` snapshot dated 10 October 2026; facts have sources but no fresh company search occurs on every run. Reverify before contact. |
| Event dates | Ranked weekend candidates with cited evidence; campus exams and venue availability unknown. No clash-free or booking guarantee. |
| Weather coverage | Explicit Subang Jaya location only; sourced city-grid proxy, not a campus microclimate. Unsupported locations stay unavailable. |
| Forecast versus history | Only today through day 15 uses forecast. Later dates use prior complete-year same-calendar-day climatology with displayed samples/uncertainty; neither recorded event date is a forecast. |
| Risk rules | 1 mm wet-day, 20 mm heavy-day and >40% indoor threshold are disclosed operational assumptions, not official alert categories. |
| Source failure/cache | Missing results are unavailable, never manufactured. Cache hits/shared in-flight calls are traceable and excluded from network counts. Cache is memory-only. |
| Funding | Allocations are estimates, reserve is protected and sponsorship asks are alternatives, not promised money. |
| People | Empty by default; opted-in fictional demo roster stays labelled. Uploaded availability is user assertion, not verified free/busy. |
| Scheduled checks | SQLite T-14/T-7/T-1 jobs execute only while the service is running; stopped/sleeping hosting cannot meet timing guarantees. No external scheduler or automatic notifications. |
| Replanning | Proposed-date weather can coherently update budget/programme/risks/unsent drafts; alternative dates are not rechecked or booked automatically. Previously created mailbox drafts require manual review if the plan changes. |
| Storage | SQLite persistence is real; external backup, redeploy survival and continuous host availability are not established. |
| Public access | Random read-only share link is a capability, not account authentication. Anyone holding it can read pack and trace, including prompt. |
| Redaction | Private roster names/emails are removed before saved/public sharing; roles and supplied dates remain. Sensitive prompt content is not automatically redacted. |
| Email | Draft preparation only; no send endpoint. Owner connector authorisation is separate from visitors. No Gmail access token persisted. |
| Deployment | No public host URL or external-host checks exist yet. The standard-library prototype is not a fully authenticated multi-tenant production service. |

## Local artifact inventory

The following artifacts existed locally when inspected. They are not proof of public upload; references are relative to the application root.

| Artifact | Meaning |
|---|---|
| `outputs/canonical-run-evidence.json` | Actual canonical pack, timestamped trace, metrics, persisted job state and browser evidence |
| `outputs/workshop-run-evidence.json` | Actual distinct workshop pack, trace and metrics |
| `outputs/EventPilot-Canonical-Event-Pack.pdf` | Export generated by the running app during canonical browser verification |
| `outputs/EventPilot-Printcious-Draft.eml` | Unsent, source-bound initial enquiry export; no sender mailbox identity required |
| `outputs/eventpilot-home-desktop.png` | Actual local desktop home screenshot |
| `outputs/eventpilot-pack-desktop.png` | Actual local desktop generated-pack screenshot |
| `outputs/eventpilot-budget-desktop.png` | Actual local budget tab screenshot |
| `outputs/eventpilot-risk-weather-desktop.png` | Actual local weather/risk tab screenshot |
| `outputs/eventpilot-sponsors-gmail-desktop.png` | Actual local sponsorship/draft UI screenshot; not evidence of browser OAuth success |
| `outputs/eventpilot-home-mobile.png` | Actual local mobile home screenshot |
| `outputs/eventpilot-pack-mobile.png` | Actual local mobile pack screenshot |
| `submission/demo-script.md` | Demonstration narration with live/replay/LLM/OAuth caveats |
| `submission/EventPilot-Pitch/EventPilot-Pitch.pptx` | Ten-page editable pitch; native PDF export completed |
| `outputs/EventPilot-Pitch.pdf` | Ten-page English pitch PDF; all pages visually reviewed |
| `repository/README.md` | Public repository README draft; application packaging and push pending |

Do **not** publish SQLite/WAL files, `.env`, tokens, private rosters, private mailbox identity or connector receipt IDs. Review PDFs, `.eml`, screenshots, JSON, recordings and any repository history for private data before public packaging. The canonical and workshop prompt/run IDs are public planning evidence, not private Gmail receipt identifiers.

## Release gate checklist

| Gate | Status at this snapshot | Required evidence before claiming completion |
|---|---|---|
| Actual canonical local run | **PASS** | Existing run JSON and browser evidence |
| Distinct workshop local run | **PASS** | Existing workshop run JSON; non-charity purpose preserved |
| Latest integrated automated tests | **PASS WITH SKIP** | 77 executed / 76 passed / 1 optional skip, 19.725 seconds; current-source suite |
| Latest queue-safeguard regressions | **PASS UNDER LOOPBACK TESTS** | Three HTTP regressions exercise failure persistence/GET/SSE, accepted submission and invalid input |
| Main local process restart and fresh browser recheck | **PASS LOCALLY** | Repaired canonical browser and distinct workshop completed; older transient POST500 cause unknown |
| Responsive dashboard / reload / exports | **PASS LOCALLY** | Existing browser checks, screenshots, PDF and `.eml` |
| Ten owner Gmail drafts | **PASS, PRIVATE RECEIPTS** | Draft-only owner evidence retained privately; zero sends |
| Visitor browser OAuth | **NOT CONFIGURED / NOT VERIFIED** | Real client configuration and authorised browser test, or explicitly accept fallback limitation |
| WorkBuddy keyless LLM runtime | **NOT ACTIVATED** | Actual activation and model execution evidence, or retain explicit deterministic-fallback disclosure |
| Public deployment link | **NOT COMPLETE** | Obtained real URL plus independently successful public health, run/SSE, reload and export checks |
| Public source packaging/push | **NOT COMPLETE** | Reviewed source/artifact inventory pushed only to `eventpilot-dormathon`, then read back remotely |
| `main` unchanged | **REQUIRED; FINAL REMOTE CHECK PENDING** | Remote comparison after final branch push; no merge |
| Pitch PDF and final presentation review | **PASS LOCALLY** | Ten-page actual PowerPoint PDF generated; all pages visually reviewed with accurate execution/release boundaries |
| Final public submission | **NOT COMPLETE** | Actual delivered links/artifacts and remaining-limitations statement |

A later verified result may update a gate. Do not replace these statuses with speculative success, fabricated links or placeholders suggesting completion.
