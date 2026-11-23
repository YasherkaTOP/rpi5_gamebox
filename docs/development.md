# Разработка и доставка кода (блок 2)

## Быстрый старт на ПК

Нужны `uv` 0.13.9, Node.js 20+, npm и GNU Make. Python для разработки фиксирует `.python-version` (3.13); `uv` может скачать его сам.

```bash
make setup          # uv sync --frozen --extra dev + npm ci в ui/
make check          # схемы, ruff, mypy, TypeScript, сборка UI, pytest
uv run gamebox smoke
uv run gamebox config validate deploy/config.example.toml
```

`make check` не трогает скрипты блока 1 `deploy/hwcheck/`: они проверялись отдельно и не переписывались в этом блоке.

### Windows

- Нужны Node.js LTS 20+ и npm в `PATH`. Проверка в PowerShell: `node --version`, `npm --version`, `where.exe npm`.
- В `Makefile` на Windows npm вызывается как `cmd /c npm`, потому что GNU Make может не находить `npm.cmd` напрямую через `CreateProcess`.
- Если `npm --version` не работает в самом PowerShell, сначала установите Node.js LTS и откройте новый терминал.
- Предупреждение uv про hardlink/copy на Windows не является ошибкой; при желании можно задать `UV_LINK_MODE=copy`.
- `make device-deploy` вызывает `deploy/device_deploy.py` и требует только `ssh` и `scp` в `PATH`. В Windows установите компонент «OpenSSH Client» (`Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0`) или используйте WSL/Git Bash. Bash для самого деплоя больше не нужен.
- Пароль SSH спрашивается несколько раз. Чтобы не вводить его каждый раз, настройте вход по ключу (`ssh-keygen`, `ssh-copy-id` или ручная запись в `~/.ssh/authorized_keys` на устройстве).
- Пароль sudo вводится один раз в конце установки. Если нужен деплой без пароля sudo, добавьте правило NOPASSWD для установщика — это решение владельца, по умолчанию не включено.

## Раскладка

```text
gamebox/common/      Config, Paths, JSONL-журнал, события, движки, текст, схемы
gamebox/device/      заготовка под ядро (цикл — блоки 7/9)
gamebox/llm/         заготовка под LLM-сервис (блок 4)
gamebox/studio/      заготовка под Студию (блоки 18–20)
gamebox/devtools/    CLI, генерация схем, smoke
ui/                  TypeScript-заготовка оболочки, сборка esbuild в ui/dist
deploy/              конфиг, wheelhouse, упаковка, SSH-деплой, шаблоны systemd
tests/               pytest
docs/journal.md      журнал выполнения и реестр решений
```

План и спецификация в репозиторий не кладутся. `AGENTS.md`, `CLAUDE.md` и `docs/blocks/` не создаются по решению владельца.

## Конфиг

Источник правды — `gamebox/common/config.py`; JSON Schema генерируется в `gamebox/common/schemas/config.schema.json` командой `make schemas`.

```python
from pathlib import Path
from gamebox.common import Config, Paths, load_config

cfg = load_config(Path("deploy/config.example.toml"))
dev = load_config(profile="dev")       # ./var, ./var/run
device = Config(profile="device")     # /var/lib/gamebox, /run/gamebox
```

Профили: `dev` и `device`. Все данные §4.1 берутся через `Paths`: `games`, `packs`, `personas`, `models`, `resources`, `db`, `tts_cache`, `logs`, `audio_debug`, `llm_socket`. Относительные пути в TOML считаются от каталога файла конфига. Значения по умолчанию для железа взяты из `docs/hardware.md`.

## Журнал и события

```python
from gamebox.common import JsonlLogger, EventBus, Utterance

log = JsonlLogger(cfg.paths.logs / "core.jsonl", component="core",
                  max_bytes=cfg.logging.max_bytes, backup_count=cfg.logging.backup_count)
log.log("turn.finished", session_id="s1", turn_id="t1", call_id=None, score=3)

bus = EventBus(maxsize=1024)
unsubscribe = bus.subscribe(Utterance, handler)  # async handler
await bus.publish(event)                         # из петли ядра
bus.publish_threadsafe(event).result(timeout=2)  # из рабочего потока
```

Поля JSONL: `ts`, `component`, `session_id`, `turn_id`, `call_id`, `event`, `level` плюс поля события. Ротация — `core.jsonl.1…N`. События неизменяемы; полезная нагрузка `UiAction` замораживается рекурсивно. Ошибка одного подписчика не останавливает шину.

## Движки и фейки

Интерфейсы в `gamebox/common/engines.py`:

```python
AsrEngine.transcribe(pcm_16k: bytes) -> AsrResult
TtsEngine.synthesize(text: str, voice: str, rate: float = 1.0) -> bytes
LlmBackend.generate(messages, max_tokens, temperature, seed, stop=()) -> AsyncIterator[str]
Embedder.embed(texts: Sequence[str]) -> list[tuple[float, ...]]
Vad.frame_prob(frame: bytes) -> float
```

