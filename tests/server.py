"""Tiny static server that serves HTML fixtures at YouTube-shaped URLs.

The content script decides what page it is on from location.pathname, so serving
fixtures at the same paths YouTube uses (/feed/subscriptions, /results, /watch, ...)
exercises the real routing logic.
"""
from __future__ import annotations

import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

FIXTURES = Path(__file__).parent / "fixtures"

# (path regex, fixture file). First match wins.
ROUTES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^/$"), "home.html"),
    (re.compile(r"^/feed/subscriptions/?$"), "subscriptions.html"),
    (re.compile(r"^/feed/history/?$"), "history.html"),
    (re.compile(r"^/feed/[^/]+/?$"), "feed.html"),
    (re.compile(r"^/results/?$"), "search.html"),
    (re.compile(r"^/watch/?$"), "watch.html"),
    (re.compile(r"^/shorts(/[A-Za-z0-9_-]+)?/?$"), "shorts.html"),
    (re.compile(r"^/@[^/]+/shorts/?$"), "channel_shorts.html"),
    (re.compile(r"^/@[^/]+(/videos|/featured)?/?$"), "channel.html"),
    (re.compile(r"^/playlist/?$"), "playlist.html"),
]


class FixtureHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep test output quiet
        pass

    def do_GET(self):  # noqa: N802 (http.server API)
        parts = urlsplit(self.path)
        path = parts.path
        if path.startswith("/static/"):
            self.path = path
            return super().do_GET()
        # ?fx=<name> serves fixtures/<name>.html at any YouTube-shaped path, so a feature can
        # have its own fixture without disturbing the shared ones.
        override = parse_qs(parts.query).get("fx", [None])[0]
        if override is not None:
            if not re.fullmatch(r"[a-z0-9_]+", override) or not (FIXTURES / f"{override}.html").is_file():
                return self.send_error(404)
            return self._send_html((FIXTURES / f"{override}.html").read_bytes())
        for pattern, name in ROUTES:
            if pattern.match(path):
                return self._send_html((FIXTURES / name).read_bytes())
        self.send_error(404)

    def _send_html(self, body: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def start(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    handler = partial(FixtureHandler, directory=str(FIXTURES))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://localhost:{server.server_address[1]}"


if __name__ == "__main__":
    srv, base = start(8765)
    print(f"Serving fixtures at {base} (Ctrl+C to stop)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
