from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MIN_INTERVAL_SEC = 2.5
MAX_HISTORY_LINES = 6
MAX_EVENTS_PER_CALL = 5
EVENT_PRIORITY = {
    "checkered": 100,
    "race_start": 95,
    "accident_suspected": 90,
    "lead_change": 85,
    "flag_change": 80,
    "laps_to_go": 75,
    "fastest_lap": 70,
    "overtake": 60,
    "battle": 55,
    "pit_exit": 40,
    "pit_entry": 35,
}

SESSION_TONE = {
    "practice": (
        "Practice session: analytical, technical, relaxed. "
        "Focus on setup work, consistency, sector times, who's testing what. "
        "Avoid drama."
    ),
    "qualifying": (
        "Qualifying session: tense, competitive, lap-by-lap focus. "
        "Emphasize purple sectors, pole battles, final attempts, traffic drama."
    ),
    "race": (
        "Race session: dramatic, energetic, full broadcast narrative. "
        "Emphasize battles, strategy, tyre wear, overtakes, lap counts."
    ),
}

SPEAKER_PERSONA = {
    1: (
        "lead play-by-play commentator. Drive the narrative, call the action as it happens, "
        "keep pace high. Think David Croft — urgent, precise, crisp."
    ),
    2: (
        "color commentator and analyst. React, add context, insight, and light humor. "
        "Think Martin Brundle — observational, knowing, occasional dry wit."
    ),
}


@dataclass
class CommentaryResult:
    speaker: int
    text: str

    def as_dict(self) -> dict:
        return {"speaker": self.speaker, "text": self.text}


def _format_event(e: dict) -> str:
    t = e.get("type", "unknown")
    if t == "overtake":
        return f"{e.get('driver','?')} overtook for P{e.get('to_pos','?')} (was P{e.get('from_pos','?')})"
    if t == "pit_entry":
        return f"{e.get('driver','?')} entered the pits"
    if t == "pit_exit":
        return f"{e.get('driver','?')} exited the pits"
    if t == "fastest_lap":
        return f"{e.get('driver','?')} set the fastest lap at {e.get('time','?')}s"
    if t == "lead_change":
        return f"{e.get('new_driver','?')} took the lead from {e.get('old_driver','?')}"
    if t == "flag_change":
        return f"{e.get('flag','?')} flag is out"
    if t == "race_start":
        return "Lights out, the race has begun"
    if t == "battle":
        return (
            f"Battle for P{e.get('position','?')}: "
            f"{e.get('leader_driver','?')} vs {e.get('chaser_driver','?')} "
            f"({e.get('gap','?')}s apart)"
        )
    if t == "accident_suspected":
        return f"{e.get('driver','?')} appears to be stopped on track"
    if t == "laps_to_go":
        return f"{e.get('laps','?')} laps to go"
    if t == "checkered":
        return "Checkered flag"
    return str(e)


def _select_events(events: list[dict]) -> list[dict]:
    if not events:
        return []
    ranked = sorted(events, key=lambda e: EVENT_PRIORITY.get(e.get("type", ""), 0), reverse=True)
    return ranked[:MAX_EVENTS_PER_CALL]


