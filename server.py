"""EventPilot: single-port, dependency-free HTTP/SSE/SQLite service.
No mail-sending route exists. Google tokens are used once and never persisted.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta, timezone
from email.message import EmailMessage
from email.policy import SMTP
import base64
import collections
import hashlib
import json
import mimetypes
import os
import secrets
import sqlite3
import threading
import time
import traceback
import textwrap

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
DB_PATH = Path(os.environ.get("EVENTPILOT_DB", str(DATA / "eventpilot.sqlite")))
MYT = timezone(timedelta(hours=8))
POOL = ThreadPoolExecutor(max_workers=4)
DB_LOCK = threading.RLock()
RATE = collections.defaultdict(collections.deque)
GMAIL_LOCK = threading.RLock()
VERSION = "1.0.0"

def now():
    return datetime.now(MYT).isoformat()

class ClosingConnection(sqlite3.Connection):
    _owns_db_lock = False

    def close(self):
        try:
            return super().close()
        finally:
            if self._owns_db_lock:
                self._owns_db_lock = False
                DB_LOCK.release()

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def db():
    # Serialize the whole connection lifetime, including readers opening WAL
    # handles. Locking writes alone permits a Windows WAL open/close race.
    DB_LOCK.acquire()
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30, factory=ClosingConnection)
        conn._owns_db_lock = True
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        DB_LOCK.release()
        raise

def initialize():
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, status TEXT NOT NULL, prompt TEXT NOT NULL, pack TEXT, trace TEXT NOT NULL, created_at TEXT NOT NULL, elapsed REAL DEFAULT 0, error TEXT, private_roster TEXT, mode TEXT DEFAULT 'live')")
        c.execute("CREATE TABLE IF NOT EXISTS rechecks (run_id TEXT, due TEXT, offset INTEGER, status TEXT DEFAULT 'pending', result TEXT, PRIMARY KEY(run_id, offset))")
        c.execute("CREATE TABLE IF NOT EXISTS gmail_receipts (run_id TEXT, account_hash TEXT, draft_index INTEGER, draft_id TEXT, subject TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL, content_hash TEXT, PRIMARY KEY(run_id, account_hash, draft_index))")
        columns = {r[1] for r in c.execute("PRAGMA table_info(gmail_receipts)")}
        if "content_hash" not in columns:
            c.execute("ALTER TABLE gmail_receipts ADD COLUMN content_hash TEXT")
        # Interrupted runs are never shown as successfully completed.
        c.execute("UPDATE runs SET status='failed', error='Service restarted during this run; re-run the prompt.' WHERE status='running'")

def row_run(run_id):
    with db() as c:
        row = c.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        return None
    result = {k: row[k] for k in ("id", "status", "created_at", "elapsed", "error", "mode")}
    result["pack"] = json.loads(row["pack"]) if row["pack"] else None
    result["trace"] = json.loads(row["trace"])
    with db() as c:
        checks = c.execute("SELECT due,offset,status,result FROM rechecks WHERE run_id=? ORDER BY due", (run_id,)).fetchall()
    result["recheckJobs"] = [{"due": r["due"], "daysBefore": r["offset"], "status": r["status"], "result": json.loads(r["result"]) if r["result"] else None} for r in checks]
    return result

def emit(run_id, agent, status, tool, message, data=None):
    event = {"agent": str(agent), "status": str(status), "tool": str(tool), "message": str(message), "time": now(), "data": data}
    with DB_LOCK, db() as c:
        row = c.execute("SELECT trace FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return
        events = json.loads(row[0])
        event["seq"] = len(events) + 1
        events.append(event)
        c.execute("UPDATE runs SET trace=? WHERE id=?", (json.dumps(events), run_id))


def public_roster(roster):
    # Public share URLs never expose personal roster contact details.
    if roster is None:
        return []
    if not isinstance(roster, list):
        raise ValueError("roster must be a list")
    out = []
    for i, item in enumerate(roster[:100]):
        if not isinstance(item, dict):
            continue
        supplied_role = str(item.get("role", "volunteer")).lower().strip()
        roles = {"mc": "MC", "emcee": "MC", "photographer": "photographer", "tech": "tech crew", "tech crew": "tech crew", "volunteer": "volunteer", "organiser": "organiser"}
        role = roles.get(supplied_role, "volunteer")
        # Client-supplied demo:true is never permission to publish private names.
        free_dates = []
        for d in (item.get("freeDates") or [])[:200]:
            try:
                free_dates.append(date.fromisoformat(str(d)).isoformat())
            except (ValueError, TypeError):
                pass
        out.append({"name": f"{'Demo ' if item.get('demo') is True else ''}{role} #{i+1}", "role": role, "freeDates": free_dates, "demo": item.get("demo") is True, "contactProvided": bool(item.get("email"))})
    return out


def normalize_public_pack(pack):
    groups = pack.get("drafts")
    if isinstance(groups, dict):
        flat = []
        for key, kind in (("sponsorEmails", "sponsor"), ("followups", "followup"), ("mc", "mc")):
            for draft in groups.get(key, []) or []:
                if isinstance(draft, dict):
                    flat.append({**draft, "type": kind})
        pack["drafts"] = flat
    pack.get("metrics", {}).pop("trace", None)
    return pack


def execute_run(run_id, prompt, overrides, roster):
    start = time.monotonic()
    try:
        from src.pipeline import run_pipeline
        emit(run_id, "Orchestrator", "running", "SQLite + thread pool", "Live execution started; specialist events below reflect actual work, not animations.")
        pack = run_pipeline(prompt, overrides=overrides, roster=public_roster(roster), emit=lambda agent, status, tool, message, data=None: emit(run_id, agent, status, tool, message, data))
        pack = normalize_public_pack(pack)
        pack["runId"] = run_id
        pack["generatedAt"] = now()
        pack["engine"] = "Tool-driven specialist agents. LLM unavailable: WorkBuddy keyless activation dismissed."
        pack["mode"] = "live"
        pack["privacy"] = "Anyone with this random share URL can view this pack. Roster names/contact details are redacted; do not enter sensitive information in prompts."
        elapsed = round(time.monotonic() - start, 2)
        trace = row_run(run_id)["trace"]
        network_calls = sum(1 for e in trace if isinstance(e.get("data"), dict) and e["data"].get("networkRequest") is True and e["status"] == "running")
        pack.setdefault("metrics", {}).update({"elapsedSeconds": elapsed, "traceEvents": len(trace), "networkRequests": network_calls, "networkRequestsDefinition": "Actual HTTP fetch attempts emitted by the weather/calendar tools; cache hits excluded.", "draftsPrepared": len(pack.get("drafts", [])), "gmailDraftsCreated": 0})
        with DB_LOCK, db() as c:
            c.execute("UPDATE runs SET status='complete',pack=?,elapsed=? WHERE id=?", (json.dumps(pack), elapsed, run_id))
            for check in pack.get("rechecks", []):
                if isinstance(check, dict):
                    due = check.get("date") or check.get("due") or check.get("dueDate")
                    offset = check.get("daysBefore") or check.get("offset") or check.get("days")
                    if due and offset:
                        c.execute("INSERT OR IGNORE INTO rechecks(run_id,due,offset) VALUES (?,?,?)", (run_id, str(due)[:10], int(offset)))
        emit(run_id, "Integrator Agent", "complete", "SQLite", f"Event Pack saved in {elapsed:.2f}s; PDF export is available.")
        # Only sanitized, genuinely completed recordings can become replay fixtures.
        recording = {"prompt": prompt, "pack": pack, "trace": row_run(run_id)["trace"], "recordedAt": now()}
        if not roster and prompt == "I want to organize a charity event at my university in March with a budget of RM2k.":
            (DATA / "recording.json").write_text(json.dumps(recording, indent=2), encoding="utf-8")
    except Exception as exc:
        emit(run_id, "Orchestrator", "failed", "runtime", f"Run failed: {type(exc).__name__}. No success is claimed.")
        with db() as c:
            c.execute("UPDATE runs SET status='failed',error=?,elapsed=? WHERE id=?", (str(exc)[:300], round(time.monotonic()-start, 2), run_id))
        traceback.print_exc()


def pdf_bytes(pack):
    """Real multi-page PDF with every Event Pack section, no external dependencies."""
    lines = ["EVENTPILOT | C-First | Taylor's University", "EVENT PACK - proposed plan, approvals required", "Generated: " + str(pack.get("generatedAt", now())), ""]
    titles = [("summary", "EXECUTIVE SUMMARY"), ("goal", "GOAL AND ASSUMPTIONS"), ("assumptions", "EDITABLE ASSUMPTIONS"), ("dateDecision", "DATE DECISION AND BACKUPS"), ("budget", "BUDGET (RM) - ALLOCATIONS, NOT VENDOR QUOTES"), ("weather", "DATE-SPECIFIC WEATHER AND LIMITATIONS"), ("risks", "RISK REGISTER AND PLAN B"), ("people", "PEOPLE AND MC AVAILABILITY"), ("venues", "VENUES AND APPROVALS"), ("programme", "RUN OF SHOW AND COUNTDOWN"), ("sponsors", "SPONSOR SHORTLIST - NOT COMMITMENTS"), ("drafts", "SPONSOR EMAILS AND FOLLOW-UPS - NEVER SENT"), ("promo", "PROMO KIT"), ("validation", "VALIDATION AND OUTSTANDING CONFIRMATIONS"), ("rechecks", "SCHEDULED WEATHER RECHECKS"), ("metrics", "MEASURED RUN RESULTS"), ("engine", "EXECUTION ENGINE")]
    def walk(value, prefix=""):
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, (list, dict)):
                    lines.append(prefix + str(k) + ":")
                    walk(v, prefix + "  ")
                else:
                    lines.extend(textwrap.wrap(prefix + str(k) + ": " + str(v), width=95, subsequent_indent=prefix + "  ", break_long_words=True) or [""])
        elif isinstance(value, list):
            for index, v in enumerate(value):
                lines.append(prefix + f"[{index+1}]")
                walk(v, prefix + "  ")
        else:
            lines.extend(textwrap.wrap(prefix + str(value), 95, break_long_words=True) or [""])
    for key, title in titles:
        lines += ["", title, "-"*65]
        walk(pack.get(key, "Not available"))
    pages = [lines[i:i+63] for i in range(0, len(lines), 63)]
    objects = []
    def obj(data):
        objects.append(data.encode("latin-1", errors="replace") if isinstance(data, str) else data)
        return len(objects)
    obj("<< /Type /Catalog /Pages 2 0 R >>")
    obj(b"")
    font_id = obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []
    for index, page in enumerate(pages):
        content = ["BT /F1 8.5 Tf 12 TL 40 797 Td"]
        for line in page:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content.append(f"({safe}) Tj T*")
        content += ["ET", f"BT /F1 9 Tf 40 30 Td (EventPilot | Page {index+1} of {len(pages)}) Tj ET"]
        stream = "\n".join(content).encode("latin-1", errors="replace")
        content_id = obj(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        page_ids.append(obj(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"))
    objects[1] = ("<< /Type /Pages /Kids [" + " ".join(f"{i} 0 R" for i in page_ids) + f"] /Count {len(page_ids)} >>").encode()
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, value in enumerate(objects, 1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode() + value + b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(out)


def email_bytes(draft):
    msg = EmailMessage(policy=SMTP)
    recipient = draft.get("to") or draft.get("email") or ""
    if isinstance(recipient, list):
        recipient = ", ".join(recipient)
    if recipient:
        msg["To"] = str(recipient).replace("\r", "").replace("\n", "")
    msg["Subject"] = str(draft.get("subject", "EventPilot draft")).replace("\r", "").replace("\n", "")
    msg.set_content(str(draft.get("body") or draft.get("text") or ""))
    return msg.as_bytes()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *args):
        pass  # Do not put public prompts or OAuth tokens in request logs.
    def response(self, code, payload, kind="application/json", headers=None):
        body = json.dumps(payload).encode() if kind == "application/json" else payload
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store" if kind in ("application/json", "application/pdf", "message/rfc822") else "public, max-age=60")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)
    def body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size > 65536 or size <= 0:
            raise ValueError("Request body must be between 1 and 65536 bytes")
        value = json.loads(self.rfile.read(size))
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value
    def allowed(self, limit=12):
        key = self.client_address[0]
        stamp = time.monotonic()
        with DB_LOCK:
            queue = RATE[key]
            while queue and queue[0] < stamp-3600:
                queue.popleft()
            if len(queue) >= limit:
                return False
            queue.append(stamp)
            return True
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            try:
                with db() as c:
                    c.execute("SELECT 1").fetchone()
                return self.response(200, {"status": "ok", "product": "EventPilot", "version": VERSION, "database": "SQLite", "llm": "unavailable - keyless activation dismissed", "gmail": "drafts only; OAuth optional", "time": now()})
            except Exception:
                return self.response(503, {"status": "error", "database": "unavailable"})
        if path == "/api/config":
            return self.response(200, {"googleClientId": os.environ.get("GOOGLE_CLIENT_ID", ""), "gmailScope": "https://www.googleapis.com/auth/gmail.compose", "engine": "Tool-driven agents; LLM unavailable", "replayAvailable": (DATA / "recording.json").exists()})
        if path.startswith("/api/runs/"):
            bits = path.strip("/").split("/")
            run = row_run(bits[2])
            if not run:
                return self.response(404, {"error": "Run not found"})
            if len(bits) == 3:
                return self.response(200, run)
            if bits[3] == "stream":
                return self.stream(run["id"])
            if bits[3] == "pdf" and run["pack"]:
                return self.response(200, pdf_bytes(run["pack"]), "application/pdf", {"Content-Disposition": 'attachment; filename="EventPilot-Event-Pack.pdf"'})
            if bits[3] == "eml" and run["pack"] and len(bits) == 5:
                try:
                    draft = run["pack"]["drafts"][int(bits[4])]
                    return self.response(200, email_bytes(draft), "message/rfc822", {"Content-Disposition": f'attachment; filename="EventPilot-draft-{int(bits[4])+1}.eml"'})
                except (ValueError, IndexError, KeyError):
                    return self.response(404, {"error": "Draft not found"})
        static = "index.html" if path == "/" or path.startswith("/run/") else path.lstrip("/")
        target = (ROOT / "public" / static).resolve()
        if not target.is_relative_to(ROOT / "public") or not target.is_file():
            return self.response(404, {"error": "Not found"})
        return self.response(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")
    def stream(self, run_id):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        last = 0
        try:
            for _ in range(3600):
                run = row_run(run_id)
                for event in run["trace"][last:]:
                    self.wfile.write(("event: trace\ndata: " + json.dumps(event) + "\n\n").encode())
                last = len(run["trace"])
                if run["status"] in ("complete", "failed"):
                    name = "complete" if run["status"] == "complete" else "failed"
                    self.wfile.write(("event: " + name + "\ndata: " + json.dumps({"id": run_id, "pack": run["pack"], "error": run["error"]}) + "\n\n").encode())
                    self.wfile.flush()
                    break
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                time.sleep(0.5)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        self.close_connection = True
    def do_POST(self):
        path = urlparse(self.path).path
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self.response(403, {"error": "Cross-origin writes are not permitted"})
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            return self.response(415, {"error": "JSON content type required"})
        try:
            value = self.body()
            if path == "/api/runs":
                if not self.allowed():
                    return self.response(429, {"error": "Hourly run limit reached; view a recorded run instead."})
                if value.get("mode") == "replay":
                    return self.replay()
                prompt = str(value.get("prompt", "")).strip()
                if not prompt or len(prompt) > 3000:
                    return self.response(400, {"error": "Provide an event prompt up to 3000 characters"})
                overrides = value.get("overrides") or {}
                if not isinstance(overrides, dict):
                    raise ValueError("overrides must be an object")
                roster = value.get("roster")
                sanitized_roster = public_roster(roster)
                from src.pipeline import parse_goal
                parse_goal(prompt, overrides)  # Reject invalid input before scheduling a run.
                run_id = secrets.token_urlsafe(18)
                with DB_LOCK, db() as c:
                    c.execute("INSERT INTO runs(id,status,prompt,trace,created_at,private_roster) VALUES (?,?,?,?,?,?)", (run_id, "running", prompt, "[]", now(), None))
                try:
                    POOL.submit(execute_run, run_id, prompt, overrides, sanitized_roster)
                except RuntimeError:
                    with DB_LOCK, db() as c:
                        c.execute("UPDATE runs SET status='failed',error=? WHERE id=?", ("Execution queue unavailable; retry after service restart.", run_id))
                    return self.response(503, {"id": run_id, "error": "Execution queue unavailable; no successful run is claimed."})
                return self.response(202, {"id": run_id, "status": "running"})
            bits = path.strip("/").split("/")
            if len(bits) == 4 and bits[:2] == ["api", "runs"] and bits[3] == "gmail-drafts":
                return self.gmail(bits[2], value)
            return self.response(404, {"error": "Route not found; no email send route exists"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.response(400, {"error": str(exc)[:200]})
        except Exception as exc:
            print("POST handler failure: " + type(exc).__name__, flush=True)
            return self.response(500, {"error": "Unexpected error; no email was sent"})
    def replay(self):
        target = DATA / "recording.json"
        if not target.exists():
            return self.response(409, {"error": "No real recorded run available yet; run an example first"})
        recording = json.loads(target.read_text(encoding="utf-8"))
        run_id = secrets.token_urlsafe(18)
        pack = recording["pack"]
        pack["mode"] = "replay"
        pack["recordedAt"] = recording["recordedAt"]
        pack["runId"] = run_id
        pack["replayNotice"] = "REPLAY OF A REAL RECORDED RUN. Not live research."
        replay_trace = [{**e, "mode": "replay", "message": "[Recorded event, not live] " + e["message"]} for e in recording["trace"]]
        with db() as c:
            c.execute("INSERT INTO runs(id,status,prompt,pack,trace,created_at,mode) VALUES (?,?,?,?,?,?,?)", (run_id, "complete", recording["prompt"], json.dumps(pack), json.dumps(replay_trace), now(), "replay"))
        return self.response(200, {"id": run_id, "status": "complete", "mode": "replay"})
    def gmail(self, run_id, value):
        run = row_run(run_id)
        if not run or not run["pack"]:
            return self.response(404, {"error": "Completed run not found"})
        if not os.environ.get("GOOGLE_CLIENT_ID"):
            return self.response(409, {"error": "Google OAuth is not configured. Use Open in Gmail, copy or .eml downloads. No Gmail drafts were created by this app.", "fallback": True})
        token = value.get("accessToken")
        if not isinstance(token, str) or not token or len(token) > 4096:
            return self.response(401, {"error": "A short-lived gmail.compose OAuth token is required", "fallback": True})
        drafts = run["pack"].get("drafts", [])
        selected = value.get("indices", [i for i, d in enumerate(drafts) if d.get("to")][:24])
        if not isinstance(selected, list) or not 1 <= len(selected) <= 24:
            raise ValueError("Select between 1 and 24 drafts")
        if any(not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(drafts) for i in selected):
            raise ValueError("Each selected draft index must exist")
        # gmail.compose already permits profile access; no additional OAuth scope.
        try:
            req = Request("https://gmail.googleapis.com/gmail/v1/users/me/profile", headers={"Authorization": "Bearer " + token})
            with urlopen(req, timeout=15) as resp:
                account = json.load(resp).get("emailAddress")
            if not account:
                raise ValueError("No verified mailbox identity")
            account_hash = hashlib.sha256(account.lower().encode()).hexdigest()
        except Exception:
            return self.response(401, {"error": "Could not verify the OAuth mailbox; no drafts created", "fallback": True})
        created, errors = [], []
        drafts = run["pack"].get("drafts", [])
        if run["pack"].get("validation", {}).get("errors"):
            return self.response(409, {"error": "Resolve Event Pack validation errors before creating drafts", "fallback": True})
        with GMAIL_LOCK:
            for i in dict.fromkeys(selected):
                if not isinstance(i, int) or isinstance(i, bool) or i < 0 or i >= len(drafts):
                    continue
                if not drafts[i].get("to") or drafts[i].get("demo"):
                    errors.append({"index": i, "error": "A verified appropriate recipient is required; use the blank-recipient compose fallback."})
                    continue
                raw_bytes = email_bytes(drafts[i])
                content_hash = hashlib.sha256(raw_bytes).hexdigest()
                with db() as c:
                    previous = c.execute("SELECT * FROM gmail_receipts WHERE run_id=? AND account_hash=? AND draft_index=?", (run_id, account_hash, i)).fetchone()
                    if previous:
                        if previous["status"] == "created":
                            stale = previous["content_hash"] != content_hash
                            created.append({"index": i, "draftId": previous["draft_id"], "subject": previous["subject"], "alreadyCreated": True, "contentChanged": stale})
                            if stale:
                                errors.append({"index": i, "error": "Saved plan changed since this Gmail draft was created. Review and update the existing draft manually; no duplicate created."})
                        else:
                            errors.append({"index": i, "error": "A previous attempt has an uncertain outcome. Check Gmail manually; automatic retry is blocked to avoid duplicates."})
                        continue
                    c.execute("INSERT INTO gmail_receipts(run_id,account_hash,draft_index,draft_id,subject,status,created_at,content_hash) VALUES (?,?,?,?,?,?,?,?)", (run_id, account_hash, i, None, drafts[i]["subject"], "attempting", now(), content_hash))
                raw = base64.urlsafe_b64encode(raw_bytes).decode().rstrip("=")
                req = Request("https://gmail.googleapis.com/gmail/v1/users/me/drafts", data=json.dumps({"message": {"raw": raw}}).encode(), headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method="POST")
                try:
                    with urlopen(req, timeout=15) as resp:
                        result = json.load(resp)
                    if not result.get("id"):
                        raise ValueError("Draft receipt missing")
                    with db() as c:
                        c.execute("UPDATE gmail_receipts SET draft_id=?,status='created' WHERE run_id=? AND account_hash=? AND draft_index=?", (result["id"], run_id, account_hash, i))
                    created.append({"index": i, "draftId": result["id"], "subject": drafts[i]["subject"]})
                except HTTPError as exc:
                    if 400 <= exc.code < 500:
                        with db() as c:
                            c.execute("DELETE FROM gmail_receipts WHERE run_id=? AND account_hash=? AND draft_index=? AND status='attempting'", (run_id, account_hash, i))
                    errors.append({"index": i, "status": exc.code, "error": "OAuth draft creation failed. Use compose fallback; no messages sent."})
                    if exc.code in (401, 403, 429) or exc.code >= 500:
                        break
                except Exception:
                    with db() as c:
                        c.execute("UPDATE gmail_receipts SET status='uncertain' WHERE run_id=? AND account_hash=? AND draft_index=?", (run_id, account_hash, i))
                    errors.append({"index": i, "error": "Draft creation outcome uncertain; check Gmail manually. Retry blocked to avoid duplicates."})
                    break
            if created:
                pack = row_run(run_id)["pack"]
                with db() as c:
                    count = c.execute("SELECT COUNT(*) FROM gmail_receipts WHERE run_id=? AND status='created'", (run_id,)).fetchone()[0]
                    pack.setdefault("metrics", {})["gmailDraftsCreated"] = count
                    c.execute("UPDATE runs SET pack=? WHERE id=?", (json.dumps(pack), run_id))
                emit(run_id, "Sponsorship Agent", "complete", "Gmail drafts.create", f"{len(created)} draft receipts verified for this mailbox; zero emails sent.")
        return self.response(200 if created else 502, {"created": created, "errors": errors, "sent": 0, "fallback": bool(errors)})


def process_due_rechecks(today=None):
    """Persist every due result and expose failures, missed jobs and re-planning."""
    today = today or datetime.now(MYT).date().isoformat()
    with db() as c:
        due = c.execute("SELECT * FROM rechecks WHERE due<=? AND status='pending' ORDER BY due", (today,)).fetchall()
    for row in due:
        result = {"checkedAt": now(), "due": row["due"], "daysBefore": row["offset"]}
        status = "failed"
        try:
            run = row_run(row["run_id"])
            pack = run["pack"] if run else None
            if not pack:
                raise ValueError("Saved Event Pack unavailable")
            chosen = pack.get("dateDecision", {}).get("chosen", {})
            event_date = chosen.get("date") if isinstance(chosen, dict) else chosen
            if not event_date:
                raise ValueError("Chosen date missing")
            if event_date < today:
                status = "missed"
                result["reason"] = "Event date already passed; no retrospective forecast invented"
                emit(run["id"], "Risk and Weather Agent", "missed", "SQLite scheduler", result["reason"], result)
            else:
                from src.weather import date_weather
                weather = date_weather(event_date, pack["goal"].get("location", "Subang Jaya"), emit=lambda a, s, t, m, data=None: emit(run["id"], a, s, t, m, data))
                result["weather"] = weather
                status = "complete" if weather.get("available") else "failed"
                pack["weather"] = weather
                pack.setdefault("weatherCheckHistory", []).append(result)
                for check in pack.get("rechecks", []):
                    if isinstance(check, dict) and (check.get("date") or check.get("due") or check.get("dueDate")) == row["due"]:
                        check.update(status=status, checkedAt=result["checkedAt"], result=weather)
                from src.pipeline import apply_weather_update
                pack = normalize_public_pack(apply_weather_update(pack, weather, emit=lambda a, s, t, m, data=None: emit(run["id"], a, s, t, m, data)))
                emit(run["id"], "Risk and Weather Agent", status, "Open-Meteo recheck", f"T-{row['offset']} check recorded; scheduled jobs require running hosting.", result)
                with db() as c:
                    c.execute("UPDATE runs SET pack=? WHERE id=?", (json.dumps(pack), run["id"]))
        except Exception as exc:
            status = "failed"
            result["error"] = str(exc)[:200]
            emit(row["run_id"], "Risk and Weather Agent", "failed", "SQLite scheduler", "Weather recheck failed; no successful update is claimed.", result)
        with db() as c:
            c.execute("UPDATE rechecks SET status=?,result=? WHERE run_id=? AND offset=?", (status, json.dumps(result), row["run_id"], row["offset"]))


def recheck_worker():
    """A sleeping/stopped host cannot run this scheduler; no guarantee is claimed."""
    while True:
        try:
            process_due_rechecks()
        except Exception as exc:
            print("Scheduler failure: " + type(exc).__name__, flush=True)
        time.sleep(60)

if __name__ == "__main__":
    initialize()
    threading.Thread(target=recheck_worker, daemon=True).start()
    port = int(os.environ.get("PORT", "3000"))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"EventPilot ready on {host}:{port}; SQLite persistence enabled", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
