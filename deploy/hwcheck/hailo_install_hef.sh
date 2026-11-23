#!/usr/bin/env bash
# Game Box. Ручная установка модели .hef в hailo-ollama (когда /api/pull недоступен без VPN).
#
# Как hailo-ollama 5.1.1 хранит модели (выяснено в блоке 1 через strace):
#   манифест: /usr/share/hailo-ollama/models/manifests/<имя>/<тег>/manifest.json  (поле hef_h10h = sha256 файла)
#   файл:     /usr/share/hailo-ollama/models/blob/sha256_<sha256>
#   конфиг:   ~/.config/hailo-ollama/hailo-ollama.json, иначе /etc/xdg/hailo-ollama/hailo-ollama.json
#             (ВНИМАНИЕ: пустая папка ~/.config/hailo-ollama роняет сервер — parse_error)
#
# Запуск:  ./hailo_install_hef.sh <имя:тег> <файл.hef> [базовая_модель:тег]
# Пример:  ./hailo_install_hef.sh qwen2-instruct:1.5b ~/Qwen2-1.5B-Instruct.hef qwen2:1.5b
# Базовая модель даёт шаблон чата и параметры генерации; берите того же семейства.
set -euo pipefail
NAME="${1:?имя:тег}"; HEF="${2:?файл .hef}"; BASE="${3:-qwen2:1.5b}"
M=/usr/share/hailo-ollama/models
n="${NAME%%:*}"; t="${NAME##*:}"; bn="${BASE%%:*}"; bt="${BASE##*:}"
BASE_MAN="$M/manifests/$bn/$bt/manifest.json"
[ -f "$HEF" ] || { echo "нет файла $HEF"; exit 1; }
[ -f "$BASE_MAN" ] || { echo "нет базового манифеста $BASE_MAN"; exit 1; }

arch="$(hailortcli parse-hef "$HEF" 2>/dev/null | grep -oE 'HAILO[0-9A-Z]+' | head -1 || true)"
echo "Архитектура HEF: ${arch:-не определена}"
[ -z "$arch" ] || [ "$arch" = HAILO10H ] || { echo "Файл не для Hailo-10H — не ставлю"; exit 1; }

H="$(sha256sum "$HEF" | cut -d' ' -f1)"
echo "sha256: $H"
OLD="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["hef_h10h"])' "$BASE_MAN")"
sudo mkdir -p "$M/manifests/$n/$t"
sed "s/$OLD/$H/" "$BASE_MAN" | sudo tee "$M/manifests/$n/$t/manifest.json" > /dev/null
sudo install -m 0644 "$HEF" "$M/blob/sha256_$H"
echo "Готово: $NAME → $M/blob/sha256_$H"
echo "Перезапусти hailo-ollama (pkill hailo-ollama) и проверь: curl -s localhost:8000/hailo/v1/list"
