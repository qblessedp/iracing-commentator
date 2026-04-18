"""E2E integration: snapshot -> EventDetector -> AICommentator -> TTS queue.

Uses mocks for irsdk / AI provider / ElevenLabs to exercise the full pipeline
wiring without real network or shared memory.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_commentator import AICommentator
from event_detector import EventDetector
from tts_elevenlabs import TTSElevenLabs


DRIVERS = {0: "Hamilton", 1: "Verstappen", 2: "Leclerc"}


def _snap(
    *,
    t: float,
    positions: list[int],
    on_pit: list[bool] | None = None,
    best: list[float] | None = None,
    flags: list[str] | None = None,
    session_type: str = "Race",
    laps_remain: int = 20,
) -> dict:
    n = len(positions)
    return {
        "session_type": session_type,
        "session_time": t,
        "session_time_remain": 3600.0 - t,
        "session_laps_remain": laps_remain,
        "drivers": DRIVERS,
        "positions": positions,
        "class_positions": positions,
        "laps": [5] * n,
        "lap_completed": [5] * n,
        "lap_dist_pct": [0.5] * n,
        "on_pit": on_pit or [False] * n,
        "lap_times": [90.0] * n,
        "best_lap_times": best or [90.0] * n,
        "estimated_times": [45.0] * n,
        "gear": [5] * n,
        "flags": flags or ["green"],
    }


def test_pipeline_overtake_to_commentary_and_tts():
    detector = EventDetector()
    commentator = AICommentator("openai", "sk-test")
    commentator._call_provider = lambda s, u: "Hamilton takes P1 from Verstappen!"  # type: ignore[assignment]

    spoken: list[tuple[str, int]] = []
    tts = TTSElevenLabs("key", "v1", "v2")
    current_speaker = {"v": 0}

    def fake_synth(text: str, voice_id: str) -> bytes:
        spk = 1 if voice_id == "v1" else 2
        current_speaker["v"] = spk
        spoken.append((text, spk))
        return b"FAKE"

    tts._synthesize = fake_synth  # type: ignore[assignment]
    tts._play = lambda audio: None  # type: ignore[assignment]
    tts.start()

    detector.detect(_snap(t=1.0, positions=[2, 1, 3]))
    events = detector.detect(_snap(t=2.0, positions=[1, 2, 3]))

    assert any(e["type"] == "overtake" for e in events)

    result = commentator.generate(events, "Race", "English")
    assert result["speaker"] in (1, 2)
    assert "Hamilton" in result["text"]

    tts.speak(result["text"], result["speaker"])
    for _ in range(20):
        if spoken:
            break
        time.sleep(0.05)
    tts.stop()

    assert spoken, "TTS worker should have consumed one item"
    assert spoken[0] == (result["text"], result["speaker"])


def test_pipeline_flag_change_then_checkered():
    detector = EventDetector()
    commentator = AICommentator("openai", "sk-test")
    commentator._call_provider = lambda s, u: "And it's the checkered flag!"  # type: ignore[assignment]

    detector.detect(_snap(t=0.5, positions=[1, 2, 3], flags=["green"]))
    events = detector.detect(_snap(t=1.5, positions=[1, 2, 3], flags=["checkered"]))

    types = {e["type"] for e in events}
    assert "checkered" in types

    result = commentator.generate(events, "Race", "English")
    assert result["text"]
    assert result["speaker"] in (1, 2)


def test_pipeline_rate_limit_suppresses_second_call():
    detector = EventDetector()
    commentator = AICommentator("openai", "sk-test")
    calls = {"n": 0}

    def provider(s, u):
        calls["n"] += 1
        return f"line {calls['n']}"

    commentator._call_provider = provider  # type: ignore[assignment]

    detector.detect(_snap(t=1.0, positions=[2, 1, 3]))
    evts_a = detector.detect(_snap(t=2.0, positions=[1, 2, 3]))
    r1 = commentator.generate(evts_a, "Race", "English")

    evts_b = detector.detect(_snap(t=2.5, positions=[2, 1, 3]))
    r2 = commentator.generate(evts_b, "Race", "English")

    assert r1["text"] == "line 1"
    assert r2 == {"speaker": 0, "text": ""}
    assert calls["n"] == 1


def test_pipeline_no_events_no_ai_call():
    detector = EventDetector()
    commentator = AICommentator("openai", "sk-test")
    called = {"n": 0}

    def provider(s, u):
        called["n"] += 1
        return "x"

    commentator._call_provider = provider  # type: ignore[assignment]

    detector.detect(_snap(t=1.0, positions=[1, 2, 3]))
    events = detector.detect(_snap(t=2.0, positions=[1, 2, 3]))

    assert events == []
    result = commentator.generate(events, "Race", "English")
    assert result == {"speaker": 0, "text": ""}
    assert called["n"] == 0
