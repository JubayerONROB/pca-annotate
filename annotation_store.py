"""Durable storage for annotation progress (Task 1.5 UI).

Streamlit Community Cloud runs on an EPHEMERAL filesystem: a restart, a redeploy, or
the app going to sleep wipes anything written to disk. For a 200-card task split across
annotators that is a real way to lose an afternoon of judgements, so progress is
mirrored into a private GitHub repo through the contents API.

Two layers, deliberately:

  local disk   always written first, atomically. Fast, and it is the source of truth
               within a session even when the network is down.
  GitHub       written after, when a token is configured. Survives restarts, and lets
               several annotators work from different machines while you watch both
               files land in one repo.

The GitHub layer degrades to a no-op rather than failing the app -- an annotator who
loses connectivity keeps labeling, and the sidebar shows the sync state honestly rather
than pretending everything is saved.

Credentials come from Streamlit secrets, never from the repo:

    [github]
    token  = "github_pat_..."     # fine-grained, contents:write, that repo only
    repo   = "owner/pca-annotate"
    branch = "main"
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API = "https://api.github.com"
TIMEOUT = 30


@dataclass
class SyncState:
    enabled: bool = False
    ok: bool = True
    detail: str = "local only"
    last_commit: str = ""


@dataclass
class GitHubStore:
    """Minimal contents-API client: read a file, write a file, remember its sha."""

    token: str
    repo: str
    branch: str = "main"
    _sha: dict[str, str] = field(default_factory=dict)

    def _request(self, method: str, path: str, payload: dict | None = None):
        request = urllib.request.Request(
            f"{API}{path}",
            method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "pca-annotate",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)

    # ---- reads ---------------------------------------------------------------

    def read_text(self, path: str) -> str | None:
        """File contents, or None when it does not exist yet."""
        try:
            data = self._request("GET", f"/repos/{self.repo}/contents/{path}"
                                        f"?ref={self.branch}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        self._sha[path] = data.get("sha", "")
        return base64.b64decode(data["content"]).decode("utf-8")

    def list_dir(self, path: str) -> list[str]:
        try:
            data = self._request("GET", f"/repos/{self.repo}/contents/{path}"
                                        f"?ref={self.branch}")
        except urllib.error.HTTPError:
            return []
        return [item["name"] for item in data if item.get("type") == "file"]

    # ---- writes --------------------------------------------------------------

    def write_text(self, path: str, text: str, message: str) -> str:
        """Create or update `path`. Returns the new commit sha."""
        payload = {
            "message": message,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        sha = self._sha.get(path)
        if sha:
            payload["sha"] = sha

        try:
            data = self._request("PUT", f"/repos/{self.repo}/contents/{path}", payload)
        except urllib.error.HTTPError as exc:
            # 409/422 mean our cached sha is stale -- someone else (or an earlier
            # container) wrote the file. Re-read to learn the current sha and retry
            # once, rather than silently dropping the annotator's work.
            if exc.code not in (409, 422):
                raise
            self.read_text(path)
            sha = self._sha.get(path)
            if sha:
                payload["sha"] = sha
            else:
                payload.pop("sha", None)
            data = self._request("PUT", f"/repos/{self.repo}/contents/{path}", payload)

        self._sha[path] = data["content"]["sha"]
        return data["commit"]["sha"][:7]


def store_from_secrets(secrets) -> GitHubStore | None:
    """Build a store from Streamlit secrets or the environment, else None.

    Accepts a [github] section, flat GITHUB_* keys, or environment variables, because
    Streamlit Cloud, a local secrets.toml and a self-hosted container all differ.
    """
    config: dict[str, str] = {}
    try:
        section = secrets.get("github", None)
        if section:
            config = {k: str(v) for k, v in dict(section).items()}
        else:
            for key in ("token", "repo", "branch"):
                value = secrets.get(f"GITHUB_{key.upper()}", None)
                if value:
                    config[key] = str(value)
    except Exception:                       # no secrets configured at all
        config = {}

    for key in ("token", "repo", "branch"):
        config.setdefault(key, os.environ.get(f"GITHUB_{key.upper()}", ""))

    if not config.get("token") or not config.get("repo"):
        return None
    return GitHubStore(token=config["token"], repo=config["repo"],
                       branch=config.get("branch") or "main")


def write_local(path: Path, text: str) -> None:
    """Atomic local write -- a crash mid-save must not truncate earlier work."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)
