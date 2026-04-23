"""Windows SAPI TTS backend (100% offline). Drop-in replacement for
TTSElevenLabs / TTSEdge.

Uses `pyttsx3`, which wraps the Windows Speech API. No network, no API
key, no cloud — everything runs locally against the voices installed in
Windows. Same public surface as the other backends so main.py / gui.py
can swap freely.

Voice IDs for this backend are SAPI voice *names* (substring match),
for example "David", "Zira", "Hazel", "Mark". Whatever is installed on
the user's Windows machine is what's available.
"""
from __future__ import annotations

import logging
import queue
import threading

logger = logging.getLogger(__name__)

# Default SAPI voice names — one per persona. These are the voices
# shipped with Windows 10/11 by default. Users can override per slot.
# Substring matching is used so "David" matches "Microsoft David Desktop".
DEFAULT_VOICE_1 = "David"   # play-by-play (US male)
DEFAULT_VOICE_2 = "Zira"    # color analyst (US female)
DEFAULT_VOICE_3 = "Mark"    # veteran (US male, calmer)
DEFAULT_VOICE_4 = "Hazel"   # hype (UK female, energetic-sounding)

# Rate tweaks per persona so each speaker has a distinct cadence even
# if the user only has one or two SAPI voices installed.
DEFAULT_RATE = {
    1: 195,  # play-by-play — brisk
    2: 175,  # color — conversational
    3: 165,  # veteran — measured
    4: 210,  # hype — faster/excited
}


class TTSSapi:
    """Windows SAPI TTS worker. Same interface as TTSElevenLabs / TTSEdge."""

    def __init__(
        self,
        voice_id_1: str,
        voice_id_2: str,
        voice_id_3: str = "",
        voice_id_4: str = "",
        volume: float = 1.0,
        api_key: str = "",  # unused, kept for signature parity
    ):
        self.api_key = ""  # SAPI is key-less
        self.voices = {
            1: (voice_id_1 or DEFAULT_VOICE_1).strip(),
            2: (voice_id_2 or DEFAULT_VOICE_2).strip(),
            3: (voice_id_3 or DEFAULT_VOICE_3).strip(),
            4: (voice_id_4 or DEFAULT_VOICE_4).strip(),
        }
        self._volume = max(0.0, min(1.0, float(volume)))
        self._queue: queue.Queue[tuple[str, int]] = queue.Queue(maxsize=8)
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self.last_error: str | None = None

    def set_volume(self, volume: float) -> None:
        """Set playback volume for commentary. Accepts 0.0-1.0."""
        self._volume = max(0.0, min(1.0, float(volume)))

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(("", 0))
        except queue.Full:
            pass

    def _resolve_voice(self, speaker: int) -> str:
        vid = self.voices.get(speaker, "")
        if vid:
            return vid
        return self.voices.get(1, "")

    def speak(self, text: str, speaker: int) -> None:
        if not text or speaker not in self.voices:
            return
        self.start()
        try:
            self._queue.put_nowait((text, speaker))
        except queue.Full:
            logger.warning("SAPI TTS queue full, dropping line")

    # ---- internals -------------------------------------------------

    @staticmethod
    def _match_voice_id(engine, name_hint: str) -> str | None:
        """Find an installed SAPI voice whose name contains the hint."""
        if not name_hint:
            return None
        hint = name_hint.lower()
        for v in engine.getProperty("voices"):
            if hint in (v.name or "").lower() or hint in (v.id or "").lower():
                return v.id
        return None

    def _configure(self, engine, speaker: int) -> None:
        voice_hint = self._resolve_voice(speaker)
        voice_id = self._match_voice_id(engine, voice_hint)
        if voice_id:
            try:
                engine.setProperty("voice", voice_id)
            except Exception:
                pass
        engine.setProperty("rate", DEFAULT_RATE.get(speaker, 180))
        # SAPI volume is 0.0-1.0; map current slider directly.
        engine.setProperty("volume", self._volume)

    def _run(self) -> None:
        # pyttsx3 engine must live entirely inside this thread — COM/SAPI
        # is not thread-safe across threads.
        #
        # Known pyttsx3/SAPI limitation: setProperty("voice", ...) only
        # takes effect reliably on a *fresh* engine instance. Reusing the
        # same engine and switching voices mid-session causes the voice
        # change to be silently ignored. Fix: reinit the engine whenever
        # the speaker changes so each persona always gets the right voice.
        import pyttsx3

        engine = None
        _last_speaker: int | None = None

        while not self._stop.is_set():
            try:
                text, speaker = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self._stop.is_set() or not text:
                continue
            try:
                if engine is None or speaker != _last_speaker:
                    # Tear down previous engine cleanly before reiniting.
                    if engine is not None:
                        try:
                            engine.stop()
                        except Exception:
                            pass
                    engine = pyttsx3.init()
                    self._configure(engine, speaker)
                    _last_speaker = speaker
                engine.say(text)
                engine.runAndWait()
                self.last_error = None
            except Exception as e:
                cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
                msg = f"{type(e).__name__}: {e}"
                if cause:
                    msg += f" [caused by {type(cause).__name__}: {cause}]"
                self.last_error = msg
                logger.warning("SAPI TTS error: %s", msg)
                # Reset engine on failure so the next call rebuilds cleanly.
                try:
                    if engine is not None:
                        engine.stop()
                except Exception:
                    pass
                engine = None
                _last_speaker = None

    def validate(self) -> tuple[bool, str]:
        """Check pyttsx3 is installed and at least one voice is available."""
        try:
            import pyttsx3
        except Exception as e:
            return False, f"pyttsx3 import failed: {e}"
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty("voices") or []
            try:
                engine.stop()
            except Exception:
                pass
            if not voices:
                return False, "No SAPI voices installed on this system"
            return True, f"OK ({len(voices)} voice(s) installed)"
        except Exception as e:
            cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
            msg = f"{type(e).__name__}: {e}"
            if cause:
                msg += f" [caused by {type(cause).__name__}: {cause}]"
            return False, msg

    @staticmethod
    def list_installed_voices() -> list[str]:
        """Return the friendly names of installed SAPI voices (best-effort)."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            names = [v.name for v in engine.getProperty("voices") or []]
            try:
                engine.stop()
            except Exception:
                pass
            return names
        except Exception:
            return []

    @staticmethod
    def list_all_voices() -> list[str]:
        """Return friendly names of ALL available voices: standard SAPI + Windows
        OneCore / neural voices (best-effort). OneCore voices live in the registry
        at HKLM\\SOFTWARE\\Microsoft\\Speech_OneCore\\Voices\\Tokens and are NOT
        surfaced by pyttsx3/SAPI5 — we read them directly via winreg."""
        names: list[str] = []

        # Standard SAPI voices via pyttsx3
        try:
            import pyttsx3
            engine = pyttsx3.init()
            for v in (engine.getProperty("voices") or []):
                name = v.name or ""
                if name and name not in names:
                    names.append(name)
            try:
                engine.stop()
            except Exception:
                pass
        except Exception:
            pass

        # Windows OneCore / neural voices from registry
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as root:
                i = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(root, i)
                        try:
                            with winreg.OpenKey(root, sub_name) as sub:
                                try:
                                    display, _ = winreg.QueryValueEx(sub, "")
                                except OSError:
                                    display = sub_name
                        except OSError:
                            display = sub_name
                        if display and display not in names:
                            names.append(display)
                        i += 1
                    except OSError:
                        break
        except Exception:
            pass

        return names
