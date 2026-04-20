# iRacing Commentator

Programa Windows que lê dados do iRacing em tempo real, gera comentário com AI (ou templates offline) e converte em voz (ElevenLabs cloud / Microsoft Edge TTS / Windows SAPI). Estilo broadcast F1, 4 comentadores com personalidades distintas, filler de factos quando não há eventos.

## Stack

- **Linguagem:** Python 3.14 (testado), 3.11+ suportado
- **Leitura iRacing:** `irsdk` / `pyirsdk` (shared memory Windows)
- **GUI:** tkinter + ttk `clam` (stdlib) — tema escuro Tokyo Night, Segoe UI + Cascadia Mono
- **Text AI:** Template (offline) / OpenAI / Anthropic / Gemini / Ollama (escolhido na UI)
- **TTS:** ElevenLabs `eleven_multilingual_v2` / Microsoft Edge TTS (grátis, precisa net) / Windows SAPI via `pyttsx3` (100% offline) — 4 Voice IDs configuráveis
- **Factos filler:** `facts_provider.py` + JSON curados em `data/` + YAML do iRacing
- **Playback:** `pygame-ce` (ElevenLabs/Edge) ou SAPI directo (pyttsx3)
- **Testes:** pytest — 40 testes
- **Distribuição:** PyInstaller (.exe onefile windowed)

## Estrutura

```
iracing-commentator/
├── main.py              # CommentatorApp — GUI + worker thread, loop 0.5s, filler throttle
├── gui.py               # CommentatorGUI (tkinter) — API keys, 4 voices, lang, log
├── iracing_reader.py    # IRacingReader — irsdk wrapper + reconexão + flags
├── event_detector.py    # EventDetector — 10 tipos de evento, DetectorState
├── ai_commentator.py    # AICommentator — 4 personas + EVENT_SPEAKER_AFFINITY + generate_filler
├── facts_provider.py    # pick_filler_subject / get_driver_facts / get_track_facts (offline)
├── tts_elevenlabs.py    # TTSElevenLabs — cloud, 4 speakers, queue worker
├── tts_edge.py          # TTSEdge — Microsoft Edge TTS neural (grátis, precisa net)
├── tts_sapi.py          # TTSSapi — Windows SAPI via pyttsx3 (100% offline)
├── templates.py         # TemplateCommentator — phrase pools + generate_filler offline
├── config.py            # load/save + migração 2→4 vozes + defaults por provider
├── updater.py           # check_and_apply GitHub releases, APP_VERSION=1.1.1
├── data/
│   ├── track_facts.json     # ~10 pistas curadas (length_km, corners, lap_record, fun_fact)
│   └── driver_facts.json    # ~15 pilotos curados (irating_peak, known_for, home_track)
├── requirements.txt
├── CLAUDE.md
└── tests/
    ├── test_event_detector.py   # 13 testes
    ├── test_ai_commentator.py   # 14 testes
    ├── test_tts_elevenlabs.py   # 9 testes
    └── test_e2e_pipeline.py     # 4 testes
```

## Fluxo

1. GUI arranca → utilizador escolhe providers, API keys, 4 Voice IDs, língua, volume
2. Botão **Start** → `_worker` thread liga ao iRacing via shared memory
3. Loop (0.5s):
   - `reader.get_snapshot()` → dados actuais
   - `detector.detect(snapshot)` → lista de eventos
   - **Se houver eventos:** `commentator.generate()` → `_pick_speaker(event_type)` via affinity → `tts.speak(text, speaker)`
   - **Se não houver eventos há >7s E último filler há >30s:** `facts_provider.pick_filler_subject()` → `commentator.generate_filler()` → `tts.speak(filler_text, speaker)`
4. Botão **Stop** → thread para, TTS worker drenado, reader desliga

## Config (`config.json`)