PCM — signed int16, little-endian, моно. ASR/TTS/VAD/Embedder синхронные; сервисы ядра будут вызывать их через `asyncio.to_thread`. Фейки: `FakeAsr`, `FakeTts`, `FakeLlm`, `FakeEmbedder`, `FakeVad`. Реальные адаптеры и выбор движков — блок 3.

## Текст

`gamebox/common/text.py`:

```python
normalize(text) -> str
tokens(text) -> tuple[str, ...]
number_to_words(number, gender="masc") -> str
words_to_number(text) -> int
parse_number(text) -> int
number_to_ordinal(number, gender="masc") -> str
ordinal_to_number(text) -> int
pluralize(count, ("очко", "очка", "очков")) -> str
with_count(count, forms) -> str
lemmatize(text) -> tuple[str, ...]
similarity(left, right) -> float
best_match(text, candidates, threshold) -> MatchResult | None
phonetic_key(text, stress=None) -> str
```

Диапазон числительных — 0–1 000 000. Порядковые — именительный падеж, род/число; сложные круглые тысячи поддержаны. Фонетический ключ — эвристика для нечёткого сравнения, не полноценная транскрипция.

## Сборка и доставка на устройство

```bash
make wheelhouse       # uv export + pip download aarch64/CPython 3.13, только wheels
make device-package   # .build/source.tar.gz, ui.tar.gz, wheelhouse.tar.gz, release.json
make device-deploy DEVICE=admin@gamebox.local
```

На устройстве должны быть выполнены раскладка и пользователь из блока 1 (`deploy/hwcheck/10_setup_layout.sh`), `python3-venv`, SSH и sudo. Деплой не ходит в интернет с устройства: зависимости ставятся из `wheelhouse/` с проверкой хэшей.

Раскладка релиза:

```text
/opt/gamebox/releases/<release_id>/
  source/             снимок исходников
  .venv/              офлайн-окружение
  ui/dist/            собранный интерфейс
  wheelhouse/         колёса и manifest.json
/opt/gamebox/current -> releases/<release_id>
```

Установка идёт через `ssh -tt`: sudo получает терминал и может запросить пароль. Уборка временного каталога выполняется той же удалённой командой, поэтому пароль SSH спрашивается три раза (mktemp, scp, установка), а не пять.

`install_release.py` проверяет хэши, безопасно распаковывает tar, создаёт venv с `--without-pip` и ставит pip из колеса в wheelhouse (системный `python3-venv`/`ensurepip` не нужен), затем ставит зависимости и колесо `gamebox`, создаёт `/etc/gamebox/config.toml` из примера при отсутствии, готовит каталог данных и runtime-каталог **из конфига** с владельцем `gamebox`, переносит каталог из `.pending-*` в финальный `releases/<id>`, чинит абсолютные shebang в `.venv/bin` (`rewrite_shebangs`), запускает `gamebox smoke` от пользователя `gamebox` **уже из финального пути**, атомарно переключает `current` и перезапускает только уже включённые сервисы. Каталог релиза получает права `0755`, чтобы пользователь сервисов мог его читать. В блоке 2 сервисы не включаются: `deploy/systemd/*.template` — заготовки для блоков 4/7. Полная самопроверка, миграции БД и автоматический откат по health — блок 19.

Порядок «перенос → починка shebang → smoke» важен: console-scripts (`gamebox`, `pip`) хранят абсолютный путь к интерпретатору, и после переименования каталога он указывал бы на удалённый `.pending-*`. Ядро в таком случае отвечает `No such file or directory` на сам скрипт, хотя файл на месте. Smoke из финального пути ловит это до переключения `current`. При отказе на любом шаге каталог релиза удаляется по актуальному пути, поэтому повторный деплой не упирается в «Релиз уже существует».

Длина пути релиза ограничена ядром: строка shebang не может превышать 127 символов. `/opt/gamebox/releases/<id>/.venv/bin/python` занимает ~59 символов, запас есть; при нестандартном `--prefix` глубокий путь сломает запуск.

Проверка установщика на ПК без устройства:

```bash
uv run python deploy/install_release.py .build/local-staging --activate \
  --prefix .build/local-opt --config-dir .build/local-etc \
  --user root --python .venv/bin/python --runtime-dir .build/local-run --skip-services
```

Эта проверка использует колёса текущей архитектуры ПК; боевой `wheelhouse/` собирается под aarch64.

## Политика зависимостей игр

Игры не приносят своих зависимостей. Файл `gamebox/common/allowed_imports.json` создан, но список наполняется и проверка импортов включается в блоках 15/17. Пока это контракт-заготовка, а не действующий запрет.
