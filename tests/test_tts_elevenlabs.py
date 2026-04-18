import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tts_elevenlabs import TTSElevenLabs


def _mock(tts: TTSElevenLabs) -> dict:
    calls = {"synth": [], "play": []}

    def fake_synth(text, voice_id):
        calls["synth"].append((text, voice_id))
        return b"FAKEAUDIO"

    def fake_play(audio):
        calls["play"].append(audio)

    tts._synthesize = fake_synth  # type: ignore[assignment]
    tts._play = fake_play  # type: ignore[assignment]
    return calls


def _wait_for(predicate, timeout=1.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_speak_ignores_empty_text():
    tts = TTSElevenLabs("sk-test", "v1", "v2")
    calls = _mock(tts)
    tts.speak("", 1)
    assert not _wait_for(lambda: calls["synth"], timeout=0.3)


def test_speak_ignores_unknown_speaker():
    tts = TTSElevenLabs("sk-test", "v1", "v2")
    calls = _mock(tts)
    tts.speak("hello", 99)
    assert not _wait_for(lambda: calls["synth"], timeout=0.3)


def test_speak_ignores_missing_voice_id():
    tts = TTSElevenLabs("sk-test", "", "")
    calls = _mock(tts)
    tts.speak("hello", 1)
    assert not _wait_for(lambda: calls["synth"], timeout=0.3)


def test_speak_ignores_missing_api_key():
    tts = TTSElevenLabs("", "v1", "v2")
    calls = _mock(tts)
    tts.speak("hello", 1)
    assert not _wait_for(lambda: calls["synth"], timeout=0.3)


def test_speak_enqueues_and_worker_synthesizes():
    tts = TTSElevenLabs("sk-test", "voice1", "voice2")
    calls = _mock(tts)
    tts.speak("Overtake!", 1)
    assert _wait_for(lambda: len(calls["synth"]) == 1)
    assert calls["synth"][0] == ("Overtake!", "voice1")
    assert calls["play"][0] == b"FAKEAUDIO"
    tts.stop()


def test_speak_routes_speaker_to_correct_voice():
    tts = TTSElevenLabs("sk-test", "voice1", "voice2")
    calls = _mock(tts)
    tts.speak("A", 1)
    tts.speak("B", 2)
    assert _wait_for(lambda: len(calls["synth"]) == 2)
    voice_ids = [c[1] for c in calls["synth"]]
    assert "voice1" in voice_ids and "voice2" in voice_ids
    tts.stop()


def test_error_in_synth_does_not_kill_worker():
    tts = TTSElevenLabs("sk-test", "voice1", "voice2")
    call_count = {"n": 0}

    def flaky(text, voice_id):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("boom")
        return b"OK"

    tts._synthesize = flaky  # type: ignore[assignment]
    tts._play = lambda audio: None  # type: ignore[assignment]
    tts.speak("first", 1)
    tts.speak("second", 1)
    assert _wait_for(lambda: call_count["n"] == 2)
    tts.stop()


def test_stop_halts_worker():
    tts = TTSElevenLabs("sk-test", "voice1", "voice2")
    _mock(tts)
    tts.speak("x", 1)
    tts.stop()
    assert _wait_for(lambda: not (tts._worker and tts._worker.is_alive()), timeout=2.0)


def test_validate_without_key():
    tts = TTSElevenLabs("", "v1", "v2")
    ok, msg = tts.validate()
    assert not ok
    assert "API key" in msg
