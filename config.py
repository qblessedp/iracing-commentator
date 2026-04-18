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

DEFAULT_CONFIG = {
    "text_provider": "openai",
    "text_api_key": "",
    "tts_provider": "elevenlabs",
    "elevenlabs_api_key": "",
    "voice_id_1": "",
    "voice_id_2": "",
    "language": "en",
    "volume": 100,
}

PROVIDERS = ["template", "openai", "anthropic", "gemini", "ollama"]
TTS_PROVIDERS = ["elevenlabs", "edge"]
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


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
