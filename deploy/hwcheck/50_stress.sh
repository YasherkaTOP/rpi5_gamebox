#!/usr/bin/env bash
# Game Box, блок 1. Стресс-тест питания и температуры.
# Нагрузка: CPU (stress-ng, 4 потока), запись на SSD, громкий звук по HDMI, генерация на Hailo в цикле.
# Каждые 5 с пишет: температуру, частоту, флаги get_throttled, напряжение 5 В, обороты вентилятора.
#
# Запуск (перед каждым прогоном — перезагрузка, чтобы сбросить флаги throttled):
#   sudo TAG=screen_from_pi DURATION_MIN=15 ./50_stress.sh      # экран питается от USB Pi
#   sudo TAG=final DURATION_MIN=60 ./50_stress.sh                # итоговый час в выбранной схеме
# Переменные: WITH_CPU/WITH_SSD/WITH_AUDIO/WITH_HAILO=0|1, MODEL=<имя модели hailo-ollama, по умолчанию qwen2-instruct:1.5b>
# Результат: ~/block1-report/stress_<TAG>/{monitor.csv,hailo_loop.csv,summary.json,dmesg_new.txt}
set -u
[ "$(id -u)" -eq 0 ] || { echo "Запусти через sudo"; exit 1; }
TAG="${TAG:-run}"
DURATION_MIN="${DURATION_MIN:-60}"
WITH_CPU="${WITH_CPU:-1}"; WITH_SSD="${WITH_SSD:-1}"; WITH_AUDIO="${WITH_AUDIO:-1}"; WITH_HAILO="${WITH_HAILO:-1}"
MODEL="${MODEL:-qwen2-instruct:1.5b}"
U="${SUDO_USER:-root}"
H="$(getent passwd "$U" | cut -d: -f6)"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT:-$H/block1-report}/stress_${TAG}"
mkdir -p "$OUT"
PLAY_DEV="${PLAY_DEV:-$(python3 "$HERE/b1common.py" play-dev)}"
START=$(date +%s)
END=$(( START + DURATION_MIN * 60 ))
STRESS_FILE=/var/tmp/gb_stress.bin

cleanup() {
  jobs -p | xargs -r kill 2>/dev/null
  pkill -f "stress-ng --cpu" 2>/dev/null
  rm -f "$STRESS_FILE"
  dmesg > "$OUT/dmesg_after.txt"
  diff <(cat "$OUT/dmesg_before.txt") "$OUT/dmesg_after.txt" | grep '^>' > "$OUT/dmesg_new.txt" || true
  python3 "$HERE/b1common.py" summarize-stress "$OUT" > /dev/null 2>&1
  chown -R "$U":"$U" "$OUT" 2>/dev/null
  echo; echo "Итог: $OUT/summary.json"; cat "$OUT/summary.json" 2>/dev/null
}
trap cleanup EXIT
trap 'exit 130' INT TERM

dmesg > "$OUT/dmesg_before.txt"
{
  echo "tag=$TAG duration_min=$DURATION_MIN cpu=$WITH_CPU ssd=$WITH_SSD audio=$WITH_AUDIO hailo=$WITH_HAILO model=$MODEL"
  echo "play_dev=$PLAY_DEV start=$(date -Is)"
  vcgencmd get_throttled
} > "$OUT/params.txt"

if [ "$WITH_CPU" = 1 ]; then
  stress-ng --cpu 4 --timeout "${DURATION_MIN}m" --quiet &
fi

if [ "$WITH_SSD" = 1 ]; then
  ( while [ "$(date +%s)" -lt "$END" ]; do
      dd if=/dev/zero of="$STRESS_FILE" bs=1M count=256 oflag=direct conv=fsync status=none
      rm -f "$STRESS_FILE"; sleep 20
    done ) &
fi

if [ "$WITH_AUDIO" = 1 ]; then
  python3 "$HERE/b1common.py" gen-noise /var/tmp/gb_noise.wav 10
  ( while [ "$(date +%s)" -lt "$END" ]; do aplay -q -D "$PLAY_DEV" /var/tmp/gb_noise.wav || sleep 2; done ) &
fi

if [ "$WITH_HAILO" = 1 ]; then
  if ! curl -s --max-time 3 http://localhost:8000/hailo/v1/list >/dev/null; then
    echo "hailo-ollama не отвечает — запускаю от $U"
    sudo -u "$U" bash -c 'nohup hailo-ollama > /tmp/hailo-ollama.log 2>&1 &'
    for _ in $(seq 30); do curl -s --max-time 2 http://localhost:8000/hailo/v1/list >/dev/null && break; sleep 2; done
  fi
  # Предварительная проверка: hailo-ollama отвечает HTTP 200 даже на "model not found"
  if curl -s --max-time 120 -H 'Content-Type: application/json' http://localhost:8000/api/chat \
       -d '{"model":"'"$MODEL"'","stream":false,"messages":[{"role":"user","content":"да"}]}' | grep -q '"error"'; then
    echo "ОШИБКА: модель $MODEL недоступна в hailo-ollama (см. /hailo/v1/list). Стресс без Hailo не имеет смысла."; exit 2
  fi
  BODY='{"model":"'"$MODEL"'","stream":false,"messages":[{"role":"user","content":"Напиши подробный рассказ о путешествии на воздушном шаре, примерно двести слов."}]}'
  ( echo "ts,seconds,http,bytes" > "$OUT/hailo_loop.csv"
    first=1
    while [ "$(date +%s)" -lt "$END" ]; do
      r=$(curl -s -o /tmp/gb_hailo_resp.json -w '%{time_total},%{http_code},%{size_download}' \
            -H 'Content-Type: application/json' -d "$BODY" --max-time 300 http://localhost:8000/api/chat)
      grep -q '"error"' /tmp/gb_hailo_resp.json 2>/dev/null && r="${r/,200,/,err,}"
      echo "$(date +%s),$r" >> "$OUT/hailo_loop.csv"
      if [ $first = 1 ]; then cp /tmp/gb_hailo_resp.json "$OUT/hailo_first_response.json"; first=0; fi
      case "$r" in *,200,*) ;; *) sleep 3 ;; esac
    done ) &
fi

echo "ts,elapsed_s,temp_c,arm_mhz,throttled,ext5v_v,fan_rpm,load1" > "$OUT/monitor.csv"
echo "Идёт стресс-тест «$TAG» на $DURATION_MIN мин. Ctrl+C — досрочно (итог всё равно сохранится)."
while [ "$(date +%s)" -lt "$END" ]; do
  t=$(vcgencmd measure_temp | grep -oE '[0-9]+\.[0-9]+')
  f=$(( $(vcgencmd measure_clock arm | cut -d= -f2) / 1000000 ))
  th=$(vcgencmd get_throttled | cut -d= -f2)
  v=$(vcgencmd pmic_read_adc EXT5V_V | grep -oE '=[0-9]+\.[0-9]+' | tr -d =)
  rpm=$(cat /sys/devices/platform/cooling_fan/hwmon/*/fan1_input 2>/dev/null | head -1)
  l=$(cut -d' ' -f1 /proc/loadavg)
  now=$(date +%s)
  echo "$now,$((now-START)),$t,$f,$th,$v,$rpm,$l" >> "$OUT/monitor.csv"
  printf '\r%5d с  %s °C  %4s МГц  throttled=%s  5V=%s В  вент.=%s   ' $((now-START)) "$t" "$f" "$th" "$v" "$rpm"
  sleep 5
done
echo
