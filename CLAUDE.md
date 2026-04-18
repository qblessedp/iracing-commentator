# iRacing Commentator

Programa Windows que lê dados do iRacing em tempo real, gera comentário com AI e converte em voz com ElevenLabs. Estilo broadcast F1.

## Stack

- **Linguagem:** Python 3.14 (testado), 3.11+ suportado
- **Leitura iRacing:** `irsdk` / `pyirsdk` (shared memory Windows)
- **GUI:** tkinter + ttk `clam` (stdlib) — tema escuro Tokyo Night, Segoe UI + Cascadia Mono
- **Text AI:** Template (offline, sem key) / OpenAI / Anthropic / Gemini / Ollama (escolhido na UI)
- **TTS:** ElevenLabs `eleven_multilingual_v2` ou Microsoft Edge TTS (grátis, sem key) — 2 Voice IDs configuráveis
- **Playback:** `pygame-ce` (mixer) — não `pygame` clássico (sem wheels em 3.14)
- **Testes:** pytest
- **Distribuição:** PyInstaller (.exe)

## Estrutura

```
iracing-commentator/
├── main.py              # CommentatorApp — GUI + thread worker, loop 0.5s
├── gui.py               # CommentatorGUI (tkinter) — API keys, voices, lang, log
├── iracing_reader.py    # IRacingReader — irsdk wrapper + reconexão + flags
├── event_detector.py    # EventDetector — 10 tipos de evento, DetectorState
├── ai_commentator.py    # AICommentator — OpenAI/Anthropic/Gemini/Ollama + persona + guidance
├── tts_elevenlabs.py    # TTSElevenLabs — queue worker + pygame playback (cloud, paga)
├── tts_edge.py          # TTSEdge — mesma interface, usa edge-tts (grátis, sem key)
├── templates.py         # TemplateCommentator — gerador offline, phrase pools por evento/língua
├── config.py            # load/save config.json + PROVIDERS/LANGUAGES/GUIDANCE
├── requirements.txt
├── CLAUDE.md
└── tests/
    ├── test_event_detector.py   # 13 testes
    ├── test_ai_commentator.py   # 14 testes
    └── test_tts_elevenlabs.py   # 9 testes
```

## Fluxo

1. GUI arranca → utilizador preenche API keys, Voice IDs, língua
2. Botão **Start** → `_worker` thread liga ao iRacing via shared memory
3. Loop (0.5s): `snapshot → detect events → AI generate → ElevenLabs speak`
4. Comentários alternados: Speaker 1 (play-by-play) / Speaker 2 (color)
5. Botão **Stop** → thread para, TTS worker drenado, reader desliga

## Config

`config.json` gerado automaticamente:
- `text_provider`: `template` | `openai` | `anthropic` | `gemini` | `ollama`
- `text_api_key`, `elevenlabs_api_key`
- `tts_provider`: `elevenlabs` | `edge`
- `voice_id_1`, `voice_id_2` (IDs ElevenLabs OU nomes Edge tipo `en-GB-RyanNeural`)
- `language`: `en` | `pt` | `es` | `jp`
- `volume`: 0-100 (só afecta o audio dos comentários)

## Eventos detetados

| Evento | Trigger |
|---|---|
| `overtake` | posição melhora (com driver, from_pos, to_pos) |
| `pit_entry` / `pit_exit` | transição boolean `on_pit` |
| `fastest_lap` | novo best lap time |
| `lead_change` | líder mudou (new/old driver) |
| `flag_change` | green, yellow, red, blue, white, caution, checkered |
| `race_start` | primeira `green` em sessão Race (fires once) |
| `battle` | gap < 1s entre consecutivos, cooldown 30s por par |
| `accident_suspected` | parado fora das boxes 4+ ticks |
| `laps_to_go` | milestones 10 / 5 / 3 / 1 |
| `checkered` | bandeira quadriculada (fires once) |

## AI Commentator

- **Personas:**
  - Speaker 1 — David Croft style (urgent play-by-play)
  - Speaker 2 — Martin Brundle style (color, dry wit)
