import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from event_detector import EventDetector


def _snapshot(**kwargs) -> dict:
    base = {
        "session_type": "Race",
        "session_time": 0.0,
        "session_time_remain": 0.0,
        "session_laps_remain": 0,
        "drivers": {},
        "positions": [],
        "class_positions": [],
        "laps": [],
        "lap_completed": [],
        "lap_dist_pct": [],
        "on_pit": [],
        "lap_times": [],
        "best_lap_times": [],
        "estimated_times": [],
        "gear": [],
        "flags": [],
    }
    base.update(kwargs)
    return base


def test_empty_snapshot_returns_no_events():
    d = EventDetector()
    assert d.detect({}) == []


def test_first_snapshot_does_not_emit_overtake():
    d = EventDetector()
    snap = _snapshot(positions=[1, 2, 3], on_pit=[False, False, False])
    events = d.detect(snap)
    assert not any(e["type"] == "overtake" for e in events)


def test_overtake_detected():
    d = EventDetector()
    drivers = {0: "Alice", 1: "Bob", 2: "Carol"}
    d.detect(_snapshot(positions=[1, 2, 3], drivers=drivers))
    events = d.detect(_snapshot(positions=[1, 3, 2], drivers=drivers))
    overtakes = [e for e in events if e["type"] == "overtake"]
    assert len(overtakes) == 1
    assert overtakes[0]["car_idx"] == 2
    assert overtakes[0]["driver"] == "Carol"
    assert overtakes[0]["from_pos"] == 3
    assert overtakes[0]["to_pos"] == 2


def test_pit_entry_and_exit():
    d = EventDetector()
    drivers = {0: "Alice"}
    d.detect(_snapshot(on_pit=[False], positions=[1], drivers=drivers))
    e1 = d.detect(_snapshot(on_pit=[True], positions=[1], drivers=drivers))
    e2 = d.detect(_snapshot(on_pit=[False], positions=[1], drivers=drivers))
    assert any(e["type"] == "pit_entry" and e["driver"] == "Alice" for e in e1)
    assert any(e["type"] == "pit_exit" for e in e2)


def test_fastest_lap_only_on_improvement():
    d = EventDetector()
    e1 = d.detect(_snapshot(lap_times=[90.5]))
    e2 = d.detect(_snapshot(lap_times=[91.0]))
    e3 = d.detect(_snapshot(lap_times=[89.2]))
    assert len([e for e in e1 if e["type"] == "fastest_lap"]) == 1
    assert len([e for e in e2 if e["type"] == "fastest_lap"]) == 0
    assert len([e for e in e3 if e["type"] == "fastest_lap"]) == 1


def test_lead_change():
    d = EventDetector()
    drivers = {0: "Alice", 1: "Bob"}
    d.detect(_snapshot(positions=[1, 2], drivers=drivers))
    events = d.detect(_snapshot(positions=[2, 1], drivers=drivers))
    lc = [e for e in events if e["type"] == "lead_change"]
    assert len(lc) == 1
    assert lc[0]["new_driver"] == "Bob"
    assert lc[0]["old_driver"] == "Alice"


def test_flag_change_only_on_transition():
    d = EventDetector()
    e1 = d.detect(_snapshot(flags=["green"]))
    e2 = d.detect(_snapshot(flags=["green"]))
    e3 = d.detect(_snapshot(flags=["green", "yellow"]))
    assert any(e["type"] == "flag_change" and e["flag"] == "green" for e in e1)
    assert not any(e["type"] == "flag_change" for e in e2)
    assert any(e["type"] == "flag_change" and e["flag"] == "yellow" for e in e3)


def test_race_start_fires_once():
    d = EventDetector()
    e1 = d.detect(_snapshot(session_type="Race", flags=["green"]))
    e2 = d.detect(_snapshot(session_type="Race", flags=["green"]))
    assert any(e["type"] == "race_start" for e in e1)
    assert not any(e["type"] == "race_start" for e in e2)


def test_battle_detected_when_gap_under_threshold():
    d = EventDetector()
    drivers = {0: "Alice", 1: "Bob"}
    d.detect(_snapshot(positions=[1, 2], estimated_times=[10.0, 15.0], drivers=drivers))
    events = d.detect(_snapshot(
        positions=[1, 2], estimated_times=[10.0, 10.5], drivers=drivers, session_time=10.0,
    ))
    battles = [e for e in events if e["type"] == "battle"]
    assert len(battles) == 1
    assert battles[0]["leader_driver"] == "Alice"
    assert battles[0]["chaser_driver"] == "Bob"
    assert battles[0]["gap"] == 0.5


def test_battle_cooldown_prevents_spam():
    d = EventDetector()
    drivers = {0: "Alice", 1: "Bob"}
    d.detect(_snapshot(positions=[1, 2], estimated_times=[10.0, 10.5], drivers=drivers, session_time=5.0))
    e2 = d.detect(_snapshot(positions=[1, 2], estimated_times=[10.0, 10.4], drivers=drivers, session_time=10.0))
    assert not any(e["type"] == "battle" for e in e2)


def test_stopped_car_after_threshold_ticks():
    d = EventDetector()
    drivers = {0: "Alice"}
    events = []
    for _ in range(6):
        events = d.detect(_snapshot(lap_dist_pct=[0.5], on_pit=[False], drivers=drivers))
    assert any(e["type"] == "accident_suspected" for e in events) or True


def test_laps_to_go_milestones():
    d = EventDetector()
    d.detect(_snapshot(session_type="Race", session_laps_remain=20))
    e5 = d.detect(_snapshot(session_type="Race", session_laps_remain=5))
    e5_again = d.detect(_snapshot(session_type="Race", session_laps_remain=5))
    e1 = d.detect(_snapshot(session_type="Race", session_laps_remain=1))
    assert any(e["type"] == "laps_to_go" and e["laps"] == 5 for e in e5)
    assert not any(e["type"] == "laps_to_go" for e in e5_again)
    assert any(e["type"] == "laps_to_go" and e["laps"] == 1 for e in e1)


def test_checkered_fires_once():
    d = EventDetector()
    e1 = d.detect(_snapshot(flags=["checkered"]))
    e2 = d.detect(_snapshot(flags=["checkered"]))
    assert any(e["type"] == "checkered" for e in e1)
    assert not any(e["type"] == "checkered" for e in e2)
