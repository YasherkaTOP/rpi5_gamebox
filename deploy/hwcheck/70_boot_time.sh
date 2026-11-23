#!/usr/bin/env bash
# Game Box, блок 1. Время загрузки ОС. Запускать через ~1 минуту после каждой загрузки.
# Запуск:  ./70_boot_time.sh "холодный старт, питание было выключено 10 мин"
# Результат: дописывает ~/block1-report/boot_times.txt
OUT="${OUT:-$HOME/block1-report}"
mkdir -p "$OUT"
{
  echo "===== $(date -Is)  ${1:-без пометки}"
  systemd-analyze
  echo "--- blame (топ-15)"
  systemd-analyze blame | head -15
  echo "--- RTC при загрузке"
  journalctl -k -b --no-pager | grep -iE "rtc" | head -5
  echo "--- первая и последняя строки журнала загрузки"
  journalctl -b -o short-iso --no-pager | head -1
  echo
} >> "$OUT/boot_times.txt"
tail -n 30 "$OUT/boot_times.txt"
