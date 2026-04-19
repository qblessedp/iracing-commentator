"""Microsoft Edge TTS backend. Drop-in replacement for TTSElevenLabs.

edge-tts is a free Python client that speaks to Microsoft's online Edge
Read Aloud voices. No API key is required. Same public surface as
TTSElevenLabs so main.py / gui.py can use either interchangeably.
"""
from __future__ import annotations

import asyncio
import io
import logging
import queue
import threading

logger = logging.getLogger(__name__)

# Default broadcast-style voices — one per persona, distinct feel each.
DEFAULT_VOICE_1 = "en-GB-RyanNeural"      # play-by-play (British male)
DEFAULT_VOICE_2 = "en-US-JennyNeural"     # color analyst (American female)
DEFAULT_VOICE_3 = "en-GB-ThomasNeural"    # veteran (British male older)
DEFAULT_VOICE_4 = "en-US-EricNeural"      # hype (American male energetic)


class TTSEdge:
    """Same interface as TTSElevenLabs: start/stop/speak/validate/set_volume."""

    def __init__(
        self,
        voice_id_1: str,
        voice_id_2: str,
        voice_id_3: str = "",
        voice_id_4: str = "",
        volume: float = 1.0,
        api_key: str = "",  # unused, kept for signature parity
    ):
        self.api_key = ""  # edge-tts is key-less
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
        self._mixer_ready = False
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
        if not self._resolve_voice(speaker):
            logger.debug("speak skipped: missing voice for speaker %s", speaker)
            return
        self.start()
        try:
            self._queue.put_nowait((text, speaker))
        except queue.Full:
            logger.warning("Edge TTS queue full, dropping line")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                text, speaker = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self._stop.is_set() or not text:
                continue
            try:
                audio = self._synthesize(text, self._resolve_voice(speaker))
                if audio:
                    self._play(audio)
                    self.last_error = None
            except Exception as e:
                cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
                msg = f"{type(e).__name__}: {e}"
                if cause:
                    msg += f" [caused by {type(cause).__name__}: {cause}]"
                self.last_error = msg
                logger.warning("Edge TTS error: %s", msg)

    def _synthesize(self, text: str, voice: str) -> bytes:
        import edge_tts

        async def _collect() -> bytes:
            communicate = edge_tts.Communicate(text, voice)
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        return asyncio.run(_collect())

    def _ensure_mixer(self) -> None:
        if self._mixer_ready:
            return
        import pygame
        pygame.mixer.init()
        self._mixer_ready = True

    def _play(self, audio_bytes: bytes) -> None:
        import pygame
        self._ensure_mixer()
        sound = pygame.mixer.Sound(io.BytesIO(audio_bytes))
        sound.set_volume(self._volume)
        channel = sound.play()
        if channel is None:
            return
        while channel.get_busy() and not self._stop.is_set():
            pygame.time.wait(50)

    def validate(self) -> tuple[bool, str]:
        """Quick sanity check: confirm edge-tts installed and voices resolve."""
        try:
            import edge_tts  # noqa: F401
        except Exception as e:
            return False, f"edge-tts import failed: {e}"
        missing = [s for s, v in self.voices.items() if not v]
        if missing:
            return False, f"Voice names missing for speaker(s) {missing}"
        # Synthesize a tiny sample to confirm the voice name is valid online
        try:
            sample = self._synthesize("test", self.voices[1])
            if not sample:
                return False, "Edge TTS returned empty audio"
            return True, "OK"
        except Exception as e:
            cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
            msg = f"{type(e).__name__}: {e}"
            if cause:
                msg += f" [caused by {type(cause).__name__}: {cause}]"
            return False, msg
