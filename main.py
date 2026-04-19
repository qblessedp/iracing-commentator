import threading
import time

import facts_provider
from gui import CommentatorGUI
from iracing_reader import IRacingReader
from event_detector import EventDetector
from ai_commentator import AICommentator
from tts_elevenlabs import TTSElevenLabs
from tts_edge import TTSEdge
from tts_sapi import TTSSapi
from config import LANGUAGES, LANGUAGE_GUIDANCE

POLL_INTERVAL_SEC = 0.5
SILENCE_THRESHOLD_SEC = 7.0
FILLER_COOLDOWN_SEC = 30.0


class CommentatorApp:
    def __init__(self):
        self.gui = CommentatorGUI(
            on_start=self.start,
            on_stop=self.stop,
            on_volume_change=self.set_volume,
        )
        self.worker_thread = None
        self.stop_flag = threading.Event()
        self.tts: TTSElevenLabs | TTSEdge | TTSSapi | None = None

    def set_volume(self, pct: int) -> None:
        """Live-update commentary volume (0-100). Safe to call with no worker running."""
        if self.tts is not None:
            self.tts.set_volume(max(0, min(100, int(pct))) / 100.0)

    def run(self) -> None:
        self.gui.mainloop()

    def start(self, cfg: dict) -> None:
        self.stop_flag.clear()
        self.worker_thread = threading.Thread(target=self._worker, args=(cfg,), daemon=True)
        self.worker_thread.start()

    def stop(self) -> None:
        self.stop_flag.set()
        self.gui.set_status("Disconnected", level="info")
        self.gui.log_line("Stopped.", tag="info")

    def _worker(self, cfg: dict) -> None:
        reader = IRacingReader()
        detector = EventDetector()
        commentator = AICommentator(cfg["text_provider"], cfg["text_api_key"])
        vol_pct = max(0, min(100, int(cfg.get("volume", 100))))
        tts_provider = (cfg.get("tts_provider") or "elevenlabs").lower().strip()
        if tts_provider == "edge":
            tts = TTSEdge(
                voice_id_1=cfg["voice_id_1"],
                voice_id_2=cfg["voice_id_2"],
                voice_id_3=cfg.get("voice_id_3", ""),
                voice_id_4=cfg.get("voice_id_4", ""),
                volume=vol_pct / 100.0,
            )
        elif tts_provider == "sapi":
            tts = TTSSapi(
                voice_id_1=cfg["voice_id_1"],
                voice_id_2=cfg["voice_id_2"],
                voice_id_3=cfg.get("voice_id_3", ""),
                voice_id_4=cfg.get("voice_id_4", ""),
                volume=vol_pct / 100.0,
            )
        else:
            tts = TTSElevenLabs(
                cfg["elevenlabs_api_key"],
                cfg["voice_id_1"],
                cfg["voice_id_2"],
                voice_id_3=cfg.get("voice_id_3", ""),
                voice_id_4=cfg.get("voice_id_4", ""),
                volume=vol_pct / 100.0,
            )
        self.tts = tts
        tts.start()
        self.gui.log_line(f"TTS: {tts_provider}", tag="info")
        lang_code = cfg["language"]
        language = LANGUAGES.get(lang_code, "English")
        guidance = LANGUAGE_GUIDANCE.get(lang_code, "")

        self.gui.set_status("Waiting for iRacing...", level="warn")
        self.gui.log_line(f"Language: {language}", tag="info")

        was_connected = False
        event_count = 0
        prev_ai_err: str | None = None
        prev_tts_err: str | None = None
        last_event_ts = time.monotonic()
        last_filler_ts = 0.0
        while not self.stop_flag.is_set():
            try:
                if not reader.ensure_connected():
                    if was_connected:
                        was_connected = False
                        self.gui.set_status("Reconnecting...", level="warn")
                        self.gui.log_line("iRacing disconnected, retrying...", tag="info")
                    time.sleep(POLL_INTERVAL_SEC)
                    continue

                if not was_connected:
                    was_connected = True
                    self.gui.set_status("Connected", level="ok")
                    self.gui.log_line("Connected to iRacing.", tag="info")

                snapshot = reader.get_snapshot()
                events = detector.detect(snapshot)
                if events:
                    event_count += len(events)
                    last_event_ts = time.monotonic()
                    result = commentator.generate(
                        events, snapshot.get("session_type", "Race"), language, guidance
                    )
                    if result["text"]:
                        self.gui.log_commentary(result["speaker"], result["text"])
                        tts.speak(result["text"], result["speaker"])
                else:
                    now = time.monotonic()
                    if (now - last_event_ts) > SILENCE_THRESHOLD_SEC and (
                        now - last_filler_ts
                    ) > FILLER_COOLDOWN_SEC:
                        subject = facts_provider.pick_filler_subject(snapshot)
                        if subject:
                            filler = commentator.generate_filler(
                                subject,
                                snapshot.get("session_type", "Race"),
                                language,
                                guidance,
                            )
                            if filler.get("text"):
                                self.gui.log_commentary(filler["speaker"], filler["text"])
                                tts.speak(filler["text"], filler["speaker"])
                                last_filler_ts = now

                # Surface provider errors (stored on .last_error) to the UI
                if commentator.last_error != prev_ai_err:
                    prev_ai_err = commentator.last_error
                    if commentator.last_error:
                        self.gui.log_error(f"AI: {commentator.last_error}")
                if tts.last_error != prev_tts_err:
                    prev_tts_err = tts.last_error
                    if tts.last_error:
                        self.gui.log_error(f"TTS: {tts.last_error}")
            except Exception as e:
                self.gui.log_error(f"{type(e).__name__}: {e}")
            time.sleep(POLL_INTERVAL_SEC)

        self.gui.log_line(f"Session events detected: {event_count}", tag="info")
        tts.stop()
        reader.disconnect()


if __name__ == "__main__":
    CommentatorApp().run()
