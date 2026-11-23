# Game Box

Платформа настольной игровой приставки на Raspberry Pi 5 + Hailo-10H: голос, экран, игры-плагины, Студия на ПК.

- Паспорт железа: [`docs/hardware.md`](docs/hardware.md). Первичная настройка устройства: [`docs/device-setup.md`](docs/device-setup.md).
- Версии внешних зависимостей: [`versions.lock`](versions.lock) (черновик блока 1).

## Состояние

| Блок | Статус |
| --- | --- |
| 1. Железо, ОС, системная база | закрыт с открытыми пунктами (см. журнал и `docs/hardware.md`); перед блоком 7 — отключить рабочий стол |
| 2. Фундамент кода | не начат: создаёт пакет `gamebox/`, `pyproject`, `Makefile` (`make check`) |

## Раскладка сейчас

```
docs/
  hardware.md               паспорт железа
  device-setup.md           первичная настройка и проверки
  hardware-report/<дата>/   сырые отчёты со скриптов проверки
deploy/hwcheck/             скрипты проверки железа
versions.lock
```
