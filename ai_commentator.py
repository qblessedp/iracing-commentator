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
        "PRACTICE session. Calm, analytical, conversational. Talk about setup work, "
        "reference laps, long runs, who is trying what. No race drama. Do NOT say "
        "'lights out', 'final stages', 'laps to go', 'lead change', 'race for the win'. "
        "Reference times and data, not position battles for the win."
    ),
    "qualifying": (
        "QUALIFYING session. Tense, urgent, laser-focused on the lap. Use 'provisional pole', "
        "'on the flyer', 'banker lap', 'out for a final run', 'purple sectors'. NEVER say "
        "'the race', 'laps to go', 'race strategy', 'tyre wear over the stint', 'pit stop for "
        "an undercut'. The race has not started — this is one-lap pace."
    ),
    "race": (
        "RACE session. Full broadcast energy, dramatic but natural. Battles, strategy, "
        "tyre degradation, overtakes, laps remaining, pit windows all in play."
    ),
}

SPEAKER_PERSONA = {
    1: (
        "lead play-by-play commentator. You talk like a real broadcaster — contractions, "
        "natural cadence, the occasional half-sentence, interjections like 'Oh', 'And', "
        "'Well', 'Look at that'. Urgent when the moment demands it, crisp the rest of the "
        "time. Think David Croft on a good day. Never stilted, never press-release prose."
    ),
    2: (
        "pit-lane reporter and color analyst. Conversational, observational, a touch of dry wit. "
        "React first, then add a short bit of insight. Think Martin Brundle — contractions, "
        "asides, real spoken English. Avoid formal or robotic phrasing. "
        "Focus on strategy, tyres, and what you'd hear from the garage."
    ),
    3: (
        "grizzled ex-driver veteran in the booth. Opinionated, dry humour, the occasional "
        "'back in my day'. References technique, car control, racecraft — understeer, "
        "rotation, throttle application, where a driver is losing time. Not afraid to call "
        "out a bad move. Think a hardened retired racer who's seen it all."
    ),
    4: (
        "hype commentator. Over-the-top energy. Big moments get BIG reactions — "
        "exclamations, the occasional CAPS on one word for emphasis. 'UNBELIEVABLE', "
        "'OH MY WORD', 'WHAT A MOVE'. Makes everything feel huge. Still a single line, "
        "still in character — just turned up to eleven."
    ),
}

# Which speakers are best suited to which event types. First choice wins when
# it isn't the last speaker; otherwise we try next in the list; otherwise
# round-robin. Keeps rotation natural without starving any persona.
EVENT_SPEAKER_AFFINITY: dict[str, list[int]] = {
    "lead_change": [1, 4],
    "checkered": [1, 4],
    "race_start": [1, 4],
    "laps_to_go": [1, 3],
    "flag_change": [1, 2],
    "battle": [2, 3],
    "overtake": [2, 4],
    "accident_suspected": [2, 3],
    "pit_entry": [3, 2],
    "pit_exit": [3, 2],
    "fastest_lap": [4, 1],
}

SPEAKER_IDS = (1, 2, 3, 4)

STYLE_DIRECTIVE = (
    "Sound like a real person on a live broadcast, not a news reader. "
    "Use contractions (he's, it's, that's, isn't, we're). Interjections are welcome "
    "('Oh!', 'And...', 'Well,', 'Look at that', 'Hang on'). Short or incomplete sentences "
    "are fine if a commentator would say them. Never start with 'In other news' or a formal "
    "connector. Never explain what an event is — react to it. No emojis, no hashtags."
)

