"""GitHub Release auto-updater.

Queries the public releases API for a newer tag, downloads the replacement
.exe, writes a helper .bat that waits for this process to exit, swaps the
executable, and relaunches. No auth required for public repos.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

APP_VERSION = "1.0.9"
GITHUB_REPO = "qblessedp/iracing-commentator"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "iRacingCommentator.exe"
USER_AGENT = f"iRacingCommentator/{APP_VERSION}"


def _norm(tag: str) -> tuple[int, ...]:
    """Normalize 'v1.0.6' or '1.0.6' -> (1, 0, 6)."""
    t = (tag or "").lstrip("vV").strip()
    parts = []
    for p in t.split("."):
        digits = "".join(c for c in p if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def fetch_latest() -> dict | None:
    """Return the latest release JSON or None on failure."""
    try:
        req = urllib.request.Request(RELEASES_API, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        logger.warning("Update check failed: %s", e)
        return None


def is_newer(latest_tag: str) -> bool:
    return _norm(latest_tag) > _norm(APP_VERSION)


def find_asset(release: dict) -> str | None:
    for a in release.get("assets", []) or []:
        if a.get("name") == ASSET_NAME:
            return a.get("browser_download_url")
    return None


def _download_once(url: str, dest: Path) -> tuple[int, int]:
    """Download `url` to `dest`. Returns (expected_size, actual_size).

    expected_size == 0 when the server omits Content-Length.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        expected = int(resp.headers.get("Content-Length", "0") or "0")
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)
    actual = dest.stat().st_size
    return expected, actual


def _download(url: str, dest: Path, attempts: int = 3) -> None:
    """Download with Content-Length validation and retry.

    Raises IOError if all attempts return a truncated file. Prevents the
    partial-download case that caused Python DLL load failures in v1.0.7.
    """
    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            expected, actual = _download_once(url, dest)
        except Exception as e:
            last_err = e
            logger.warning("Download attempt %d failed: %s", i, e)
            dest.unlink(missing_ok=True)
            if i < attempts:
                time.sleep(1.5 * i)
                continue
            raise
        if expected and actual != expected:
            logger.warning(
                "Download attempt %d truncated: got %d / %d bytes", i, actual, expected
            )
            dest.unlink(missing_ok=True)
            last_err = IOError(f"Truncated download: {actual}/{expected} bytes")
            if i < attempts:
                time.sleep(1.5 * i)
                continue
            raise last_err
        # success (or server omitted Content-Length and we got some bytes)
        if actual == 0:
            dest.unlink(missing_ok=True)
            last_err = IOError("Empty download (0 bytes)")
            if i < attempts:
                time.sleep(1.5 * i)
                continue
            raise last_err
        return
    # unreachable, but keeps type checkers happy
    if last_err:
        raise last_err


def _write_swap_script(new_exe: Path, current_exe: Path) -> Path:
    """Create a .bat that waits for the current process, swaps the exe, relaunches."""
    bat = Path(tempfile.gettempdir()) / "iracing_commentator_update.bat"
    content = (
        "@echo off\r\n"
        "setlocal\r\n"
        ":wait\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        f'move /y "{new_exe}" "{current_exe}" >nul 2>&1\r\n'
        "if errorlevel 1 goto wait\r\n"
        f'start "" "{current_exe}"\r\n'
        '(goto) 2>nul & del "%~f0"\r\n'
    )
    bat.write_text(content, encoding="ascii")
    return bat


def check_and_apply(on_status=None, confirm=None) -> tuple[bool, str]:
    """Check for a newer release and apply it.

    - on_status: optional callable(msg: str) for progress updates
    - confirm:   optional callable(latest_tag: str) -> bool to prompt user
    Returns (applied, message). If applied is True, the app will exit shortly.
    """
    def log(m: str) -> None:
        logger.info(m)
        if on_status:
            try:
                on_status(m)
            except Exception:
                pass

    if not getattr(sys, "frozen", False):
        return False, "Update only available in the packaged .exe build."

    log("Checking for updates...")
    release = fetch_latest()
    if release is None:
        return False, "Could not contact GitHub."
    tag = release.get("tag_name", "")
    if not is_newer(tag):
        return False, f"Already on latest version ({APP_VERSION})."

    asset_url = find_asset(release)
    if not asset_url:
        return False, f"Release {tag} has no {ASSET_NAME} asset."

    if confirm is not None:
        try:
            if not confirm(tag):
                return False, "Update cancelled by user."
        except Exception:
            return False, "Update prompt error."

    log(f"Downloading {tag}...")
    current_exe = Path(sys.executable).resolve()
    tmp_exe = current_exe.with_name(current_exe.stem + f".new-{tag}.exe")
    try:
        _download(asset_url, tmp_exe)
    except Exception as e:
        return False, f"Download failed: {type(e).__name__}: {e}"

    log("Swapping executable...")
    try:
        bat = _write_swap_script(tmp_exe, current_exe)
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat)],
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            close_fds=True,
        )
    except Exception as e:
        try:
            tmp_exe.unlink(missing_ok=True)
        except Exception:
            pass
        return False, f"Swap launch failed: {type(e).__name__}: {e}"

    log("Update ready - closing app to apply.")
    threading.Timer(0.8, lambda: os._exit(0)).start()
    return True, f"Updating to {tag}..."
