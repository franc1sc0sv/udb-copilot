"""Moodle web-service client (the same API the Moodle mobile app uses).

Auth is a mobile web-service token, created once from your username and
password (`udb moodle login`) and stored outside the repo with mode 600. In
cloud sessions set `MOODLE_TOKEN` instead. The password is never stored.
"""
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

from udb.config import settings

# httpx logs every request URL at INFO, and file URLs carry the token: never log them.
logging.getLogger("httpx").setLevel(logging.WARNING)

READ_RE = re.compile(r"^[a-z0-9]+_[a-z0-9_]*?(get|search)_")
NEVER = ("autologin", "tokens", "export_token")


class MissingCredentials(RuntimeError):
    pass


class MoodleError(RuntimeError):
    pass


def base_url() -> str:
    url = settings.get().institution.get("moodle_url")
    if not url:
        raise MoodleError("udb.yaml has no institution.moodle_url")
    return url.rstrip("/")


def token_path() -> Path:
    return settings.get().secrets / "moodle-token"


def read_token() -> str:
    from_env = os.environ.get("MOODLE_TOKEN")
    if from_env:
        return from_env.strip()
    if token_path().exists():
        return token_path().read_text(encoding="utf-8").strip()
    raise MissingCredentials("no Moodle token. Run `udb moodle login` "
                             "(or set MOODLE_TOKEN in cloud sessions).")


def fetch_token(user: str, password: str) -> str:
    """Exchange username and password for a web-service token. Nothing is stored here."""
    service = settings.get().institution.get("moodle_service", "moodle_mobile_app")
    response = httpx.post(f"{base_url()}/login/token.php",
                          data={"username": user, "password": password, "service": service},
                          timeout=30.0, follow_redirects=True)
    data = response.json()
    if "token" not in data:
        raise MoodleError(f"Moodle refused the login: {data.get('error', 'unknown error')}")
    return data["token"]


def store_token(token: str) -> Path:
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    path.write_text(token, encoding="utf-8")
    return path


class MoodleApi:
    def __init__(self, url: str, token: str):
        self.base = url.rstrip("/")
        self.token = token
        self.client = httpx.Client(timeout=30.0, follow_redirects=True)

    def call(self, function: str, **params) -> Any:
        # udb only reads: anything that is not a pure read (*_get_*, *_search_*) is
        # refused here, so no tool can submit, post or mark something as read.
        if not READ_RE.match(function) or any(word in function for word in NEVER):
            raise MoodleError(f"{function} is not a read-only call; refused")
        # The token goes in the POST body, never in the URL: URLs end up in
        # logs and in exception messages.
        data = {"wstoken": self.token, "moodlewsrestformat": "json", "wsfunction": function,
                **params}
        try:
            response = self.client.post(f"{self.base}/webservice/rest/server.php", data=data)
        except httpx.HTTPError as exc:
            raise MoodleError(f"{function}: {type(exc).__name__}") from None
        if response.status_code != 200:
            raise MoodleError(f"{function}: HTTP {response.status_code}")
        result = response.json()
        if isinstance(result, dict) and result.get("exception"):
            raise MoodleError(f"{function}: {result.get('message')}")
        return result

    def site_info(self) -> dict:
        return self.call("core_webservice_get_site_info")

    def course_contents(self, course_id: int) -> list[dict]:
        return self.call("core_course_get_contents", courseid=course_id)

    def submission_status(self, assign_id: int) -> dict:
        return self.call("mod_assign_get_submission_status", assignid=assign_id)

    def submission_info(self, assign_id: int) -> dict:
        """Status, uploaded files and grade of a submission (individual or team)."""
        data = self.submission_status(assign_id)
        last = data.get("lastattempt") or {}
        parts = [last.get(key) or {} for key in ("submission", "teamsubmission")]
        statuses = {p.get("status") for p in parts}
        files = [f["filename"] for p in parts for pl in p.get("plugins", [])
                 for fa in pl.get("fileareas", []) for f in fa.get("files", [])]
        grade = re.sub(r"&nbsp;|\s+", " ", (data.get("feedback") or {})
                       .get("gradefordisplay") or "").strip()
        if "submitted" in statuses:
            state = "submitted"
        else:
            state = "draft" if "draft" in statuses else "not-submitted"
        return {"status": state, "files": files, "grade": grade or None}

    def download(self, file_url: str, dest: Path) -> Path:
        separator = "&" if "?" in file_url else "?"
        with self.client.stream("GET", f"{file_url}{separator}token={self.token}") as response:
            if response.status_code != 200:
                raise MoodleError(f"HTTP {response.status_code} downloading {dest.name}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as fh:
                for block in response.iter_bytes():
                    fh.write(block)
        return dest

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def connect() -> MoodleApi:
    return MoodleApi(base_url(), read_token())


def files_in(contents: list[dict]) -> list[dict]:
    out = []
    for section in contents:
        for module in section.get("modules", []):
            for item in module.get("contents", []) or []:
                if item.get("type") != "file":
                    continue
                out.append({
                    "section": section.get("name", ""),
                    "section_id": section.get("id"),
                    "module": module.get("name", ""),
                    "modname": module.get("modname", ""),
                    "filename": item.get("filename"),
                    "fileurl": item.get("fileurl"),
                    "timemodified": item.get("timemodified"),
                    "filesize": item.get("filesize"),
                    "moodle_id": f"{module.get('id')}:{item.get('filename')}",
                })
    return out


def html_links_in(contents: list[dict]) -> list[dict]:
    """'url' modules that point at a static course-material HTML page."""
    out = []
    for section in contents:
        for module in section.get("modules", []):
            if module.get("modname") != "url":
                continue
            for item in module.get("contents", []) or []:
                url = item.get("fileurl") or ""
                if "/materiales_didacticos/" not in url or not url.endswith(".html"):
                    continue
                filename = url.rsplit("/", 1)[-1]
                out.append({"section": section.get("name", ""), "module": module.get("name", ""),
                            "filename": filename, "fileurl": url,
                            "moodle_id": f"{module.get('id')}:{filename}"})
    return out


def pause() -> None:
    time.sleep(float(settings.get().data.get("rate_limit_seconds", 1.0)))
