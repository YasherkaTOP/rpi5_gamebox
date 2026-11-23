#!/usr/bin/env bash
# Game Box, блок 1. Упаковать отчёт для отправки.
# Запуск:  ./90_pack.sh   (после sudo ./00_collect.sh и заполнения manual_notes.md)
set -e
R="$HOME/block1-report"
[ -d "$R" ] || { echo "Нет $R"; exit 1; }
[ -f "$R/manual_notes.md" ] || echo "ВНИМАНИЕ: нет $R/manual_notes.md — скопируй шаблон и заполни"
[ -d "$R/collect" ] || echo "ВНИМАНИЕ: нет collect/ — сначала sudo ./00_collect.sh"
F="$HOME/block1-report-$(date +%Y%m%d-%H%M).tar.gz"
sudo chown -R "$USER":"$USER" "$R" 2>/dev/null || true
tar czf "$F" -C "$HOME" block1-report
ls -lh "$F"
echo "Скопируй на ПК:  scp $(whoami)@gamebox.local:$F ."
