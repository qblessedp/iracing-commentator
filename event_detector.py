from __future__ import annotations

from dataclasses import dataclass, field

BATTLE_GAP_SEC = 1.0
COOLDOWN_BATTLE_SEC = 30.0
STOPPED_POSITION_DELTA = 0.0005
STOPPED_MIN_TICKS = 4


@dataclass
class DetectorState:
    prev_positions: list[int] = field(default_factory=list)
    prev_on_pit: list[bool] = field(default_factory=list)
    prev_lap_dist_pct: list[float] = field(default_factory=list)
    prev_flags: set[str] = field(default_factory=set)
    prev_leader: int | None = None
    best_lap_time: float | None = None
    announced_milestones: set[str] = field(default_factory=set)
    battle_cooldowns: dict[tuple[int, int], float] = field(default_factory=dict)
    stopped_ticks: dict[int, int] = field(default_factory=dict)
    race_started: bool = False


def _driver_name(drivers: dict, car_idx: int) -> str:
    if isinstance(drivers, dict):
        return drivers.get(car_idx, f"Car {car_idx}")
    return f"Car {car_idx}"


class EventDetector:
    def __init__(self):
        self.state = DetectorState()

    def reset(self) -> None:
        self.state = DetectorState()

    def detect(self, snapshot: dict) -> list[dict]:
        if not snapshot:
            return []
        events: list[dict] = []
        drivers = snapshot.get("drivers") or {}
        positions = snapshot.get("positions") or []
        on_pit = snapshot.get("on_pit") or []
        lap_times = snapshot.get("lap_times") or []
        lap_dist_pct = snapshot.get("lap_dist_pct") or []
        estimated = snapshot.get("estimated_times") or []
        flags = set(snapshot.get("flags") or [])
        session_time = snapshot.get("session_time", 0.0) or 0.0
        laps_remain = snapshot.get("session_laps_remain", 0) or 0
        session_type = snapshot.get("session_type", "unknown")

        events.extend(self._detect_flags(flags, drivers))
        events.extend(self._detect_race_start(flags, session_type))
        events.extend(self._detect_overtakes(positions, drivers))
        events.extend(self._detect_pit(on_pit, drivers))
        events.extend(self._detect_fastest_lap(lap_times, drivers))
        events.extend(self._detect_lead_change(positions, drivers))
        events.extend(self._detect_battles(positions, estimated, drivers, session_time))
        events.extend(self._detect_stopped(lap_dist_pct, on_pit, drivers))
        events.extend(self._detect_laps_to_go(laps_remain, session_type))
        events.extend(self._detect_checkered(flags))

        self.state.prev_positions = list(positions)
        self.state.prev_on_pit = list(on_pit)
        self.state.prev_lap_dist_pct = list(lap_dist_pct)
        self.state.prev_flags = flags
        return events

    def _detect_flags(self, flags: set[str], drivers: dict) -> list[dict]:
        added = flags - self.state.prev_flags
        events = []
        significant = {
            "green", "yellow", "red", "checkered", "caution", "caution_waving",
            "yellow_waving", "blue", "white",
        }
        for f in added & significant:
            events.append({"type": "flag_change", "flag": f})
        return events

    def _detect_race_start(self, flags: set[str], session_type: str) -> list[dict]:
        if self.state.race_started:
            return []
        if session_type.lower().startswith("race") and "green" in flags:
            self.state.race_started = True
            return [{"type": "race_start"}]
        return []

    def _detect_overtakes(self, positions: list[int], drivers: dict) -> list[dict]:
        events = []
        prev = self.state.prev_positions
        if not prev:
            return events
        for idx, pos in enumerate(positions):
            if idx >= len(prev) or not pos or not prev[idx]:
                continue
            if pos < prev[idx]:
                events.append({
                    "type": "overtake",
                    "car_idx": idx,
                    "driver": _driver_name(drivers, idx),
                    "from_pos": prev[idx],
                    "to_pos": pos,
                })
        return events

    def _detect_pit(self, on_pit: list[bool], drivers: dict) -> list[dict]:
        events = []
        prev = self.state.prev_on_pit
        if not prev:
            return events
        for idx, pit in enumerate(on_pit):
            if idx >= len(prev):
                continue
            if pit and not prev[idx]:
                events.append({"type": "pit_entry", "car_idx": idx, "driver": _driver_name(drivers, idx)})
            elif not pit and prev[idx]:
                events.append({"type": "pit_exit", "car_idx": idx, "driver": _driver_name(drivers, idx)})
        return events

    def _detect_fastest_lap(self, lap_times: list[float], drivers: dict) -> list[dict]:
        events = []
        for idx, t in enumerate(lap_times):
            if not t or t <= 0:
                continue
            if self.state.best_lap_time is None or t < self.state.best_lap_time:
                self.state.best_lap_time = t
                events.append({
                    "type": "fastest_lap",
                    "car_idx": idx,
                    "driver": _driver_name(drivers, idx),
                    "time": round(t, 3),
                })
        return events

    def _detect_lead_change(self, positions: list[int], drivers: dict) -> list[dict]:
        if not positions:
            return []
        leader = None
        for idx, pos in enumerate(positions):
            if pos == 1:
                leader = idx
                break
        if leader is None:
            return []
        events = []
        if self.state.prev_leader is not None and leader != self.state.prev_leader:
            events.append({
                "type": "lead_change",
                "new_leader": leader,
                "new_driver": _driver_name(drivers, leader),
                "old_leader": self.state.prev_leader,
                "old_driver": _driver_name(drivers, self.state.prev_leader),
            })
        self.state.prev_leader = leader
        return events

    def _detect_battles(
        self, positions: list[int], estimated: list[float], drivers: dict, session_time: float
    ) -> list[dict]:
        if not positions or not estimated:
            return []
        ordered = []
        for idx, pos in enumerate(positions):
            if pos and pos > 0 and idx < len(estimated):
                ordered.append((pos, idx, estimated[idx]))
        ordered.sort()
        events = []
        for i in range(len(ordered) - 1):
            pos_a, idx_a, est_a = ordered[i]
            pos_b, idx_b, est_b = ordered[i + 1]
            if pos_b != pos_a + 1:
                continue
            gap = abs(est_b - est_a) if est_a and est_b else None
            if gap is None or gap > BATTLE_GAP_SEC:
                continue
            key = (idx_a, idx_b)
            last = self.state.battle_cooldowns.get(key)
            if last is not None and session_time - last < COOLDOWN_BATTLE_SEC:
                continue
            self.state.battle_cooldowns[key] = session_time
            events.append({
                "type": "battle",
                "leader_idx": idx_a,
                "leader_driver": _driver_name(drivers, idx_a),
                "chaser_idx": idx_b,
                "chaser_driver": _driver_name(drivers, idx_b),
                "position": pos_a,
                "gap": round(gap, 3),
            })
        return events

    def _detect_stopped(
        self, lap_dist_pct: list[float], on_pit: list[bool], drivers: dict
    ) -> list[dict]:
        events = []
        prev = self.state.prev_lap_dist_pct
        if not prev:
            return events
        for idx, pct in enumerate(lap_dist_pct):
            if idx >= len(prev) or idx >= len(on_pit):
                continue
            if on_pit[idx]:
                self.state.stopped_ticks[idx] = 0
                continue
            delta = abs(pct - prev[idx])
            if delta < STOPPED_POSITION_DELTA:
                self.state.stopped_ticks[idx] = self.state.stopped_ticks.get(idx, 0) + 1
                if self.state.stopped_ticks[idx] == STOPPED_MIN_TICKS:
                    events.append({
                        "type": "accident_suspected",
                        "car_idx": idx,
                        "driver": _driver_name(drivers, idx),
                    })
            else:
                self.state.stopped_ticks[idx] = 0
        return events

    def _detect_laps_to_go(self, laps_remain: int, session_type: str) -> list[dict]:
        if not session_type.lower().startswith("race") or laps_remain <= 0:
            return []
        events = []
        for milestone in (10, 5, 3, 1):
            key = f"laps_to_go_{milestone}"
            if laps_remain == milestone and key not in self.state.announced_milestones:
                self.state.announced_milestones.add(key)
                events.append({"type": "laps_to_go", "laps": milestone})
        return events

    def _detect_checkered(self, flags: set[str]) -> list[dict]:
        if "checkered" in flags and "checkered" not in self.state.prev_flags:
            return [{"type": "checkered"}]
        return []
