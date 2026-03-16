"""
Lightweight HTTP server for the Rekall Forensic Explorer.
Serves the single-page explorer UI and provides JSON API endpoints
that read from the local vault. No external dependencies.
"""
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from rekall.core.state_store import StateStore, resolve_vault_dir

_store: Optional[StateStore] = None


def _get_store() -> StateStore:
    global _store
    if _store is None:
        vault = resolve_vault_dir()
        _store = StateStore(vault)
    return _store


def _unified_events() -> List[Dict[str, Any]]:
    """Load all events from all streams into a unified list."""
    store = _get_store()
    events: List[Dict[str, Any]] = []

    for e in store._load_stream_raw("timeline", hot_only=False):
        etype = e.get("type", "note")
        events.append({
            "id": e.get("event_id", ""),
            "stream": "timeline",
            "type": "checkpoint" if etype == "milestone" else etype,
            "timestamp": e.get("timestamp", ""),
            "summary": e.get("summary", e.get("title", "")),
            "actor": _actor_id(e),
            "git_sha": e.get("git_sha"),
            "event_hash": e.get("event_hash"),
            "prev_hash": e.get("prev_hash"),
            "verified": e.get("event_hash") is not None,
            "related_ids": _extract_related(e),
            "raw": e,
        })

    for a in store._load_stream_raw("attempts", hot_only=False):
        outcome = str(a.get("outcome", "unknown")).lower()
        events.append({
            "id": a.get("attempt_id", ""),
            "stream": "attempts",
            "type": f"attempt_{outcome}",
            "timestamp": a.get("timestamp", ""),
            "summary": a.get("title") or a.get("hypothesis", ""),
            "detail": a.get("evidence", ""),
            "actor": _actor_id(a),
            "event_hash": a.get("event_hash"),
            "prev_hash": a.get("prev_hash"),
            "verified": a.get("event_hash") is not None,
            "related_ids": _extract_related(a),
            "raw": a,
        })

    for d in store._load_stream_raw("decisions", hot_only=False):
        status = d.get("status", "proposed")
        events.append({
            "id": d.get("decision_id", ""),
            "stream": "decisions",
            "type": f"decision_{status}",
            "timestamp": d.get("timestamp", ""),
            "summary": d.get("title", ""),
            "detail": d.get("rationale", ""),
            "actor": _actor_id(d),
            "event_hash": d.get("event_hash"),
            "prev_hash": d.get("prev_hash"),
            "verified": d.get("event_hash") is not None,
            "related_ids": _extract_related(d),
            "raw": d,
        })

    for w in store._load_stream_raw("work_items", hot_only=False):
        events.append({
            "id": w.get("event_id", w.get("work_item_id", "")),
            "stream": "work_items",
            "type": w.get("type", "work_item").lower().replace("work_item_", "wi_"),
            "timestamp": w.get("timestamp", ""),
            "summary": w.get("patch", {}).get("title", w.get("type", "")),
            "detail": w.get("patch", {}).get("status", ""),
            "actor": _actor_id(w),
            "event_hash": w.get("event_hash"),
            "prev_hash": w.get("prev_hash"),
            "verified": w.get("event_hash") is not None,
            "related_ids": _extract_related(w),
            "raw": w,
        })

    for h in store._load_stream_raw("head_moves", hot_only=False):
        events.append({
            "id": h.get("head_move_id", ""),
            "stream": "head_moves",
            "type": "head_move",
            "timestamp": h.get("timestamp", ""),
            "summary": h.get("reason", "HEAD moved"),
            "detail": f"to_event: {h.get('to_event_id', 'N/A')}, to_ts: {h.get('to_timestamp', 'N/A')}",
            "actor": _actor_id(h),
            "event_hash": h.get("event_hash"),
            "prev_hash": h.get("prev_hash"),
            "verified": h.get("event_hash") is not None,
            "related_ids": _extract_related(h),
            "raw": h,
        })

    for act in store._load_stream_raw("activity", hot_only=False):
        atype = act.get("type", act.get("action", "activity"))
        # Skip low-level activity that duplicates timeline events
        if atype in ("append", "create") and act.get("target_type") == "timeline":
            continue
        events.append({
            "id": act.get("activity_id", act.get("eval_id", act.get("event_id", ""))),
            "stream": "activity",
            "type": str(atype).lower().replace(" ", "_"),
            "timestamp": act.get("timestamp", ""),
            "summary": _activity_summary(act),
            "actor": _actor_id(act),
            "event_hash": act.get("event_hash"),
            "prev_hash": act.get("prev_hash"),
            "verified": act.get("event_hash") is not None,
            "related_ids": _extract_related(act),
            "raw": act,
        })

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    return events


def _actor_id(e: dict) -> str:
    actor = e.get("actor") or e.get("created_by") or e.get("performed_by") or {}
    if isinstance(actor, dict):
        return actor.get("actor_id", "unknown")
    return str(actor)


def _extract_related(e: dict) -> List[str]:
    ids = []
    for key in ("work_item_id", "decision_id", "attempt_id", "approval_id",
                "policy_eval_id", "target_id", "to_event_id"):
        val = e.get(key)
        if val:
            ids.append(val)
    return ids


def _activity_summary(act: dict) -> str:
    atype = act.get("type", act.get("action", ""))
    if atype == "PolicyEvaluation":
        return f"Policy: {act.get('action_type', '?')} -> {act.get('effect', '?')}"
    if atype == "CapabilityDenied":
        return f"Denied: {act.get('capability', '?')} for {act.get('action', '?')}"
    if atype == "ApprovalRequired":
        return f"Approval needed: {act.get('action', '?')}"
    if atype == "ApprovalGranted":
        return f"Approved: {act.get('approval_id', '?')}"
    target = act.get("target_type", "")
    action = act.get("action", atype)
    return f"{action} {target}".strip()


class ExplorerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress request logging

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, content: str):
        body = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            html_path = Path(__file__).parent / "index.html"
            self._send_html(html_path.read_text(encoding="utf-8"))

        elif path == "/api/events":
            events = _unified_events()
            # Optional filtering
            stream_filter = params.get("stream", [None])[0]
            type_filter = params.get("type", [None])[0]
            search = params.get("q", [None])[0]

            if stream_filter:
                events = [e for e in events if e["stream"] == stream_filter]
            if type_filter:
                events = [e for e in events if type_filter in e["type"]]
            if search:
                q = search.lower()
                events = [e for e in events if
                          q in e.get("summary", "").lower() or
                          q in e.get("id", "").lower() or
                          q in e.get("type", "").lower()]

            self._send_json(events)

        elif path == "/api/stats":
            from rekall.core.stats import compute_stats
            store = _get_store()
            self._send_json(compute_stats(store))

        elif path == "/api/verify":
            store = _get_store()
            results = {}
            for stream in ["timeline", "work_items", "decisions", "attempts", "activity", "head_moves"]:
                results[stream] = store.verify_stream_integrity(stream)
            self._send_json(results)

        elif path.startswith("/api/event/"):
            event_id = path.split("/api/event/")[1]
            events = _unified_events()
            match = next((e for e in events if e["id"] == event_id), None)
            if match:
                self._send_json(match)
            else:
                self._send_json({"error": "Event not found"}, 404)

        else:
            self.send_error(404)


def start_server(port: int = 7700, open_browser: bool = True):
    """Start the Forensic Explorer server."""
    global _store
    _store = None  # Reset to pick up latest vault

    server = HTTPServer(("127.0.0.1", port), ExplorerHandler)
    url = f"http://127.0.0.1:{port}"

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    print(f"Rekall Forensic Explorer running at {url}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("\nExplorer stopped.")