FILLER_STYLE_DIRECTIVE = (
    "This is natural broadcaster filler between on-track moments. Weave the fact in like "
    "you're chatting between laps — never read it as a list, never say 'fun fact' or "
    "'did you know'. One short line, conversational, in character."
)


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
        self._last_speaker: int | None = None
        self._history: deque[str] = deque(maxlen=MAX_HISTORY_LINES)
        self._last_call = 0.0
        self.last_error: str | None = None
        self._template = None
        if self.provider == "template":
            from templates import TemplateCommentator
            self._template = TemplateCommentator()

    def _pick_speaker(self, event_type: str | None) -> int:
        """Pick a speaker for the given event.

        Rules:
          1. If the event has an affinity list, return the first speaker in
             that list that isn't the last one used.
          2. Otherwise (or if everyone in the list was last), round-robin
             through all 4 speakers starting after `_last_speaker`.
        """
        affinity = EVENT_SPEAKER_AFFINITY.get((event_type or "").lower(), [])
        for s in affinity:
            if s != self._last_speaker:
                self._last_speaker = s
                return s
        # Round-robin fallback
        if self._last_speaker in SPEAKER_IDS:
            idx = SPEAKER_IDS.index(self._last_speaker)
            s = SPEAKER_IDS[(idx + 1) % len(SPEAKER_IDS)]
        else:
            s = SPEAKER_IDS[0]
        self._last_speaker = s
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
            f"{STYLE_DIRECTIVE}\n"
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

        speaker = self._pick_speaker(selected[0].get("type"))
        # Template provider: skip LLM, pick from curated phrase pools
        if self.provider == "template" and self._template is not None:
            try:
                text = self._template.generate(selected[0], language, session_type)
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

    # ------------------------------------------------------------------ filler
    def _filler_speaker(self, kind: str) -> int:
        """Pick a speaker for filler. Hype (4) does most of it, veteran (3)
        chimes in ~30% of the time. Color analyst (2) is a quieter backup."""
        import random as _r
        roll = _r.random()
        if kind == "driver":
            if roll < 0.5:
                preferred = 4
            elif roll < 0.85:
                preferred = 3
            else:
                preferred = 2
        else:  # track
            if roll < 0.45:
                preferred = 3
            elif roll < 0.85:
                preferred = 1
            else:
                preferred = 2
        # Avoid immediate repeat if possible
        if preferred == self._last_speaker:
            for alt in (3, 4, 1, 2):
                if alt != self._last_speaker:
                    preferred = alt
                    break
        self._last_speaker = preferred
        return preferred

    @staticmethod
    def _format_filler_facts(subject: dict) -> str:
        kind = subject.get("kind", "")
        data = subject.get("data", {}) or {}
        lines: list[str] = []
        if kind == "driver":
            name = data.get("name") or data.get("username") or "this driver"
            lines.append(f"Driver: {name}")
            for key, label in (
                ("carnumber", "car number"),
                ("teamname", "team"),
                ("irating", "current iRating"),
                ("licstring", "licence"),
                ("irating_peak", "peak iRating"),
                ("known_for", "known for"),
                ("home_track", "home track"),
                ("fun_fact", "fun fact"),
            ):
                val = data.get(key)
                if val not in (None, ""):
                    lines.append(f"- {label}: {val}")
        else:  # track
            name = data.get("name") or "this track"
            lines.append(f"Track: {name}")
            for key, label in (
                ("length_km", "length (km)"),
                ("corners", "corners"),
                ("lap_record", "lap record"),
                ("elevation_m", "elevation change (m)"),
                ("opened_year", "opened"),
                ("fun_fact", "fun fact"),
            ):
                val = data.get(key)
                if val not in (None, ""):
                    lines.append(f"- {label}: {val}")
        return "\n".join(lines)

    def _filler_system_prompt(self, speaker: int, session_type: str, language: str, guidance: str) -> str:
        persona = SPEAKER_PERSONA[speaker]
        tone = self._session_tone(session_type)
        guidance_block = f"\nLanguage guidance: {guidance}" if guidance else ""
        return (
            f"You are the {persona}\n"
            f"{tone}\n"
            f"{STYLE_DIRECTIVE}\n"
            f"{FILLER_STYLE_DIRECTIVE}\n"
            f"Respond in {language}. One line only, under 22 words. "
            f"No intros, no sign-offs, just the line."
            f"{guidance_block}"
        )

    def generate_filler(
        self,
        subject: dict,
        session_type: str = "Race",
        language: str = "English",
        guidance: str = "",
    ) -> dict:
        """Generate a single filler line about a driver or a track."""
        if not subject or not subject.get("data"):
            return {"speaker": 0, "text": ""}
        now = time.monotonic()
        if now - self._last_call < MIN_INTERVAL_SEC:
            return {"speaker": 0, "text": ""}

        kind = subject.get("kind") or "driver"
        speaker = self._filler_speaker(kind)

        # Template provider: short-circuit via templates.generate_filler
        if self.provider == "template" and self._template is not None:
            try:
                text = self._template.generate_filler(subject, language)
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                return {"speaker": 0, "text": ""}
            text = (text or "").strip()
            if not text:
                return {"speaker": 0, "text": ""}
            self.last_error = None
            self._history.append(text)
            self._last_call = now
            return CommentaryResult(speaker=speaker, text=text).as_dict()

        sys_p = self._filler_system_prompt(speaker, session_type, language, guidance)
        facts_block = self._format_filler_facts(subject)
        history_block = ""
        if self._history:
            history_block = "\nRecent commentary (do not repeat):\n" + "\n".join(
                f"- {h}" for h in self._history
            )
        usr_p = (
            f"Between-laps filler. Work these details in naturally:\n{facts_block}"
            f"{history_block}\n\nOne broadcast line only."
        )
        try:
            text = self._call_provider(sys_p, usr_p)
        except Exception as e:
            cause = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
            msg = f"{type(e).__name__}: {e}"
            if cause:
                msg += f" [caused by {type(cause).__name__}: {cause}]"
            self.last_error = msg
            logger.warning("AI filler error: %s", msg)
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
