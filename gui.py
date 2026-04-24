"""Dark-themed tkinter UI for the iRacing Commentator.

Palette inspired by Tokyo Night. Typography uses Segoe UI for readability
on Windows and a mono face (Cascadia Mono / Consolas) for the log.
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from ai_commentator import AICommentator
from config import (
    load_config, save_config, PROVIDERS, TTS_PROVIDERS, LANGUAGE_LABELS,
    EDGE_NEURAL_VOICES, SAPI_DEFAULT_VOICES, EDGE_DEFAULT_VOICES, ELEVENLABS_DEFAULT_VOICES,
)
from tts_elevenlabs import TTSElevenLabs
from tts_edge import TTSEdge
from tts_sapi import TTSSapi
from updater import APP_VERSION, check_and_apply


# --- Palette -----------------------------------------------------------------
BG = "#1a1b26"          # window background
PANEL = "#24283b"       # label-frame surface
FIELD = "#2f334d"       # entry / combobox surface
BORDER = "#414868"
TEXT = "#c0caf5"        # primary text
MUTED = "#9aa5ce"       # secondary text
ACCENT = "#7aa2f7"      # primary accent (blue)
ACCENT_HOVER = "#89b4ff"
SPEAKER1 = "#7aa2f7"    # blue
SPEAKER2 = "#ff9e64"    # orange
SPEAKER3 = "#bb9af7"    # purple (veteran)
SPEAKER4 = "#f7768e"    # pink/red (hype)
OK = "#9ece6a"          # green
WARN = "#e0af68"        # amber
ERR = "#f7768e"         # red / pink

# --- Typography --------------------------------------------------------------
FONT_UI = ("Segoe UI", 10)
FONT_UI_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI Semibold", 11)
FONT_LOG = ("Cascadia Mono", 10)
FONT_LOG_FALLBACK = ("Consolas", 10)


class CommentatorGUI(tk.Tk):
    def __init__(self, on_start=None, on_stop=None, on_volume_change=None, on_language_change=None):
        super().__init__()
        self.title(f"iRacing Commentator v{APP_VERSION}")
        self.minsize(700, 720)
        self.configure(bg=BG)

        self.on_start = on_start
        self.on_stop = on_stop
        self.on_volume_change = on_volume_change
        self.on_language_change = on_language_change
        self.running = False
        self.config_data = load_config()

        # Restore saved window geometry (size + optional position).
        saved_geo = self.config_data.get("window_geometry", "640x780")
        try:
            self.geometry(saved_geo)
        except Exception:
            self.geometry("640x780")

        self._apply_theme()
        self._build_ui()

        # Persist geometry whenever the user resizes or moves the window.
        self._geo_save_job: str | None = None
        self.bind("<Configure>", self._on_window_configure)

    # ------------------------------------------------------------------ theme
    def _apply_theme(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=BG, foreground=TEXT, font=FONT_UI)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)

        style.configure(
            "TLabelframe",
            background=BG,
            foreground=MUTED,
            bordercolor=BORDER,
            relief="flat",
            padding=12,
        )
        style.configure(
            "TLabelframe.Label",
            background=BG,
            foreground=ACCENT,
            font=FONT_TITLE,
        )

        style.configure("TLabel", background=BG, foreground=TEXT, font=FONT_UI)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Status.TLabel", background=BG, foreground=MUTED, font=FONT_UI_BOLD)

        style.configure(
            "TEntry",
            fieldbackground=FIELD,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=6,
        )
        style.map("TEntry", fieldbackground=[("focus", FIELD)], bordercolor=[("focus", ACCENT)])

        style.configure(
            "TCombobox",
            fieldbackground=FIELD,
            background=FIELD,
            foreground=TEXT,
            arrowcolor=TEXT,
            bordercolor=BORDER,
            padding=6,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", FIELD)],
            foreground=[("readonly", TEXT)],
            bordercolor=[("focus", ACCENT)],
        )
        # Popdown listbox colors
        self.option_add("*TCombobox*Listbox.background", FIELD)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", BG)
        self.option_add("*TCombobox*Listbox.font", FONT_UI)

        style.configure(
            "TButton",
            background=FIELD,
            foreground=TEXT,
            bordercolor=BORDER,
            focusthickness=0,
            padding=(14, 6),
            font=FONT_UI_BOLD,
        )
        style.map(
            "TButton",
            background=[("active", BORDER), ("pressed", BORDER)],
            foreground=[("active", TEXT)],
        )

        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground=BG,
            bordercolor=ACCENT,
            padding=(18, 7),
            font=FONT_UI_BOLD,
        )
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)],
            foreground=[("active", BG)],
        )

        # Horizontal scale (volume slider) — Tokyo Night
        style.configure(
            "Accent.Horizontal.TScale",
            background=BG,
            troughcolor=FIELD,
            bordercolor=BORDER,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
        )
        style.map(
            "Accent.Horizontal.TScale",
            background=[("active", BG)],
            troughcolor=[("active", FIELD)],
        )

    # --------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        pad = {"padx": 14, "pady": 6}

        # Text AI
        frame = ttk.LabelFrame(self, text="Text AI")
        frame.pack(fill="x", **pad)
        ttk.Label(frame, text="Provider").grid(row=0, column=0, sticky="w", pady=4)
        self.provider_var = tk.StringVar(value=self.config_data["text_provider"])
        self.provider_combo = ttk.Combobox(
            frame,
            textvariable=self.provider_var,
            values=PROVIDERS,
            state="readonly",
            width=22,
            font=FONT_UI,
        )
        self.provider_combo.grid(row=0, column=1, sticky="w", padx=10, pady=4)
        self.provider_combo.bind("<<ComboboxSelected>>", self._on_text_provider_change)

        ttk.Label(frame, text="API Key").grid(row=1, column=0, sticky="w", pady=4)
        self.text_key_var = tk.StringVar(value=self.config_data["text_api_key"])
        self.text_key_entry = ttk.Entry(
            frame, textvariable=self.text_key_var, show="•", width=44, font=FONT_UI
        )
        self.text_key_entry.grid(row=1, column=1, sticky="w", padx=10, pady=4)
        self.ai_test_btn = ttk.Button(frame, text="Test", command=self._test_ai_key, width=7)
        self.ai_test_btn.grid(row=1, column=2, sticky="w", padx=(0, 6), pady=4)
        self.ai_status_var = tk.StringVar(value="")
        self.ai_status_indicator = ttk.Label(frame, textvariable=self.ai_status_var, font=FONT_UI_BOLD)
        self.ai_status_indicator.grid(row=1, column=3, sticky="w", pady=4)

        # TTS (ElevenLabs or Microsoft Edge)
        frame2 = ttk.LabelFrame(self, text="Text-to-Speech")
        frame2.pack(fill="x", **pad)

        ttk.Label(frame2, text="Provider").grid(row=0, column=0, sticky="w", pady=4)
        self.tts_provider_var = tk.StringVar(
            value=self.config_data.get("tts_provider", "elevenlabs")
        )
        self.tts_provider_combo = ttk.Combobox(
            frame2,
            textvariable=self.tts_provider_var,
            values=TTS_PROVIDERS,
            state="readonly",
            width=22,
            font=FONT_UI,
        )
        self.tts_provider_combo.grid(row=0, column=1, sticky="w", padx=10, pady=4)
        self.tts_provider_combo.bind("<<ComboboxSelected>>", self._on_tts_provider_change)

        ttk.Label(frame2, text="API Key").grid(row=1, column=0, sticky="w", pady=4)
        self.el_key_var = tk.StringVar(value=self.config_data["elevenlabs_api_key"])
        self.el_key_entry = ttk.Entry(
            frame2, textvariable=self.el_key_var, show="•", width=44, font=FONT_UI
        )
        self.el_key_entry.grid(row=1, column=1, sticky="w", padx=10, pady=4)
        self.tts_test_btn = ttk.Button(frame2, text="Test", command=self._test_tts_key, width=7)
        self.tts_test_btn.grid(row=1, column=2, sticky="w", padx=(0, 6), pady=4)
        self.tts_status_var = tk.StringVar(value="")
        self.tts_status_indicator = ttk.Label(frame2, textvariable=self.tts_status_var, font=FONT_UI_BOLD)
        self.tts_status_indicator.grid(row=1, column=3, sticky="w", pady=4)

        self.preview_btns: dict[int, ttk.Button] = {}
        self.pick_btns: dict[int, ttk.Button] = {}

        ttk.Label(frame2, text="Speaker 1 — Play-by-play").grid(row=2, column=0, sticky="w", pady=4)
        self.voice1_var = tk.StringVar(value=self.config_data["voice_id_1"])
        ttk.Entry(frame2, textvariable=self.voice1_var, width=44, font=FONT_UI).grid(
            row=2, column=1, sticky="w", padx=10, pady=4
        )
        _pb1 = ttk.Button(frame2, text="▶", width=3, command=lambda: self._preview_voice(1))
        _pb1.grid(row=2, column=2, sticky="w", padx=(0, 2), pady=4)
        self.preview_btns[1] = _pb1
        _pk1 = ttk.Button(frame2, text="🎙", width=3, command=lambda: self._voice_picker_dialog(1))
        _pk1.grid(row=2, column=3, sticky="w", padx=(0, 4), pady=4)
        self.pick_btns[1] = _pk1

        ttk.Label(frame2, text="Speaker 2 — Color Analyst").grid(row=3, column=0, sticky="w", pady=4)
        self.voice2_var = tk.StringVar(value=self.config_data["voice_id_2"])
        ttk.Entry(frame2, textvariable=self.voice2_var, width=44, font=FONT_UI).grid(
            row=3, column=1, sticky="w", padx=10, pady=4
        )
        _pb2 = ttk.Button(frame2, text="▶", width=3, command=lambda: self._preview_voice(2))
        _pb2.grid(row=3, column=2, sticky="w", padx=(0, 2), pady=4)
        self.preview_btns[2] = _pb2
        _pk2 = ttk.Button(frame2, text="🎙", width=3, command=lambda: self._voice_picker_dialog(2))
        _pk2.grid(row=3, column=3, sticky="w", padx=(0, 4), pady=4)
        self.pick_btns[2] = _pk2

        ttk.Label(frame2, text="Speaker 3 — Veteran Ex-Driver").grid(row=4, column=0, sticky="w", pady=4)
        self.voice3_var = tk.StringVar(value=self.config_data.get("voice_id_3", ""))
        ttk.Entry(frame2, textvariable=self.voice3_var, width=44, font=FONT_UI).grid(
            row=4, column=1, sticky="w", padx=10, pady=4
        )
        _pb3 = ttk.Button(frame2, text="▶", width=3, command=lambda: self._preview_voice(3))
        _pb3.grid(row=4, column=2, sticky="w", padx=(0, 2), pady=4)
        self.preview_btns[3] = _pb3
        _pk3 = ttk.Button(frame2, text="🎙", width=3, command=lambda: self._voice_picker_dialog(3))
        _pk3.grid(row=4, column=3, sticky="w", padx=(0, 4), pady=4)
        self.pick_btns[3] = _pk3

        ttk.Label(frame2, text="Speaker 4 — Hype Commentator").grid(row=5, column=0, sticky="w", pady=4)
        self.voice4_var = tk.StringVar(value=self.config_data.get("voice_id_4", ""))
        ttk.Entry(frame2, textvariable=self.voice4_var, width=44, font=FONT_UI).grid(
            row=5, column=1, sticky="w", padx=10, pady=4
        )
        _pb4 = ttk.Button(frame2, text="▶", width=3, command=lambda: self._preview_voice(4))
        _pb4.grid(row=5, column=2, sticky="w", padx=(0, 2), pady=4)
        self.preview_btns[4] = _pb4
        _pk4 = ttk.Button(frame2, text="🎙", width=3, command=lambda: self._voice_picker_dialog(4))
        _pk4.grid(row=5, column=3, sticky="w", padx=(0, 4), pady=4)
        self.pick_btns[4] = _pk4
        self._apply_tts_provider_state()
        self._apply_text_provider_state()

        # Language
        frame3 = ttk.LabelFrame(self, text="Language")
        frame3.pack(fill="x", **pad)
        self._lang_display_to_code = {label: code for code, label in LANGUAGE_LABELS.items()}
        current_code = self.config_data["language"]
        current_label = LANGUAGE_LABELS.get(current_code, LANGUAGE_LABELS["en"])
        self.lang_display_var = tk.StringVar(value=current_label)
        lang_combo = ttk.Combobox(
            frame3,
            textvariable=self.lang_display_var,
            values=list(LANGUAGE_LABELS.values()),
            state="readonly",
            width=28,
            font=FONT_UI,
        )
        lang_combo.grid(row=0, column=0, sticky="w", pady=4)
        lang_combo.bind("<<ComboboxSelected>>", self._on_language_change)

        # Volume (commentary playback only)
        frame4 = ttk.LabelFrame(self, text="Commentary Volume")
        frame4.pack(fill="x", **pad)
        frame4.columnconfigure(1, weight=1)

        initial_vol = int(self.config_data.get("volume", 100))
        initial_vol = max(0, min(100, initial_vol))
        self.volume_var = tk.IntVar(value=initial_vol)
        self.volume_readout_var = tk.StringVar(value=f"{initial_vol}%")

        ttk.Label(frame4, text="🔈", foreground=MUTED).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self.volume_scale = ttk.Scale(
            frame4,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.volume_var,
            command=self._on_volume_change,
            style="Accent.Horizontal.TScale",
        )
        self.volume_scale.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(frame4, text="🔊", foreground=ACCENT).grid(
            row=0, column=2, sticky="w", padx=(8, 10)
        )
        self.volume_readout_label = ttk.Label(
            frame4,
            textvariable=self.volume_readout_var,
            font=FONT_UI_BOLD,
            foreground=ACCENT,
            width=5,
            anchor="e",
        )
        self.volume_readout_label.grid(row=0, column=3, sticky="e")

        # Controls
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", **pad)
        self.start_btn = ttk.Button(
            btn_frame, text="  Start  ", command=self._toggle, style="Accent.TButton"
        )
        self.start_btn.pack(side="left", padx=(0, 8))
        ttk.Button(btn_frame, text="Save Config", command=self._save).pack(side="left")
        ttk.Button(btn_frame, text="Check for Updates", command=self._check_updates).pack(
            side="left", padx=(8, 0)
        )

        self.status_var = tk.StringVar(value="● Disconnected")
        self.status_label = ttk.Label(btn_frame, textvariable=self.status_var, style="Status.TLabel")
        self.status_label.pack(side="right")
        self._set_status_color(MUTED)

        # Log
        log_frame = ttk.LabelFrame(self, text="Broadcast Log")
        log_frame.pack(fill="both", expand=True, **pad)

        log_font = FONT_LOG
        try:
            # Probe font; fallback if Cascadia not installed
            from tkinter import font as tkfont
            if "Cascadia Mono" not in tkfont.families():
                log_font = FONT_LOG_FALLBACK
        except Exception:
            log_font = FONT_LOG_FALLBACK

        self.log = ScrolledText(
            log_frame,
            height=14,
            state="disabled",
            wrap="word",
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground=ACCENT,
            selectforeground=BG,
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=8,
            font=log_font,
        )
        self.log.pack(fill="both", expand=True)
        self.log.tag_config("speaker1", foreground=SPEAKER1, font=(log_font[0], log_font[1], "bold"))
        self.log.tag_config("speaker2", foreground=SPEAKER2, font=(log_font[0], log_font[1], "bold"))
        self.log.tag_config("speaker3", foreground=SPEAKER3, font=(log_font[0], log_font[1], "bold"))
        self.log.tag_config("speaker4", foreground=SPEAKER4, font=(log_font[0], log_font[1], "bold"))
        self.log.tag_config("error", foreground=ERR)
        self.log.tag_config("info", foreground=MUTED)
        self.log.tag_config("ok", foreground=OK)
        self.log.tag_config("warn", foreground=WARN)

    # --------------------------------------------------------------- helpers
    def _set_status_color(self, color: str) -> None:
        # ttk Style doesn't let us per-instance recolor a label foreground easily;
        # we stash a dedicated style name keyed by color.
        style = ttk.Style(self)
        style_name = f"Status{color.strip('#')}.TLabel"
        style.configure(style_name, background=BG, foreground=color, font=FONT_UI_BOLD)
        self.status_label.configure(style=style_name)

    def _collect(self) -> dict:
        def clean(v: str) -> str:
            return (v or "").strip()
        return {
            "text_provider": clean(self.provider_var.get()),
            "text_api_key": clean(self.text_key_var.get()),
            "elevenlabs_api_key": clean(self.el_key_var.get()),
            "voice_id_1": clean(self.voice1_var.get()),
            "voice_id_2": clean(self.voice2_var.get()),
            "voice_id_3": clean(self.voice3_var.get()),
            "voice_id_4": clean(self.voice4_var.get()),
            "language": self._lang_display_to_code.get(self.lang_display_var.get(), "en"),
            "volume": int(self.volume_var.get()),
            "tts_provider": clean(self.tts_provider_var.get()) or "elevenlabs",
            "window_geometry": self.winfo_geometry(),
        }

    def _on_window_configure(self, event: tk.Event) -> None:
        """Debounced save of window geometry on resize/move."""
        if event.widget is not self:
            return
        if self._geo_save_job:
            try:
                self.after_cancel(self._geo_save_job)
            except Exception:
                pass
        self._geo_save_job = self.after(500, self._persist_geometry)

    def _persist_geometry(self) -> None:
        self._geo_save_job = None
        try:
            w = self.winfo_width()
            h = self.winfo_height()
            x = self.winfo_x()
            y = self.winfo_y()
            # Skip degenerate values emitted during startup before the window
            # has been fully laid out (winfo returns 1x1 until first map).
            if w < 100 or h < 100:
                return
            geo = f"{w}x{h}+{x}+{y}"
            self.config_data["window_geometry"] = geo
            save_config(self.config_data)
        except Exception:
            pass

    def _on_language_change(self, _event=None) -> None:
        lang_code = self._lang_display_to_code.get(self.lang_display_var.get(), "en")
        if self.on_language_change:
            try:
                self.on_language_change(lang_code)
            except Exception:
                pass

    # --- Voice ID format helpers -------------------------------------------

    @staticmethod
    def _voice_is_elevenlabs(v: str) -> bool:
        """ElevenLabs IDs are ≥15 purely alphanumeric chars — no dashes or spaces."""
        return len(v) >= 15 and v.isalnum()

    @staticmethod
    def _voice_is_edge(v: str) -> bool:
        """Edge neural voices follow the locale-Neural pattern, e.g. en-GB-RyanNeural."""
        return "Neural" in v and "-" in v

    def _on_tts_provider_change(self, _event=None) -> None:
        """Auto-fill voice IDs with sensible defaults when the TTS provider changes.

        Each voice field is inspected individually: if its current value is in the
        wrong format for the new provider (e.g. an ElevenLabs hash still sitting in
        the field after switching to SAPI), it is replaced with the correct default.
        Custom values already in the right format are kept as-is."""
        new_provider = (self.tts_provider_var.get() or "elevenlabs").lower().strip()
        voice_vars = {
            1: self.voice1_var,
            2: self.voice2_var,
            3: self.voice3_var,
            4: self.voice4_var,
        }
        for slot, var in voice_vars.items():
            current = (var.get() or "").strip()
            is_el   = self._voice_is_elevenlabs(current)
            is_edge = self._voice_is_edge(current)
            # is_sapi: non-empty and doesn't look like the other two formats
            is_sapi = bool(current) and not is_el and not is_edge

            if new_provider == "elevenlabs":
                if not current or is_edge or is_sapi:
                    var.set(ELEVENLABS_DEFAULT_VOICES.get(slot, ""))
            elif new_provider == "edge":
                if not current or is_el or is_sapi:
                    var.set(EDGE_DEFAULT_VOICES.get(slot, ""))
            elif new_provider == "sapi":
                # The old bug: ElevenLabs hashes are alphanumeric with no dash,
                # so the previous len>30 check never fired. is_el catches them.
                if not current or is_el or is_edge:
                    var.set(SAPI_DEFAULT_VOICES.get(slot, ""))
        self._apply_tts_provider_state()

    def _apply_tts_provider_state(self) -> None:
        """Grey out the ElevenLabs API key entry for key-less backends.
        Enable the 🎙 pick buttons only for providers with an enumerable voice list."""
        provider = (self.tts_provider_var.get() or "").lower().strip()
        if provider in ("edge", "sapi"):
            self.el_key_entry.configure(state="disabled")
        else:
            self.el_key_entry.configure(state="normal")
        # Voice picker only makes sense for SAPI (list from OS) and Edge (curated list).
        pick_state = "normal" if provider in ("edge", "sapi") else "disabled"
        for btn in self.pick_btns.values():
            btn.configure(state=pick_state)

    def _voice_picker_dialog(self, slot: int) -> None:
        """Open a modal voice-picker for the given speaker slot.

        SAPI: shows all installed voices (standard + OneCore) from
              TTSSapi.list_all_voices() with a live filter box.
        Edge: shows the curated EDGE_NEURAL_VOICES list with a live filter box.
        Double-clicking or pressing Select writes the chosen name into the
        corresponding voice_id entry field."""
        provider = (self.tts_provider_var.get() or "elevenlabs").lower().strip()
        if provider == "sapi":
            voices = TTSSapi.list_all_voices()
            title = f"Speaker {slot} — Windows SAPI Voice"
        elif provider == "edge":
            voices = list(EDGE_NEURAL_VOICES)
            title = f"Speaker {slot} — Edge Neural Voice"
        else:
            return  # ElevenLabs: no enumerable list

        if not voices:
            self.log_line("No voices found for this provider.", tag="warn")
            return

        voice_var = {
            1: self.voice1_var, 2: self.voice2_var,
            3: self.voice3_var, 4: self.voice4_var,
        }.get(slot)
        if voice_var is None:
            return

        dlg = tk.Toplevel(self)
        dlg.title(title)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()  # modal — blocks interaction with main window

        # Filter box
        search_frame = ttk.Frame(dlg)
        search_frame.pack(fill="x", padx=12, pady=(12, 4))
        ttk.Label(search_frame, text="Filter:").pack(side="left")
        search_var = tk.StringVar()
        search_entry = ttk.Entry(
            search_frame, textvariable=search_var, width=32, font=FONT_UI
        )
        search_entry.pack(side="left", padx=(6, 0), fill="x", expand=True)

        # Scrollable Listbox
        list_frame = ttk.Frame(dlg)
        list_frame.pack(fill="both", expand=True, padx=12, pady=4)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        listbox = tk.Listbox(
            list_frame,
            bg=FIELD,
            fg=TEXT,
            selectbackground=ACCENT,
            selectforeground=BG,
            font=FONT_UI,
            activestyle="none",
            height=16,
            width=42,
            yscrollcommand=scrollbar.set,
            relief="flat",
            borderwidth=0,
        )
        scrollbar.config(command=listbox.yview)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _populate(filter_text: str = "") -> None:
            listbox.delete(0, "end")
            fl = filter_text.lower()
            for v in voices:
                if fl in v.lower():
                    listbox.insert("end", v)
            # Pre-select the currently configured voice
            current = voice_var.get().strip().lower()
            for i in range(listbox.size()):
                item = listbox.get(i).lower()
                if current and (item == current or current in item):
                    listbox.selection_set(i)
                    listbox.see(i)
                    break

        _populate()
        search_var.trace_add("write", lambda *_: _populate(search_var.get()))

        def _select() -> None:
            sel = listbox.curselection()
            if not sel:
                return
            voice_var.set(listbox.get(sel[0]))
            dlg.destroy()

        listbox.bind("<Double-Button-1>", lambda _e: _select())
        dlg.bind("<Return>", lambda _e: _select())

        # Action buttons
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(
            btn_frame, text="Select", style="Accent.TButton", command=_select
        ).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side="left")

        # Centre dialog over the main window
        dlg.update_idletasks()
        pw = self.winfo_x() + (self.winfo_width() - dlg.winfo_width()) // 2
        ph = self.winfo_y() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{pw}+{ph}")
        search_entry.focus_set()

    def _on_text_provider_change(self, _event=None) -> None:
        self._apply_text_provider_state()

    def _apply_text_provider_state(self) -> None:
        """Grey out the Text AI API key entry when template (offline) is selected."""
        provider = (self.provider_var.get() or "").lower().strip()
        if provider == "template":
            self.text_key_entry.configure(state="disabled")
        else:
            self.text_key_entry.configure(state="normal")

    def _on_volume_change(self, _val: str) -> None:
        pct = max(0, min(100, int(float(self.volume_var.get()))))
        self.volume_var.set(pct)
        self.volume_readout_var.set(f"{pct}%")
        # Live apply (safe no-op if worker not running)
        if self.on_volume_change:
            try:
                self.on_volume_change(pct)
            except Exception:
                pass
        # Debounced persist (latest movement wins within 400ms)
        if getattr(self, "_volume_save_job", None):
            try:
                self.after_cancel(self._volume_save_job)
            except Exception:
                pass
        self._volume_save_job = self.after(400, self._persist_volume)

    def _persist_volume(self) -> None:
        self._volume_save_job = None
        try:
            cfg = self._collect()
            save_config(cfg)
            self.config_data = cfg
        except Exception:
            pass

    def _save(self) -> None:
        cfg = self._collect()
        save_config(cfg)
        self.config_data = cfg
        self.log_line("Config saved.", tag="ok")

    def _set_indicator(self, label: ttk.Label, var: tk.StringVar, ok: bool | None, msg: str = "") -> None:
        if ok is None:
            var.set("…")
            color = MUTED
        elif ok:
            var.set("✓")
            color = OK
        else:
            var.set("✗")
            color = ERR
        style = ttk.Style(self)
        style_name = f"Ind{color.strip('#')}.TLabel"
        style.configure(style_name, background=BG, foreground=color, font=FONT_UI_BOLD)
        label.configure(style=style_name)
        if msg:
            self.log_line(msg, tag="ok" if ok else "error")

    def _test_ai_key(self) -> None:
        provider = (self.provider_var.get() or "").strip()
        api_key = (self.text_key_var.get() or "").strip()
        self._set_indicator(self.ai_status_indicator, self.ai_status_var, None)
        self.ai_test_btn.configure(state="disabled")

        def worker() -> None:
            ok, msg = AICommentator.test_key(provider, api_key)
            def update() -> None:
                self.ai_test_btn.configure(state="normal")
                self._set_indicator(
                    self.ai_status_indicator,
                    self.ai_status_var,
                    ok,
                    f"AI key test: {msg}" if not ok else "AI key OK",
                )
            self.after(0, update)

        threading.Thread(target=worker, daemon=True).start()

    def _test_tts_key(self) -> None:
        provider = (self.tts_provider_var.get() or "elevenlabs").lower().strip()
        api_key = (self.el_key_var.get() or "").strip()
        v1 = (self.voice1_var.get() or "").strip()
        v2 = (self.voice2_var.get() or "").strip()
        self._set_indicator(self.tts_status_indicator, self.tts_status_var, None)
        self.tts_test_btn.configure(state="disabled")

        def worker() -> None:
            if provider == "edge":
                tts = TTSEdge(voice_id_1=v1, voice_id_2=v2)
                label = "Edge TTS"
            elif provider == "sapi":
                tts = TTSSapi(voice_id_1=v1, voice_id_2=v2)
                label = "Windows SAPI"
            else:
                tts = TTSElevenLabs(api_key=api_key, voice_id_1=v1, voice_id_2=v2)
                label = "ElevenLabs"
            ok, msg = tts.validate()
            def update() -> None:
                self.tts_test_btn.configure(state="normal")
                self._set_indicator(
                    self.tts_status_indicator,
                    self.tts_status_var,
                    ok,
                    f"{label} test: {msg}" if not ok else f"{label} OK",
                )
            self.after(0, update)

        threading.Thread(target=worker, daemon=True).start()

    def _preview_voice(self, slot: int) -> None:
        import time

        PREVIEW_TEXTS = {
            1: "Lights out and away we go! A brilliant start from the front!",
            2: "The strategy here is absolutely crucial. We could see an undercut play out.",
            3: "Back in my day, you had to earn every position. Pure racecraft.",
            4: "OH MY WORD! That is ABSOLUTELY UNBELIEVABLE! What a moment!",
        }
        text = PREVIEW_TEXTS.get(slot, "Testing voice preview.")
        cfg = self._collect()
        provider = cfg.get("tts_provider", "elevenlabs").lower()
        api_key = cfg.get("elevenlabs_api_key", "")
        v = {i: cfg.get(f"voice_id_{i}", "") for i in range(1, 5)}
        volume = max(0.0, min(1.0, cfg.get("volume", 100) / 100.0))

        btn = self.preview_btns.get(slot)
        if btn:
            btn.configure(state="disabled")
        self.log_line(f"▶ Previewing Speaker {slot}...", tag="info")

        def worker() -> None:
            import time as _time
            tts = None
            btn_enabled = False
            try:
                if provider == "sapi":
                    # Run pyttsx3 directly and synchronously in this thread.
                    # Avoids the queue/_run daemon complexity that caused
                    # silent failures on some Windows COM setups.
                    import pyttsx3
                    engine = pyttsx3.init()
                    voice_hint = (v.get(slot) or "").strip()
                    for vobj in (engine.getProperty("voices") or []):
                        if voice_hint.lower() in (vobj.name or "").lower():
                            engine.setProperty("voice", vobj.id)
                            break
                    rates = {1: 195, 2: 175, 3: 165, 4: 210}
                    engine.setProperty("rate", rates.get(slot, 180))
                    engine.setProperty("volume", volume)
                    engine.say(text)
                    # Re-enable button before blocking on runAndWait.
                    if btn:
                        self.after(0, lambda: btn.configure(state="normal"))
                    btn_enabled = True
                    engine.runAndWait()
                    try:
                        engine.stop()
                    except Exception:
                        pass
                elif provider == "edge":
                    tts = TTSEdge(
                        voice_id_1=v[1], voice_id_2=v[2],
                        voice_id_3=v[3], voice_id_4=v[4],
                        volume=volume,
                    )
                    tts.start()
                    tts.speak(text, slot)
                    if btn:
                        self.after(0, lambda: btn.configure(state="normal"))
                    btn_enabled = True
                    _time.sleep(8)
                else:
                    tts = TTSElevenLabs(
                        api_key=api_key,
                        voice_id_1=v[1], voice_id_2=v[2],
                        voice_id_3=v[3], voice_id_4=v[4],
                        volume=volume,
                    )
                    tts.start()
                    tts.speak(text, slot)
                    if btn:
                        self.after(0, lambda: btn.configure(state="normal"))
                    btn_enabled = True
                    _time.sleep(8)
            except Exception as e:
                self.after(0, lambda err=e: self.log_line(f"Preview error: {err}", tag="error"))
            finally:
                if tts:
                    try:
                        tts.stop()
                    except Exception:
                        pass
                if btn and not btn_enabled:
                    self.after(0, lambda: btn.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _check_updates(self) -> None:
        from tkinter import messagebox
        self.log_line("Checking for updates...", tag="info")

        def confirm(tag: str) -> bool:
            return messagebox.askyesno(
                "Update available",
                f"A new version {tag} is available (current {APP_VERSION}).\n\n"
                "Download and apply now? The app will restart.",
            )

        def worker() -> None:
            def status(msg: str) -> None:
                self.after(0, lambda: self.log_line(msg, tag="info"))

            applied, msg = check_and_apply(on_status=status, confirm=confirm)
            def done() -> None:
                tag = "ok" if applied else "info"
                self.log_line(msg, tag=tag)
                if not applied and "latest" not in msg.lower() and "cancel" not in msg.lower():
                    self.log_line("Update check finished.", tag="warn")
            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _toggle(self) -> None:
        if self.running:
            self.running = False
            self.start_btn.config(text="  Start  ")
            self.set_status("Stopping...", level="warn")
            if self.on_stop:
                self.on_stop()
        else:
            self._save()
            self.running = True
            self.start_btn.config(text="   Stop   ")
            self.set_status("Starting...", level="warn")
            if self.on_start:
                self.on_start(self.config_data)

    # ----------------------------------------------------------- public API
    def set_status(self, text: str, level: str = "info") -> None:
        color = {"ok": OK, "warn": WARN, "error": ERR, "info": MUTED, "accent": ACCENT}.get(
            level, MUTED
        )
        dot = "●"
        self.status_var.set(f"{dot} {text}")
        self._set_status_color(color)

    def log_line(self, text: str, tag: str | None = None) -> None:
        self.log.configure(state="normal")
        if tag:
            self.log.insert("end", text + "\n", tag)
        else:
            self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def log_commentary(self, speaker: int, text: str) -> None:
        tag_map = {1: "speaker1", 2: "speaker2", 3: "speaker3", 4: "speaker4"}
        label_map = {1: "S1", 2: "S2", 3: "S3", 4: "S4"}
        tag = tag_map.get(speaker, "info")
        label = label_map.get(speaker, "–")
        self.log_line(f"[{label}] {text}", tag=tag)

    def log_error(self, text: str) -> None:
        self.log_line(f"✗ {text}", tag="error")