- **Tom por sessão:** `practice` (analítico), `qualifying` (tenso), `race` (dramático)
- **Priorização:** `EVENT_PRIORITY` — checkered(100) > race_start > accident > lead_change > flag_change > laps_to_go > fastest_lap > overtake > battle > pits
- **Rate limit:** `MIN_INTERVAL_SEC = 2.5s`
- **Anti-repetição:** `deque(maxlen=6)` com histórico injectado no user prompt
- **Error handling:** exception → retorna `{speaker:0, text:""}` em vez de crashar

## Línguas + vocabulário F1

Cada língua tem um bloco `LANGUAGE_GUIDANCE` em `config.py` injectado no system prompt:
- **EN:** British F1 terms (DRS, apex, kerb, undercut, overcut)
- **PT:** boxes, volta mais rápida, ultrapassagem, bandeira amarela — evita brasileirismos
- **ES:** pole position, adelantamiento, vuelta rápida, coche de seguridad
- **JP:** ポールポジション, オーバーテイク, ファステストラップ, セーフティカー

Todas validadas end-to-end com ElevenLabs `eleven_multilingual_v2`.

## TTS (ElevenLabs)

- **Queue:** `queue.Queue(maxsize=8)` + thread worker daemon
- **Backpressure:** fila cheia → drop com warning
- **Error recovery:** exceção no synth não mata o worker
- **Lazy init:** client ElevenLabs e pygame.mixer só criados no primeiro uso
- **`validate()`:** verifica API key + voice IDs antes de arrancar

## Fases

