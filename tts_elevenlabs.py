from __future__ import annotations

import io
import logging
import queue
import threading

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "eleven_multilingual_v2"
DEFAULT_FORMAT = "mp3_44100_128"


class TTSElevenLabs:
    def __init__(
        self,
        api_key: str,
        voice_id_1: str,
        voice_id_2: str,
        voice_id_3: str = "",
        voice_id_4: str = "",
        model: str = DEFAULT_MODEL,
        volume: float = 1.0,
    ):
        self.api_key = (api_key or "").strip()
        self.voices = {
            1: (voice_id_1 or "").strip(),
            2: (voice_id_2 or "").strip(),
            3: (voice_id_3 or "").strip(),
            4: (voice_id_4 or "").strip(),
        }
        self.model = model
        self._volume = max(0.0, min(1.0, float(volume)))
        self._queue: queue.Queue[tuple[str, int]] = queue.Queue(maxsize=8)
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._mixer_ready = False
        self._client = None
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
        """Return the voice ID for this speaker, falling back to voice_1
        when the slot is empty so speakers 3 and 4 still play something."""
        vid = self.voices.get(speaker, "")
        if vid:
            return vid
        return self.voices.get(1, "")

    def speak(self, text: str, speaker: int) -> None:
        if not text or speaker not in self.voices:
            return
        if not self._resolve_voice(speaker) or not self.api_key:
            logger.debug("speak skipped: missing voice_id or api_key")
            return
        self.start()
        try:
            self._queue.put_nowait((text, speaker))
        except queue.Full:
            logger.warning("TTS queue full, dropping line")

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
                self.last_error = f"{type(e).__name__}: {e}"
                logger.warning("TTS error: %s", e)

    def _get_client(self):
        if self._client is None:
            from elevenlabs.client import ElevenLabs
            self._client = ElevenLabs(api_key=self.api_key)
        return self._client

    def _synthesize(self, text: str, voice_id: str) -> bytes:
        client = self._get_client()
        audio_iter = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=self.model,
            output_format=DEFAULT_FORMAT,
        )
        return b"".join(audio_iter)

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
        if not self.api_key:
            return False, "No API key"
        try:
            client = self._get_client()
            voices = client.voices.search(page_size=1)
            _ = voices
            if not self.voices.get(1):
                return False, "Voice ID missing for Speaker 1 (play-by-play)"
            return True, "OK"
        except Exception as e:
            return False, f"API error: {e}"
