import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests


class TokenAuth:
    def __init__(self, token):
        self.token = token

    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def ensure_fresh(self):
        pass

    def refresh(self):
        return False


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        self.server.result = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h3>Signed in. You can close this tab "
            b"and return to the app.</h3></body></html>"
        )

    def log_message(self, *args):
        pass


class OAuth:
    """Canvas OAuth2 (authorization-code flow) with a loopback redirect.
    `store` is config.data["oauth"]; `on_change` persists it."""

    def __init__(self, base_url, client_id, client_secret, store, on_change, port=53682):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.store = store
        self.on_change = on_change
        self.port = port
        self._lock = threading.RLock()

    @property
    def redirect_uri(self):
        return f"http://127.0.0.1:{self.port}/callback"

    def headers(self):
        return {"Authorization": f"Bearer {self.store.get('access_token', '')}", "User-Agent": "SpreeGrader/0.1"}

    def ensure_fresh(self):
        if time.time() > self.store.get("expires_at", 0) - 60:
            self.refresh()

    def _apply(self, d):
        self.store["access_token"] = d["access_token"]
        if d.get("refresh_token"):  # refresh responses usually omit it
            self.store["refresh_token"] = d["refresh_token"]
        self.store["expires_at"] = time.time() + int(d.get("expires_in", 3600))
        self.on_change()

    def _token_request(self, **data):
        return requests.post(
            f"{self.base_url}/login/oauth2/token",
            data={"client_id": self.client_id, "client_secret": self.client_secret, **data},
            timeout=30,
        )

    def refresh(self):
        with self._lock:
            rt = self.store.get("refresh_token")
            if not rt:
                return False
            try:
                r = self._token_request(grant_type="refresh_token", refresh_token=rt)
            except requests.RequestException:
                return False
            if not r.ok:
                return False
            self._apply(r.json())
            return True

    def authorize(self, timeout=300):
        """Blocking: opens the browser and waits for the redirect.
        Run it with asyncio.to_thread."""
        state = secrets.token_urlsafe(16)
        server = HTTPServer(("127.0.0.1", self.port), _CallbackHandler)
        server.timeout = 1
        server.result = None
        query = urlencode({
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "state": state,
        })
        webbrowser.open(f"{self.base_url}/login/oauth2/auth?{query}")
        deadline = time.monotonic() + timeout
        try:
            while server.result is None and time.monotonic() < deadline:
                server.handle_request()
        finally:
            server.server_close()

        result = server.result
        if result is None:
            raise TimeoutError("Timed out waiting for browser sign-in")
        if "error" in result:
            raise RuntimeError(f"Sign-in failed: {result.get('error_description', result['error'])}")
        if result.get("state") != state:
            raise RuntimeError("Sign-in failed: state mismatch")

        r = self._token_request(
            grant_type="authorization_code",
            redirect_uri=self.redirect_uri,
            code=result["code"],
        )
        if not r.ok:
            raise RuntimeError(f"Token exchange failed (HTTP {r.status_code})")
        with self._lock:
            self._apply(r.json())