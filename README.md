# Game Box

Платформа настольной игровой приставки на Raspberry Pi 5 + Hailo-10H: голос, экран, игры-плагины, Студия на ПК.

- Паспорт железа: [`docs/hardware.md`](docs/hardware.md). Первичная настройка устройства: [`docs/device-setup.md`](docs/device-setup.md).
- Разработка, контракты и деплой: [`docs/development.md`](docs/development.md).
- Журнал выполнения и реестр решений: [`docs/journal.md`](docs/journal.md).
- Версии: [`versions.lock`](versions.lock), `uv.lock`, `ui/package-lock.json`.

## Состояние

| Блок | Статус |
| --- | --- |
| 1. Железо, ОС, системная база | закрыт с открытыми пунктами (см. журнал и `docs/hardware.md`) |
| 2. Фундамент кода | реализован; `make check` и сборка aarch64-wheelhouse проходят на ПК, подтверждение `device-deploy` на Pi ожидается |

## Быстрый старт

```bash
make setup
make check
uv run gamebox smoke
```

Доставка на устройство:

```bash
make device-deploy DEVICE=admin@gamebox.local
```

Подробности и ограничения — в [`docs/development.md`](docs/development.md).
