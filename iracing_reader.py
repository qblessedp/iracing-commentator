from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class IRacingReader:
    def __init__(self, reconnect_interval_sec: float = 2.0):
        self.ir = None
        self.connected = False
        self.reconnect_interval_sec = reconnect_interval_sec
        self._last_reconnect_attempt = 0.0

    def connect(self) -> bool:
        try:
            import irsdk
            self.ir = irsdk.IRSDK()
            ok = self.ir.startup()
            self.connected = bool(ok and self.ir.is_connected)
            return self.connected
        except Exception as e:
            logger.debug("connect failed: %s", e)
            self.connected = False
            return False

    def ensure_connected(self) -> bool:
        if self.connected and self.ir is not None and self.ir.is_connected:
            return True
        now = time.monotonic()
        if now - self._last_reconnect_attempt < self.reconnect_interval_sec:
            return False
        self._last_reconnect_attempt = now
        return self.connect()

    def disconnect(self) -> None:
        if self.ir is not None:
            try:
                self.ir.shutdown()
            except Exception:
                pass
        self.connected = False
        self.ir = None

    def _safe_get(self, key: str, default=None):
        try:
            val = self.ir[key]
            return default if val is None else val
        except Exception:
            return default

    def get_session_type(self) -> str:
        info = self._safe_get("SessionInfo")
        num = self._safe_get("SessionNum", 0)
        if not info or "Sessions" not in info:
            return "unknown"
        try:
            return info["Sessions"][num].get("SessionType", "unknown")
        except (IndexError, KeyError, TypeError):
            return "unknown"

    def get_drivers_map(self) -> dict[int, str]:
        info = self._safe_get("DriverInfo")
        if not info or "Drivers" not in info:
            return {}
        result = {}
        for d in info["Drivers"]:
            idx = d.get("CarIdx")
            name = d.get("UserName") or d.get("AbbrevName") or f"Car {idx}"
            if idx is not None:
                result[idx] = name
        return result

    def get_flag_state(self) -> list[str]:
        raw = self._safe_get("SessionFlags", 0) or 0
        flags = []
        mapping = {
            0x00000001: "checkered",
            0x00000002: "white",
            0x00000004: "green",
            0x00000008: "yellow",
            0x00000010: "red",
            0x00000020: "blue",
            0x00000040: "debris",
            0x00000080: "crossed",
            0x00000100: "yellow_waving",
            0x00000200: "one_lap_to_green",
            0x00000400: "green_held",
            0x00000800: "ten_to_go",
            0x00001000: "five_to_go",
            0x00002000: "random_waving",
            0x00004000: "caution",
            0x00008000: "caution_waving",
        }
        for bit, name in mapping.items():
            if raw & bit:
                flags.append(name)
        return flags

    def get_snapshot(self) -> dict:
        if not self.ensure_connected() or self.ir is None:
            return {}
        try:
            self.ir.freeze_var_buffer_latest()
        except Exception:
            return {}
        return {
            "session_type": self.get_session_type(),
            "session_time": self._safe_get("SessionTime", 0.0),
            "session_time_remain": self._safe_get("SessionTimeRemain", 0.0),
            "session_laps_remain": self._safe_get("SessionLapsRemainEx", 0),
            "drivers": self.get_drivers_map(),
            "positions": list(self._safe_get("CarIdxPosition", []) or []),
            "class_positions": list(self._safe_get("CarIdxClassPosition", []) or []),
            "laps": list(self._safe_get("CarIdxLap", []) or []),
            "lap_completed": list(self._safe_get("CarIdxLapCompleted", []) or []),
            "lap_dist_pct": list(self._safe_get("CarIdxLapDistPct", []) or []),
            "on_pit": list(self._safe_get("CarIdxOnPitRoad", []) or []),
            "lap_times": list(self._safe_get("CarIdxLastLapTime", []) or []),
            "best_lap_times": list(self._safe_get("CarIdxBestLapTime", []) or []),
            "estimated_times": list(self._safe_get("CarIdxEstTime", []) or []),
            "gear": list(self._safe_get("CarIdxGear", []) or []),
            "flags": self.get_flag_state(),
        }