- [x] **Fase 1** — Estrutura base + GUI esqueleto
- [x] **Fase 2** — Dependências + ligação real ao iRacing (reconexão, campos ricos, flags)
- [x] **Fase 3** — Deteção de eventos ricos (10 tipos, cooldowns, milestones)
- [x] **Fase 4** — Text AI com personas, tom por sessão, priorização, rate-limit, histórico
- [x] **Fase 5** — ElevenLabs TTS com queue worker, validação, error recovery (testado real)
- [x] **Fase 6** — Línguas EN/PT/ES/JP com vocabulário F1 (testado multilingue real)
- [x] **Fase 7** — Testes E2E integrados (4), reconexão automática, log colorido por speaker, `.gitignore`
- [x] **Fase 7.5** — UI dark theme (Tokyo Night), Segoe UI + Cascadia Mono, status colorido, botão Accent
- [x] **Fase 8** — PyInstaller `.exe` onefile windowed (37 MB), `build.bat` para rebuilds
- [x] **Fase 8.1** — Hardening: erros AI/TTS borbulham para o log; config persiste ao lado do .exe; strip de whitespace em keys/voice IDs; certifi/httpx/httpcore embutidos
- [x] **Fase 8.2** — Botões **Test** ao lado de cada API key (Text AI + ElevenLabs). Verde ✓ se a key autentica, vermelho ✗ se falha. Teste corre em thread daemon e actualiza UI via `self.after()`. Usa `AICommentator.test_key()` + `TTSElevenLabs.validate()`.
- [x] **Fase 8.3** — 4º provider: **Google Gemini** (`gemini-2.0-flash`). `PROVIDERS = ["openai", "anthropic", "gemini", "ollama"]`. `AICommentator._call_gemini()` + branch `"gemini"` em `test_key()` via `google.generativeai`. `requirements.txt` + `build.bat` (hidden-import + collect-submodules google.generativeai/google.ai + collect-data). Exe cresceu para ~62 MB (deps do Google SDK).
- [x] **Fase 8.4** — Slider de volume (Tokyo Night `Accent.Horizontal.TScale`) só para comentários. 0-100%, live-update via `pygame.Sound.set_volume()`, auto-persist debounced 400ms em `config.json`. `TTSElevenLabs.set_volume()` + `TTSEdge.set_volume()` + `CommentatorApp.set_volume()` encadeados.
- [x] **Fase 8.6** — **Template provider offline** (`templates.py::TemplateCommentator`). Zero dependencies, zero API key, zero tokens — 100% offline. `PROVIDERS = ["template", "openai", "anthropic", "gemini", "ollama"]`. ~700 frases curadas em 4 línguas (en/pt/es/jp) × 15+ chaves de evento (overtake, pit_entry/exit, fastest_lap, lead_change, flag_green/yellow/red/blue/white/checkered/generic, race_start, battle, accident_suspected, laps_to_go, checkered). Anti-repetição via `deque(maxlen=8)` por tag. `AICommentator.__init__` instancia `TemplateCommentator` quando provider=="template"; `generate()` faz short-circuit antes do LLM; `test_key("template",…)` devolve `(True, "OK (offline)")`. UI: dropdown com "template" como primeira opção; campo API Key acinzenta quando template é escolhido (mesmo padrão do edge TTS). Placeholders safe via `_SafeDict` (missing keys → "?"). Combinado com Edge TTS → app 100% grátis sem configuração de keys.
- [x] **Fase 8.5** — 2º provider de TTS: **Microsoft Edge TTS** (grátis, sem API key). Novo módulo `tts_edge.py::TTSEdge` com interface idêntica a `TTSElevenLabs` (start/stop/speak/validate/set_volume/last_error). `TTS_PROVIDERS = ["elevenlabs", "edge"]` em `config.py`. Dropdown "Provider" na UI desactiva o campo API Key quando edge é escolhido. Botão **Test** funciona para ambos. Usa vozes neurais MS tipo `en-GB-RyanNeural`, `pt-PT-DuarteNeural`. Requires `edge-tts>=6.1.0` + `aiohttp`. Exe cresceu para ~64 MB.
- [x] **Fase 9.1** — v1.0.7: expansão do pool de frases `accident_suspected` nas 4 línguas (~15 novas frases por língua) em `templates.py`. README actualizado: "Eleven event types" + accidents na lista. Teste real do fluxo auto-update (v1.0.6 → v1.0.7).
- [x] **Fase 9** — GitHub release (v1.0.6 publicado em `qblessedp/iracing-commentator`)
  - Repo público: https://github.com/qblessedp/iracing-commentator
  - `README.md` com features, setup 100% grátis, API keys links, vozes recomendadas, arquitetura
  - `LICENSE` MIT
  - `updater.py::check_and_apply()` — consulta `/releases/latest`, compara `tag_name` com `APP_VERSION`, descarrega asset, gera `.bat` de swap (`move` + relaunch), chama `os._exit(0)` após detach
  - Botão **Check for Updates** no `btn_frame`, thread daemon, confirm via `messagebox.askyesno`
  - Título da janela mostra `v{APP_VERSION}`
  - `build.bat`: `--hidden-import templates --hidden-import updater`

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
| `ai_commentator` | 14 | priorização, rate limit, personas, tone, history, guidance, error handling |
| `tts_elevenlabs` | 9 | queue, empty/missing inputs, routing, error recovery, stop, validate |
| `e2e_pipeline` | 4 | snapshot→detect→AI→TTS end-to-end, flag change, rate limit, no-op path |

Todos os testes correm sem API keys reais (mocks).

## Notas técnicas

- `irsdk` só funciona em Windows (shared memory Lemans)
- `pygame-ce` em vez de `pygame` (wheels para Python 3.14)
- GUI testada headless: 640×720, mínimo 600×640, dark theme
- Paleta: bg `#1a1b26`, panel `#24283b`, text `#c0caf5`, accent `#7aa2f7`, speaker2 `#ff9e64`
- API keys devem ser guardadas apenas em `config.json` (NUNCA em código)
- `config.json` é gravado ao lado do `.exe` (via `sys.executable` quando `sys.frozen`)
- API keys e Voice IDs são sempre `.strip()` antes de uso — previne `LocalProtocolError: Illegal header value` quando a key tem `\n` final
- Erros de AI/TTS têm `[caused by <TipoErro>: <mensagem>]` com a causa raiz (chain `__cause__`/`__context__`)
- Teste real realizado com vozes Charlie + George (ElevenLabs), 4 línguas

## Próximos passos

- Fase 7: testes E2E com iRacing real + OpenAI/Anthropic real
- Fase 8: empacotar com PyInstaller (ícone, splash, onefile)
- Fase 9: publicar em GitHub Releases com auto-update check