| Campo | Valores | Notas |
|---|---|---|
| `text_provider` | `template` \| `openai` \| `anthropic` \| `gemini` \| `ollama` | `template` = totalmente offline |
| `text_api_key` | string | acinzentada na UI quando provider=template |
| `tts_provider` | `elevenlabs` \| `edge` \| `sapi` | `sapi` = 100% offline |
| `elevenlabs_api_key` | string | acinzentada na UI quando tts_provider ∈ {edge, sapi} |
| `voice_id_1..4` | string | IDs ElevenLabs OU nome Edge (`en-GB-RyanNeural`) OU nome SAPI (`David`) |
| `language` | `en` \| `pt` \| `es` \| `jp` | |
| `volume` | 0–100 | live-update + persist debounced 400ms |

### Migração retrocompatível
`config._migrate()` aceita configs antigos de 2 vozes; preenche `voice_id_3` e `voice_id_4` via `_default_voice_for(slot, tts_provider)`. Defaults por provider em `ELEVENLABS_DEFAULT_VOICES`, `EDGE_DEFAULT_VOICES`, `SAPI_DEFAULT_VOICES`.

## Eventos detetados

| Evento | Trigger |
|---|---|
| `overtake` | posição melhora (driver, from_pos, to_pos) |
| `pit_entry` / `pit_exit` | transição boolean `on_pit` |
| `fastest_lap` | novo best lap time |
| `lead_change` | líder mudou (new/old driver) |
| `flag_change` | green, yellow, red, blue, white, caution, checkered |
| `race_start` | primeira `green` em sessão Race (fires once) |
| `battle` | gap < 1s entre consecutivos, cooldown 30s por par |
| `accident_suspected` | parado fora das boxes 4+ ticks |
| `laps_to_go` | milestones 10 / 5 / 3 / 1 |
| `checkered` | bandeira quadriculada (fires once) |

## AI Commentator (4 personas)

| Speaker | Persona | Estilo |
|---|---|---|
| 1 | **Play-by-play** | David Croft — urgente, crisp, narrativo |
| 2 | **Pit-lane color analyst** | Martin Brundle — conversacional, dry wit, estratégia/pneus |
| 3 | **Veteran ex-driver** | Grizzled, "back in my day", racecraft, técnica |
| 4 | **Hype commentator** | Over-the-top, CAPS pontuais, "UNBELIEVABLE", "OH MY WORD" |

### Afinidade evento → speakers (`EVENT_SPEAKER_AFFINITY`)

```
lead_change   → [1, 4]      battle     → [2, 3]
checkered     → [1, 4]      overtake   → [2, 4]
race_start    → [1, 4]      accident   → [2, 3]
laps_to_go    → [1, 3]      pit_entry  → [3, 2]
flag_change   → [1, 2]      pit_exit   → [3, 2]
fastest_lap   → [4, 1]
```

### Selecção (`_pick_speaker(event_type)`)
1. Percorre a lista de afinidade: primeiro speaker ≠ `_last_speaker` ganha.
2. Fallback: round-robin 1→2→3→4 a partir do último.

Evita monotonia sem estrangular personas raras (ex: pit-reporter numa corrida sem pit stops).

### Outras características
- **Tom por sessão:** `practice` (analítico), `qualifying` (tenso), `race` (dramático). `SESSION_TONE` tem proibições duras (quali NUNCA diz "race"/"laps to go"; practice NUNCA diz "lights out").
- **Priorização:** `EVENT_PRIORITY` — checkered(100) > race_start(95) > accident(90) > lead_change(85) > flag_change(80) > laps_to_go(75) > fastest_lap(70) > overtake(60) > battle(55) > pit_exit(40) > pit_entry(35)
- **Rate limit:** `MIN_INTERVAL_SEC = 2.5s`
- **Anti-repetição:** `deque(maxlen=6)` com histórico injectado no user prompt
- **Error handling:** exception → `{speaker:0, text:""}` em vez de crashar
- **`STYLE_DIRECTIVE`:** obriga o LLM a soar como broadcaster ao vivo (contractions, interjeições, frases incompletas permitidas)

## Filler (factos entre eventos)

