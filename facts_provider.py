"""Curated driver/track facts + iRacing YAML merge, used for silence-filler.

Loads JSON files once at import. Public API:
    get_track_facts(track_name) -> dict | None
    get_driver_facts(driver_name, yaml_data=None) -> dict
    pick_filler_subject(session_state) -> dict | None

`pick_filler_subject` returns {"kind": "driver"|"track", "data": {...}} or None
if nothing usable is available. Alternates kinds and keeps a short TTL cache
to avoid repeating the same subject.
"""
from __future__ import annotations

import json
import logging
import random
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    # PyInstaller onefile: data is extracted under sys._MEIPASS
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = Path(base) / "data"
        if p.exists():
            return p
    return Path(__file__).resolve().parent / "data"


def _load_json(name: str) -> dict:
    path = _data_dir() / name
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("facts_provider: could not load %s: %s", name, e)
        return {}


_TRACK_FACTS: dict = {k: v for k, v in _load_json("track_facts.json").items() if not k.startswith("_")}
_DRIVER_FACTS: dict = {k: v for k, v in _load_json("driver_facts.json").items() if not k.startswith("_")}

_RECENT_TTL_SEC = 300.0  # 5 minutes
_recent_subjects: dict[str, float] = {}
_last_kind: str | None = None


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _prune_recent(now: float) -> None:
    stale = [k for k, ts in _recent_subjects.items() if now - ts > _RECENT_TTL_SEC]
    for k in stale:
        _recent_subjects.pop(k, None)


def _mark_recent(key: str) -> None:
    _recent_subjects[key] = time.monotonic()


def _is_recent(key: str) -> bool:
    return key in _recent_subjects


def get_track_facts(track_name: str) -> dict | None:
    """Look up curated facts for a track. Matches on slug key OR the 'name' field."""
    if not track_name:
        return None
    q = _norm(track_name)
    if q in _TRACK_FACTS:
        return dict(_TRACK_FACTS[q])
    slug = q.replace(" ", "_").replace("-", "_")
    if slug in _TRACK_FACTS:
        return dict(_TRACK_FACTS[slug])
    for k, v in _TRACK_FACTS.items():
        if k in q or q in k:
            return dict(v)
        name = _norm(v.get("name", ""))
        if name and (name in q or q in name):
            return dict(v)
    return None


def get_driver_facts(driver_name: str, yaml_data: dict | None = None) -> dict:
    """Merge iRacing YAML driver entry with curated JSON (if found)."""
    q = _norm(driver_name)
    merged: dict = {}
    if yaml_data:
        for key in ("CarNumber", "TeamName", "IRating", "LicString", "UserName", "AbbrevName"):
            val = yaml_data.get(key)
            if val not in (None, ""):
                merged[key.lower()] = val
    merged.setdefault("name", driver_name)

    curated = _DRIVER_FACTS.get(q)
    if curated is None:
        for k, v in _DRIVER_FACTS.items():
            if k in q or q in k:
                curated = v
                break
    if curated:
        for fk, fv in curated.items():
            merged[fk] = fv
    return merged


def _pick_driver_subject(session_state: dict) -> dict | None:
    drivers = session_state.get("drivers") or {}
    positions = session_state.get("positions") or []
    on_pit = session_state.get("on_pit") or []
    if not drivers:
        return None

    def pos_of(idx: int) -> int:
        try:
            p = positions[idx]
            return int(p) if p and p > 0 else 999
        except (IndexError, TypeError, ValueError):
            return 999

    def on_pit_of(idx: int) -> bool:
        try:
            return bool(on_pit[idx])
        except (IndexError, TypeError):
            return False

    items = list(drivers.items())
    leader = [i for i, _ in items if pos_of(i) == 1]
    rest = [i for i, _ in items if pos_of(i) != 1 and not on_pit_of(i)]
    random.shuffle(rest)
    order = leader + rest
    if not order:
        order = [i for i, _ in items]

    for idx in order:
        name = drivers.get(idx)
        if not name:
            continue
        key = f"driver:{_norm(name)}"
        if _is_recent(key):
            continue
        yaml_entry = (session_state.get("drivers_yaml") or {}).get(idx)
        data = get_driver_facts(name, yaml_entry)
        has_narrative = any(data.get(f) for f in ("known_for", "fun_fact", "irating_peak", "irating"))
        has_meta = any(data.get(f) for f in ("teamname", "carnumber"))
        if not (has_narrative or has_meta):
            continue
        _mark_recent(key)
        return {"kind": "driver", "data": data}
    return None


def _pick_track_subject(session_state: dict) -> dict | None:
    track_name = session_state.get("track_name") or session_state.get("track") or ""
    facts = get_track_facts(track_name)
    if not facts:
        return None
    key = f"track:{_norm(facts.get('name', track_name))}"
    if _is_recent(key):
        return None
    _mark_recent(key)
    return {"kind": "track", "data": facts}


def pick_filler_subject(session_state: dict) -> dict | None:
    """Pick a filler subject, alternating driver/track and avoiding repeats."""
    global _last_kind
    now = time.monotonic()
    _prune_recent(now)

    order = ["track", "driver"] if _last_kind == "driver" else ["driver", "track"]
    for kind in order:
        picker = _pick_driver_subject if kind == "driver" else _pick_track_subject
        subj = picker(session_state)
        if subj:
            _last_kind = subj["kind"]
            return subj
    return None


def reset_cache() -> None:
    """Test helper: clear recent-subjects state."""
    global _last_kind
    _recent_subjects.clear()
    _last_kind = None
