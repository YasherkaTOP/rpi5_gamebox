#!/usr/bin/env bash
# Game Box, блок 1. Эталонная генерация на Hailo-10H через hailo-ollama.
# Запуск (БЕЗ sudo, от своего пользователя):  MODEL=qwen2-instruct:1.5b ./60_hailo_smoke.sh
# Результат: ~/block1-report/hailo/
set -u
MODEL="${MODEL:-qwen2-instruct:1.5b}"
API=http://localhost:8000
OUT="${OUT:-$HOME/block1-report}/hailo"
mkdir -p "$OUT"

if ! curl -s --max-time 3 "$API/hailo/v1/list" >/dev/null; then
  echo "Запускаю hailo-ollama в фоне (журнал: $OUT/hailo-ollama.log)"
  nohup hailo-ollama > "$OUT/hailo-ollama.log" 2>&1 &
  for _ in $(seq 30); do curl -s --max-time 2 "$API/hailo/v1/list" >/dev/null && break; sleep 2; done
fi

curl -s "$API/hailo/v1/list" | tee "$OUT/models_list.json"; echo
echo "Скачиваю/проверяю модель $MODEL ..."
curl -s --no-buffer "$API/api/pull" -H 'Content-Type: application/json' \
     -d "{\"model\": \"$MODEL\", \"stream\": true}" | tail -3 | tee "$OUT/pull_tail.txt"; echo

ask() { # ask <имя> <текст>
  local name="$1" text="$2"
  local body
  body=$(printf '{"model":"%s","stream":true,"messages":[{"role":"user","content":"%s"}]}' "$MODEL" "$text")
  local t0; t0=$(date +%s.%N)
  echo "t0 $t0" > "$OUT/$name.stream.log"
  curl -s --no-buffer "$API/api/chat" -H 'Content-Type: application/json' -d "$body" \
    | while IFS= read -r line; do echo "$(date +%s.%N) $line"; done >> "$OUT/$name.stream.log"
  python3 - "$OUT/$name.stream.log" <<'PY'
import json, sys
lines = open(sys.argv[1]).read().splitlines()
t0 = float(lines[0].split()[1])
text, first, last, final = "", None, None, {}
for l in lines[1:]:
    ts, _, js = l.partition(" ")
    try:
        d = json.loads(js)
    except Exception:
        continue
    c = (d.get("message") or {}).get("content", "")
    if c and first is None:
        first = float(ts)
    text += c
    last = float(ts)
    if d.get("done"):
        final = d
print("Ответ:", text.strip())
if first:
    print(f"До первого фрагмента: {first - t0:.2f} с (вместе с HTTP и загрузкой модели при первом вызове); всего: {last - t0:.2f} с")
for k in ("eval_count", "eval_duration", "prompt_eval_count", "prompt_eval_duration", "load_duration", "total_duration"):
    if k in final:
        print(f"{k}: {final[k]}")
PY
}

ask ru1 "Ответь одним коротким предложением по-русски: какого цвета небо днём?" | tee "$OUT/ru1.txt"
ask ru2 "Придумай короткое приветствие ведущего викторины, не длиннее двенадцати слов." | tee "$OUT/ru2.txt"
ask ru3 "Сколько будет два плюс три? Ответь одним словом." | tee "$OUT/ru3.txt"
echo "Сохранено в $OUT"
