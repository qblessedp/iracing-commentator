import json
import sys
from pathlib import Path


def _base_dir() -> Path:
    """Where to read/write config.json. Survives PyInstaller onefile."""
    if getattr(sys, "frozen", False):
        # Running from a PyInstaller bundle: persist next to the .exe
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_PATH = _base_dir() / "config.json"

VOICE_SLOTS = (1, 2, 3, 4)

# ElevenLabs preset voice IDs — distinct character per persona. These are the
# public default voices shipped with Eleven accounts; users can overwrite.
ELEVENLABS_DEFAULT_VOICES = {
    1: "pNInz6obpgDQGcFmaJgB",  # Adam — play-by-play
    2: "21m00Tcm4TlvDq8ikWAM",  # Rachel — color / pit lane
    3: "TxGEqnHWrfWFTfGW9XjX",  # Josh — veteran
    4: "AZnzlk1XvdvUeBnXmlld",  # Domi — hype
}

# Microsoft Edge TTS — 4 distinct neural voices (accents/genders).
EDGE_DEFAULT_VOICES = {
    1: "en-GB-RyanNeural",    # British male — play-by-play
    2: "en-US-JennyNeural",   # American female — color
    3: "en-GB-ThomasNeural",  # British male — veteran
    4: "en-US-EricNeural",    # American male — hype
}

# Windows SAPI voice name hints (substring match against installed voices).
# Fully offline — no network required. Whatever Windows has installed is used.
SAPI_DEFAULT_VOICES = {
    1: "David",  # US male — play-by-play
    2: "Zira",   # US female — color
    3: "Mark",   # US male calmer — veteran
    4: "Hazel",  # UK female — hype
}

PERSONA_HINTS = {
    1: "Play-by-play — crisp British broadcaster, urgent when it counts.",
    2: "Color analyst / pit-lane reporter — conversational, dry wit.",
    3: "Veteran ex-driver — grizzled, opinionated, technique-focused.",
    4: "Hype commentator — big energy, exclamations, drama.",
}

DEFAULT_CONFIG = {
    "text_provider": "openai",
    "text_api_key": "",
    "tts_provider": "elevenlabs",
    "elevenlabs_api_key": "",
    "voice_id_1": "",
    "voice_id_2": "",
    "voice_id_3": "",
    "voice_id_4": "",
    "language": "en",
    "volume": 100,
    "window_geometry": "640x780",
}


def _default_voice_for(slot: int, tts_provider: str) -> str:
    p = (tts_provider or "").lower().strip()
    if p == "edge":
        return EDGE_DEFAULT_VOICES.get(slot, "")
    if p == "sapi":
        return SAPI_DEFAULT_VOICES.get(slot, "")
    return ELEVENLABS_DEFAULT_VOICES.get(slot, "")

# Curated list of Edge TTS neural voices. EN / PT-PT / ES / JP all included.
EDGE_NEURAL_VOICES: list[str] = [
    # English — British
    "en-GB-RyanNeural", "en-GB-ThomasNeural", "en-GB-OliverNeural",
    "en-GB-SoniaNeural", "en-GB-LibbyNeural", "en-GB-MaisieNeural",
    # English — American
    "en-US-GuyNeural", "en-US-ChristopherNeural", "en-US-EricNeural",
    "en-US-DavisNeural", "en-US-TonyNeural", "en-US-JasonNeural",
    "en-US-AriaNeural", "en-US-JennyNeural", "en-US-MonicaNeural",
    "en-US-SaraNeural", "en-US-NancyNeural",
    # English — AU / IE / NZ / CA
    "en-AU-WilliamNeural", "en-AU-NatashaNeural",
    "en-IE-ConnorNeural", "en-IE-EmilyNeural",
    "en-NZ-MitchellNeural", "en-CA-LiamNeural",
    # Portuguese — Portugal (PT-PT, not PT-BR)
    "pt-PT-DuarteNeural", "pt-PT-RaquelNeural", "pt-PT-FernandaNeural",
    # Spanish — Castilian
    "es-ES-AlvaroNeural", "es-ES-ElviraNeural", "es-ES-AbrilNeural",
    "es-ES-ArnauNeural", "es-ES-DarioNeural", "es-ES-IreneNeural",
    # Japanese
    "ja-JP-KeitaNeural", "ja-JP-NanamiNeural",
    "ja-JP-DaichiNeural", "ja-JP-ShioriNeural",
]

PROVIDERS = ["template", "openai", "anthropic", "gemini", "ollama"]
TTS_PROVIDERS = ["elevenlabs", "edge", "sapi"]
LANGUAGES = {"en": "English", "pt": "Portugues", "es": "Espanol", "jp": "Japanese"}
LANGUAGE_LABELS = {
    "en": "English",
    "pt": "Portugues (PT-PT)",
    "es": "Espanol",
    "jp": "Nihongo",
}
LANGUAGE_GUIDANCE = {
    "en": (
        "Use British F1 broadcast English. Terms: pole position, pit lane, "
        "gap, apex, kerb, DRS, undercut, overcut, out-lap, in-lap."
    ),
    "pt": (
        "Portugues de Portugal, estilo transmissao de F1. "
        "Usa termos: pole position, boxes (pit lane), gap, undercut, overcut, "
        "volta mais rapida, ultrapassagem, bandeira amarela, safety car. "
        "Evita brasileirismos."
    ),
    "es": (
        "Espanol peninsular, estilo retransmision F1. "
        "Usa: pole position, pit lane o boxes, vuelta rapida, adelantamiento, "
        "undercut, overcut, bandera amarilla, coche de seguridad."
    ),
    "jp": (
        "F1 放送スタイルの日本語。専門用語: ポールポジション, ピットレーン, "
        "ファステストラップ, オーバーテイク, セーフティカー, イエローフラッグ, "
        "アンダーカット, オーバーカット。ドラマチックかつ簡潔に。"
    ),
}


def _migrate(data: dict) -> dict:
    """Merge persisted config over defaults. Fill voice_id_3/voice_id_4 from
    defaults when missing, so old 2-voice configs keep working."""
    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    tts_provider = merged.get("tts_provider", "elevenlabs")
    for slot in (3, 4):
        key = f"voice_id_{slot}"
        if not merged.get(key):
            merged[key] = _default_voice_for(slot, tts_provider)
    return merged


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        cfg = DEFAULT_CONFIG.copy()
        for slot in VOICE_SLOTS:
            cfg[f"voice_id_{slot}"] = _default_voice_for(slot, cfg["tts_provider"])
        return cfg
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _migrate(data)
    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