class AICommentator:
    def __init__(self, provider: str, api_key: str, model: str | None = None):
        self.provider = (provider or "").lower().strip()
        self.api_key = (api_key or "").strip()
        self.model = model
        self._turn = 1
        self._history: deque[str] = deque(maxlen=MAX_HISTORY_LINES)
        self._last_call = 0.0
        self.last_error: str | None = None
        self._template = None
        if self.provider == "template":
            from templates import TemplateCommentator
            self._template = TemplateCommentator()

    def _next_speaker(self) -> int:
        s = self._turn
        self._turn = 2 if s == 1 else 1
        return s

    def _session_tone(self, session_type: str) -> str:
        key = (session_type or "").lower()
        for s in ("qualifying", "practice", "race"):
            if s in key:
                return SESSION_TONE[s]
        return SESSION_TONE["race"]

    def _system_prompt(self, speaker: int, session_type: str, language: str, guidance: str = "") -> str:
        persona = SPEAKER_PERSONA[speaker]
        tone = self._session_tone(session_type)
        guidance_block = f"\nLanguage guidance: {guidance}" if guidance else ""
        return (
            f"You are the {persona}\n"
            f"{tone}\n"
            f"Respond in {language}. One line only, under 22 words. "
            f"Do not invent events not in the input. Do not repeat prior commentary. "
            f"No intros, no sign-offs, just the broadcast line."
            f"{guidance_block}"
        )

    def _user_prompt(self, events: list[dict]) -> str:
        lines = [f"- {_format_event(e)}" for e in events]
        history_block = ""
        if self._history:
            history_block = "\nRecent commentary (do not repeat):\n" + "\n".join(
                f"- {h}" for h in self._history
            )
        return (
            "Current events:\n" + "\n".join(lines) + history_block +
            "\n\nGive one broadcast line reacting to the most important event."
        )

    def generate(self, events: list[dict], session_type: str, language: str, guidance: str = "") -> dict:
        now = time.monotonic()
        if now - self._last_call < MIN_INTERVAL_SEC:
            return {"speaker": 0, "text": ""}
        selected = _select_events(events)
        if not selected:
            return {"speaker": 0, "text": ""}

        speaker = self._next_speaker()
        # Template provider: skip LLM, pick from curated phrase pools
        if self.provider == "template" and self._template is not None:
            try:
                text = self._template.generate(selected[0], language)
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                return {"speaker": 0, "text": ""}
            text = (text or "").strip()
            if not text:
                self.last_error = "template returned empty"
                return {"speaker": 0, "text": ""}
            self.last_error = None
            self._history.append(text)
            self._last_call = now
            return CommentaryResult(speaker=speaker, text=text).as_dict()

        sys_p = self._system_prompt(speaker, session_type, language, guidance)
        usr_p = self._user_prompt(selected)
        try:
            text = self._call_provider(sys_p, usr_p)
        except Exception as e:
            cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
            msg = f"{type(e).__name__}: {e}"
            if cause:
                msg += f" [caused by {type(cause).__name__}: {cause}]"
            self.last_error = msg
            logger.warning("AI provider error: %s", msg)
            return {"speaker": 0, "text": ""}

        text = (text or "").strip().strip('"').strip()
        if not text:
            self.last_error = "provider returned empty response"
            return {"speaker": 0, "text": ""}

        self.last_error = None
        self._history.append(text)
        self._last_call = now
        return CommentaryResult(speaker=speaker, text=text).as_dict()

    @staticmethod
    def test_key(provider: str, api_key: str) -> tuple[bool, str]:
        """Lightweight auth check against the given provider. Returns (ok, message)."""
        provider = (provider or "").lower().strip()
        api_key = (api_key or "").strip()
        if provider == "template":
            return True, "OK (offline)"
        if not api_key and provider != "ollama":
            return False, "No API key"
        try:
            if provider == "openai":
                from openai import OpenAI
                client = OpenAI(api_key=api_key, timeout=10.0)
                client.models.list()
                return True, "OK"
            if provider == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=api_key, timeout=10.0)
                client.messages.create(
                    model="claude-haiku-4-5",
                    max_tokens=1,
                    messages=[{"role": "user", "content": "hi"}],
                )
                return True, "OK"
            if provider == "gemini":
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                # list_models is a lightweight auth check
                _ = list(genai.list_models())
                return True, "OK"
            if provider == "ollama":
                import requests
                r = requests.get("http://localhost:11434/api/tags", timeout=5)
                r.raise_for_status()
                return True, "OK"
            return False, f"Unknown provider: {provider}"
        except Exception as e:
            cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
            msg = f"{type(e).__name__}: {e}"
            if cause:
                msg += f" [caused by {type(cause).__name__}: {cause}]"
            return False, msg

    def _call_provider(self, system: str, user: str) -> str:
        if self.provider == "openai":
            return self._call_openai(system, user)
        if self.provider == "anthropic":
            return self._call_anthropic(system, user)
        if self.provider == "gemini":
            return self._call_gemini(system, user)
        if self.provider == "ollama":
            return self._call_ollama(system, user)
        raise ValueError(f"Unknown provider: {self.provider}")

    def _call_openai(self, system: str, user: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)
        resp = client.chat.completions.create(
            model=self.model or "gpt-4o-mini",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=80,
            temperature=0.9,
        )
        return resp.choices[0].message.content or ""

    def _call_anthropic(self, system: str, user: str) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        resp = client.messages.create(
            model=self.model or "claude-sonnet-4-6",
            system=system,
            max_tokens=120,
            temperature=0.9,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text if resp.content else ""

    def _call_gemini(self, system: str, user: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            model_name=self.model or "gemini-2.0-flash",
            system_instruction=system,
        )
        resp = model.generate_content(
            user,
            generation_config={"max_output_tokens": 120, "temperature": 0.9},
        )
        return getattr(resp, "text", "") or ""

    def _call_ollama(self, system: str, user: str) -> str:
        import requests
        r = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": self.model or "llama3",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.9},
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")
