import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_commentator import AICommentator, _format_event, _select_events, EVENT_PRIORITY


def _patch(commentator: AICommentator, text: str) -> list[tuple[str, str]]:
    captured: list[tuple[str, str]] = []

    def fake(sys_p, usr_p):
        captured.append((sys_p, usr_p))
        return text

    commentator._call_provider = fake  # type: ignore[assignment]
    return captured


def test_format_event_variants():
    assert "Alice" in _format_event({"type": "overtake", "driver": "Alice", "from_pos": 5, "to_pos": 4})
    assert "fastest lap" in _format_event({"type": "fastest_lap", "driver": "Bob", "time": 91.2})
    assert "Checkered" in _format_event({"type": "checkered"})
    assert "lights" in _format_event({"type": "race_start"}).lower()


def test_select_events_orders_by_priority():
    events = [
        {"type": "pit_entry", "driver": "A"},
        {"type": "lead_change", "new_driver": "B", "old_driver": "C"},
        {"type": "overtake", "driver": "D"},
    ]
    selected = _select_events(events)
    assert selected[0]["type"] == "lead_change"
    assert selected[-1]["type"] == "pit_entry"


def test_generate_returns_empty_when_no_events():
    c = AICommentator("openai", "sk-test")
    _patch(c, "should not be called")
    result = c.generate([], "Race", "English")
    assert result == {"speaker": 0, "text": ""}


def test_generate_alternates_speakers():
    c = AICommentator("openai", "sk-test")
    _patch(c, "Into turn one, Alice goes wide!")
    r1 = c.generate([{"type": "overtake", "driver": "Alice", "from_pos": 2, "to_pos": 1}], "Race", "English")
    c._last_call = 0.0
    r2 = c.generate([{"type": "overtake", "driver": "Bob", "from_pos": 4, "to_pos": 3}], "Race", "English")
    assert r1["speaker"] == 1
    assert r2["speaker"] == 2


def test_rate_limit_blocks_second_call():
    c = AICommentator("openai", "sk-test")
    _patch(c, "Line one")
    c.generate([{"type": "overtake", "driver": "X", "from_pos": 2, "to_pos": 1}], "Race", "English")
    r2 = c.generate([{"type": "overtake", "driver": "Y", "from_pos": 3, "to_pos": 2}], "Race", "English")
    assert r2 == {"speaker": 0, "text": ""}


def test_session_tone_selection():
    c = AICommentator("openai", "sk-test")
    assert "qualifying" in c._session_tone("Qualifying").lower()
    assert "practice" in c._session_tone("Open Practice").lower()
    assert "race" in c._session_tone("Race").lower()
    assert "race" in c._session_tone("Unknown").lower()


def test_system_prompt_includes_persona_and_language():
    c = AICommentator("openai", "sk-test")
    p1 = c._system_prompt(1, "Race", "Portuguese")
    p2 = c._system_prompt(2, "Race", "Portuguese")
    assert "play-by-play" in p1
    assert "color commentator" in p2
    assert "Portuguese" in p1


def test_history_passed_to_user_prompt():
    c = AICommentator("openai", "sk-test")
    captured = _patch(c, "First line.")
    c.generate([{"type": "overtake", "driver": "X", "from_pos": 2, "to_pos": 1}], "Race", "English")
    c._last_call = 0.0
    c.generate([{"type": "fastest_lap", "driver": "Y", "time": 90.0}], "Race", "English")
    assert "First line." in captured[-1][1]


def test_provider_error_returns_empty():
    c = AICommentator("openai", "sk-test")

    def boom(sys_p, usr_p):
        raise RuntimeError("down")

    c._call_provider = boom  # type: ignore[assignment]
    result = c.generate([{"type": "checkered"}], "Race", "English")
    assert result == {"speaker": 0, "text": ""}


def test_unknown_provider_returns_empty():
    c = AICommentator("unknown", "sk-test")
    result = c.generate([{"type": "checkered"}], "Race", "English")
    assert result == {"speaker": 0, "text": ""}


def test_language_guidance_embedded_in_prompt():
    c = AICommentator("openai", "sk-test")
    p = c._system_prompt(1, "Race", "Portugues", "Usa boxes e gap, evita brasileirismos.")
    assert "Portugues" in p
    assert "Usa boxes e gap" in p


def test_language_guidance_absent_when_empty():
    c = AICommentator("openai", "sk-test")
    p = c._system_prompt(1, "Race", "English", "")
    assert "Language guidance" not in p


def test_generate_forwards_guidance_to_prompt():
    c = AICommentator("openai", "sk-test")
    captured = _patch(c, "Boxes agora para Hamilton!")
    c.generate(
        [{"type": "pit_entry", "driver": "Hamilton"}],
        "Race",
        "Portugues",
        guidance="Usa boxes em vez de pit lane.",
    )
    assert "boxes" in captured[-1][0].lower()


def test_priority_table_consistent():
    assert EVENT_PRIORITY["checkered"] > EVENT_PRIORITY["overtake"]
    assert EVENT_PRIORITY["lead_change"] > EVENT_PRIORITY["pit_entry"]