### `facts_provider.py`
- `get_track_facts(name)` → lê `data/track_facts.json` (campos: `length_km`, `corners`, `lap_record`, `elevation_m`, `opened_year`, `fun_fact`).
- `get_driver_facts(name, yaml_data)` → merge YAML do iRacing (`CarNumber`, `TeamName`, `IRating`, `LicString`, `UserName`) com `data/driver_facts.json` (campos: `irating_peak`, `known_for`, `home_track`, `fun_fact`).
- `pick_filler_subject(session_state)` → alterna driver/track, cache TTL 5 min evita repetir subject.

### `ai_commentator.generate_filler(subject, session_type, lang, guidance)`
- `_filler_speaker(kind)` — hype (4) faz ~50% do filler de pilotos, veterano (3) ~35%, color (2) ~15%. Para track, veterano e play-by-play dominam.
- Evita repetir `_last_speaker`.
- `FILLER_STYLE_DIRECTIVE` — "weave naturally, never 'fun fact', never 'did you know', one short line, in character".
- Template provider curto-circuita para `TemplateCommentator.generate_filler()` → suporta 100% offline.

### Throttle (em `main.py`)
```python
SILENCE_THRESHOLD_SEC = 7.0   # silêncio mínimo antes de filler
FILLER_COOLDOWN_SEC = 30.0    # intervalo entre fillers
```

## TTS backends (3)

Todos partilham a mesma interface: `start() / stop() / speak(text, speaker) / validate() / set_volume(0-1) / last_error`.

### `tts_elevenlabs.py::TTSElevenLabs` (cloud, pago)
- `eleven_multilingual_v2`, 4 voice slots, defaults Adam/Rachel/Josh/Domi.
- Queue `maxsize=8`, backpressure com warning, error recovery no worker.
- Lazy init de client + pygame mixer.
- `validate()` verifica API key + todos os voice IDs.

### `tts_edge.py::TTSEdge` (grátis, precisa net)
- `edge-tts` neural MS, 4 voices distintas (Ryan/Jenny/Thomas/Eric).
- Mesma arquitectura de queue/worker/mixer que ElevenLabs.
- Sem API key. Usa websocket MS em runtime → requer internet.

### `tts_sapi.py::TTSSapi` (100% offline)
- `pyttsx3` → Windows Speech API directo. Zero rede.
- Engine criado **lazy dentro do worker thread** (COM/SAPI não é thread-safe cross-thread).
- `_match_voice_id()` faz substring match case-insensitive contra vozes instaladas (hint "David" → "Microsoft David Desktop"). Se nenhuma bater, SAPI usa o default do sistema.
- `DEFAULT_RATE` distinto por persona (195/175/165/210 WPM) → as 4 personas distinguem-se por cadência mesmo com apenas 1 voz SAPI instalada.
- `validate()` confirma pyttsx3 importável e devolve número de vozes instaladas.
- `list_installed_voices()` disponível para futura UI picker.

## Combinações de uso

| Text Provider | TTS Provider | Internet? | API keys? |
|---|---|---|---|
| `openai` / `anthropic` / `gemini` | `elevenlabs` | Sim | Sim (ambas) |
| `template` | `edge` | Sim | Não |
| `template` | `sapi` | **Não** | **Não** |
| `ollama` (local) | `sapi` | Não (se Ollama local) | Não |

**Modo 100% offline:** `template` + `sapi` → zero rede, zero keys, zero cloud.

## Línguas + vocabulário F1

Bloco `LANGUAGE_GUIDANCE` em `config.py` injectado no system prompt:
- **EN:** British F1 terms (DRS, apex, kerb, undercut, overcut)
- **PT:** boxes, volta mais rápida, ultrapassagem, bandeira amarela — evita brasileirismos
- **ES:** pole position, adelantamiento, vuelta rápida, coche de seguridad
- **JP:** ポールポジション, オーバーテイク, ファステストラップ, セーフティカー

Template offline (`templates.py`) tem phrase pools em todas as 4 línguas × 15+ chaves de evento × 3 session types. Filler offline também é 4-lingual.

## Comandos

```bash
pip install -r requirements.txt
python main.py
python -m pytest tests/         # 40 testes
build.bat                        # gera dist/iRacingCommentator.exe
```

## Testes

