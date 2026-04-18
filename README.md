# iRacing Commentator

Real-time F1-style broadcast commentary for iRacing. Reads live telemetry,
detects events (overtakes, pit stops, flags, battles, fastest laps, ...),
generates commentary with AI, and speaks it in two alternating voices.

> **Windows-only.** Uses the iRacing shared-memory SDK.

## Features

- **Eleven event types** detected automatically: overtakes, pit entry/exit,
  fastest laps, lead changes, flags, race start, battles, accidents,
  stopped cars, laps-to-go milestones, chequered flag.
- **Five text AI providers:** Template (offline, no key),
  OpenAI, Anthropic Claude, Google Gemini, Ollama (local).
- **Two TTS providers:** ElevenLabs (cloud, paid) and Microsoft Edge TTS
  (free, no key).
- **Four languages:** English, Portuguese (PT-PT), Spanish, Japanese —
  each with authentic F1 broadcast vocabulary.
- **Two alternating personas:** play-by-play (David Croft style) and color
  commentator (Martin Brundle style).
- Commentary **volume slider** (0-100%) that affects only the spoken lines.
- **Test buttons** to validate your API keys before a session.
- **Check for Updates** button pulls the latest release from GitHub.
- Dark Tokyo Night theme.

## 100% free setup (no API keys)

Pick `template` as the Text AI provider and `edge` as the TTS provider —
the app then runs entirely offline and costs nothing.

| | Free tier | Paid |
|---|---|---|
| **Text** | Template (offline), Ollama (local) | OpenAI, Anthropic, Gemini |
| **TTS**  | Microsoft Edge TTS | ElevenLabs |

## Download

Grab the latest `iRacingCommentator.exe` from the
[**Releases page**](https://github.com/qblessedp/iracing-commentator/releases/latest).
No installer — just run the executable. Configuration is saved to
`config.json` next to the `.exe`.

## Quick start

1. Launch iRacing and load into a session (practice, qualifying, or race).
2. Run `iRacingCommentator.exe`.
3. Pick a **Text AI** provider — if you have no API key, choose `template`.
4. Pick a **TTS** provider — `edge` is free.
5. Fill in voice IDs:
   - **ElevenLabs:** paste a Voice ID from your ElevenLabs dashboard.
   - **Edge:** use a neural voice name, e.g. `en-GB-RyanNeural`,
     `pt-PT-DuarteNeural`. Preview at the
     [Microsoft Voice Gallery](https://speech.microsoft.com/portal/voicegallery).
6. Choose a language, adjust the volume, hit **Start**.

## API keys

- **OpenAI:** https://platform.openai.com/api-keys
- **Anthropic:** https://console.anthropic.com/settings/keys
- **Google Gemini:** https://aistudio.google.com/apikey
- **ElevenLabs:** https://elevenlabs.io/app/settings/api-keys
- **Ollama:** no key — install locally from https://ollama.com

Keys are stored only in your local `config.json`.

## Recommended Edge voices

| Language | Speaker 1 (play-by-play) | Speaker 2 (color) |
|---|---|---|
| English  | `en-GB-RyanNeural`   | `en-GB-ThomasNeural` |
| Portuguese | `pt-PT-DuarteNeural` | `pt-PT-RaquelNeural` |
| Spanish  | `es-ES-AlvaroNeural` | `es-ES-ElviraNeural` |
| Japanese | `ja-JP-KeitaNeural`  | `ja-JP-NanamiNeural` |

## Building from source

```bash
git clone https://github.com/qblessedp/iracing-commentator.git
cd iracing-commentator
pip install -r requirements.txt
python main.py          # run directly
python -m pytest tests/ # run test suite (40 tests)
build.bat               # produce dist/iRacingCommentator.exe
```

Requires Python 3.11+ (tested on 3.14).

## Architecture

```
main.py              CommentatorApp - GUI + worker thread (0.5s poll)
gui.py               Tokyo Night dark UI
iracing_reader.py    irsdk wrapper with auto-reconnect
event_detector.py    10 event types with cooldowns and milestones
ai_commentator.py    5 providers, personas, session tone, rate limit
templates.py         Offline phrase-pool generator (~700 lines, 4 langs)
tts_elevenlabs.py    ElevenLabs queue worker
tts_edge.py          Microsoft Edge TTS queue worker
updater.py           GitHub Releases auto-update
config.py            Persistent config.json
```

## License

MIT

## Disclaimer

Not affiliated with iRacing, Formula 1, ElevenLabs, Microsoft, OpenAI,
Anthropic, or Google. Driver names in commentary come from your own
iRacing session telemetry.
