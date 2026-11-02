import copy
import json
import os
import threading
from pathlib import Path

DEFAULTS = {
    "version": 1,
    "base_url": "",
    "auth_method": None,          # "token" | "oauth" | None
    "api_key": "",
    "oauth": {"access_token": "", "refresh_token": "", "expires_at": 0},
    "download_dir": "",
}


class Config:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.data = self._load()

    def _load(self):
        data = copy.deepcopy(DEFAULTS)
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            oauth = {**data["oauth"], **loaded.pop("oauth", {})}
            data.update(loaded)
            data["oauth"] = oauth
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass  # first run or corrupt file: start from defaults
        return data

    def save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            # 0o600: owner-only on POSIX (largely ignored on Windows)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)  # atomic

    def clear_credentials(self):
        self.data["auth_method"] = None
        self.data["api_key"] = ""
        self.data["oauth"] = copy.deepcopy(DEFAULTS["oauth"])
        self.save()