| Módulo | Testes | Cobertura principal |
|---|---|---|
| `event_detector` | 13 | overtake, pit, fastest lap, lead, flags, race_start, battle, cooldown, stopped, laps_to_go, checkered |
| `ai_commentator` | 14 | priorização, rate limit, 4 personas, affinity rotation, tone, history, guidance, error handling |
| `tts_elevenlabs` | 9 | queue, empty/missing inputs, 4-speaker routing, error recovery, stop, validate |
| `e2e_pipeline` | 4 | snapshot→detect→AI→TTS end-to-end, flag change, rate limit, no-op path |

Todos os testes correm sem API keys reais (mocks) e sem SAPI instalado (validate usa try/except).

## Fases

- [x] **Fase 1–8** — Base, iRacing, eventos, AI, ElevenLabs, línguas, PyInstaller, hardening
- [x] **Fase 8.2** — Botões Test ao lado das keys, indicadores ✓/✗
- [x] **Fase 8.3** — Gemini como 4º text provider
- [x] **Fase 8.4** — Slider volume live + persist debounced
- [x] **Fase 8.5** — TTSEdge (edge-tts MS neural)
- [x] **Fase 8.6** — TemplateCommentator offline
- [x] **Fase 9** — GitHub release v1.0.6, README, LICENSE MIT, updater
- [x] **Fase 9.1** — v1.0.7: mais frases accident_suspected
- [x] **Fase 9.2** — v1.0.8: tom por sessão separado (practice/qualifying/race) + STYLE_DIRECTIVE
- [x] **Fase 10 — v1.0.9: 4 comentadores + filler facts + SAPI offline** (actual)
  - Speakers 3 (veteran) e 4 (hype) com personas distintas
  - `EVENT_SPEAKER_AFFINITY` + `_pick_speaker()` com anti-repetição e fallback round-robin
  - `facts_provider.py` + `data/*.json` + merge YAML iRacing
  - `generate_filler()` + throttle 7s / 30s
  - `tts_sapi.py::TTSSapi` (pyttsx3) — 3º backend TTS, 100% offline
  - 4 voice slots em config com migração 2→4
  - GUI com 4 voice pickers etiquetados por persona
  - `build.bat` hidden-imports `pyttsx3`/`pyttsx3.drivers.sapi5`/`tts_sapi`/`facts_provider` + `--add-data "data;data"`

## Notas técnicas

- `irsdk` só funciona em Windows (shared memory Lemans)
- `pygame-ce` em vez de `pygame` (wheels para Python 3.14)
- `pyttsx3` + `pywin32` + `comtypes` são Windows-only (consistente com `irsdk`)
- **SAPI é thread-sensitive:** engine é criado dentro do worker thread de `TTSSapi._run()`, nunca no main thread
- **SAPI voice matching é tolerante:** substring match case-insensitive; se nenhuma voz bater, usa default do sistema
- GUI testada headless: 640×720, mínimo 600×640, dark theme
- Paleta: bg `#1a1b26`, panel `#24283b`, text `#c0caf5`, accent `#7aa2f7`, speaker2 `#ff9e64`
- API keys devem ser guardadas apenas em `config.json` (NUNCA em código)
- `config.json` é gravado ao lado do `.exe` (via `sys.executable` quando `sys.frozen`)
- API keys e Voice IDs são sempre `.strip()` antes de uso — previne `LocalProtocolError: Illegal header value`
- Erros de AI/TTS têm `[caused by <TipoErro>: <mensagem>]` com a causa raiz (chain `__cause__`/`__context__`)
- `data/*.json` são empacotados no `.exe` via PyInstaller `--add-data "data;data"`
- `facts_provider` descobre `data/` via `_base_dir()` que respeita `sys.frozen` + `_MEIPASS`

## Próximos passos (opcionais)

- Mais factos curados em `data/driver_facts.json` (comunidade contribui via PR)
- [x] ~~Voice preview na UI~~ → implementado (v1.1.0): botão `▶` por slot, frase de teste por persona, thread dedicada, re-enable após 8s
- Detecção automática de idioma do YAML (auto-seleccionar EN/PT)
- Suporte macOS/Linux para equivalentes SAPI (NSSpeechSynthesizer / espeak) — actualmente Windows-only
