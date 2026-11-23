#!/usr/bin/env python3
"""Game Box, блок 1. Грубый замер HDMI-звука экрана.

Что меряет:
  1. Задержку «тёплого» воспроизведения: файл начинается с 2 с цифровой тишины
     (экран успевает проснуться), затем серия щелчков. Задержка = когда щелчки
     пришли в микрофон минус когда они должны были прозвучать.
  2. Обрезание начала после тишины 5, 30 и 60 с: серия из 20 щелчков через 50 мс
     идёт с самого начала файла. Сколько первых щелчков пропало — столько экран
     «съел» (шаг 50 мс).

Ограничение (выяснено в блоке 1): абсолютная задержка этим методом НЕ измеряется —
время старта arecord неизвестно, и привязка к часам даёт нереальные 5–6 мс. Поле
latency_ms_unreliable оставлено для истории. Обрезание считается надёжно, по положению
щелчков внутри записи относительно «тёплого» эталона (шаг 50 мс).
Точная задержка — блок 5 (калибровка по эталонному сигналу).
Условия: тихая комната, рабочая громкость экрана, микрофон на своём месте.

Запуск:  python3 40_hdmi_audio.py [--play-dev hdmi:CARD=vc4hdmi0,DEV=0] [--rec-dev plughw:CARD=X,DEV=0]
         [--gaps 5,30,60] [--repeats 2]
Результат: ~/block1-report/hdmi/  (WAV всех попыток + hdmi.json)
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from b1common import REC_FS, detect_play_dev, detect_rec_dev, report_dir, write_wav  # noqa: E402

PLAY_FS = 48000
F0 = 3000.0
N_BURSTS = 20
SPACING = 0.050
BURST = 0.005
WARM_LEAD = 2.0
PRE_ROLL = 0.8


def burst_train(lead):
    total = lead + N_BURSTS * SPACING + 0.4
    x = np.zeros(int(total * PLAY_FS))
    n = int(BURST * PLAY_FS)
    t = np.arange(n) / PLAY_FS
    b = 0.6 * np.sin(2 * np.pi * F0 * t) * np.hanning(n)
    for k in range(N_BURSTS):
        i = int((lead + k * SPACING) * PLAY_FS)
        x[i:i + n] += b
    return x


class Recorder:
    def __init__(self, dev):
        self.p = subprocess.Popen(
            ["arecord", "-q", "-D", dev, "-f", "S16_LE", "-r", str(REC_FS), "-c", "1", "-t", "raw",
             "--buffer-time=40000", "--period-time=10000"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.buf = []
        self.marks = []
        self.n = 0
        self.th = threading.Thread(target=self._run, daemon=True)
        self.th.start()

    def _run(self):
        while True:
            b = self.p.stdout.read(320)
            if not b:
                break
            now = time.monotonic()
            self.buf.append(b)
            self.n += len(b) // 2
            self.marks.append((now, self.n))

    def stop(self):
        self.p.terminate()
        self.th.join(timeout=3)
        raw = b"".join(self.buf)
        raw = raw[: len(raw) // 2 * 2]
        x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
        if len(self.marks) < 5:
            err = self.p.stderr.read().decode(errors="replace")
            raise SystemExit(f"Запись не идёт: {err}")
        t0 = min(t - n / REC_FS for t, n in self.marks)  # монотонное время отсчёта 0
        return x, t0


def envelope(x):
    n = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / REC_FS)
    X[(f < F0 - 700) | (f > F0 + 700)] = 0
    y = np.fft.irfft(X, n)
    w = max(1, int(0.002 * REC_FS))
    return np.convolve(np.abs(y), np.ones(w) / w, mode="same")


def events(e, ratio):
    noise = float(np.median(e[: int(0.5 * REC_FS)])) + 1e-9
    peak = float(e.max())
    thr = max(noise * 6, peak * ratio)
    idx = np.flatnonzero(e > thr)
    ev = []
    if len(idx):
        start = prev = idx[0]
        for j in idx[1:]:
            if j - prev > int(0.015 * REC_FS):
                ev.append(start)
                start = j
            prev = j
        ev.append(start)
    return ev, 20 * np.log10(peak / noise)


def trial(play_dev, rec_dev, wav_path, save_path):
    rec = Recorder(rec_dev)
    time.sleep(PRE_ROLL)
    t_play = time.monotonic()
    r = subprocess.run(["aplay", "-q", "-D", play_dev, str(wav_path)], capture_output=True, text=True)
    t_end = time.monotonic()
    time.sleep(0.8)
    x, t0 = rec.stop()
    if r.returncode != 0:
        raise SystemExit(f"aplay ошибка: {r.stderr.strip()}")
    write_wav(save_path, x, REC_FS)
    return x, t0, t_play, t_end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--play-dev")
    ap.add_argument("--rec-dev")
    ap.add_argument("--gaps", default="5,30,60")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--warm", type=int, default=5)
    a = ap.parse_args()
    play_dev = a.play_dev or detect_play_dev()
    rec_dev = a.rec_dev or detect_rec_dev()[0]
    out = report_dir() / "hdmi"
    out.mkdir(exist_ok=True)
    warm_wav, cold_wav = out / "_play_warm.wav", out / "_play_cold.wav"
    write_wav(warm_wav, burst_train(WARM_LEAD), PLAY_FS, channels=2)
    write_wav(cold_wav, burst_train(0.0), PLAY_FS, channels=2)
    print(f"Вывод: {play_dev}   Запись: {rec_dev}")
    print("Тихо в комнате ~4 минуты. Громкость экрана — рабочая.\n")

    # 1. Тёплые попытки: подобрать порог детектора и измерить задержку
    warm = []
    ratio_ok = None
    for i in range(a.warm):
        x, t0, t_play, t_end = trial(play_dev, rec_dev, warm_wav, out / f"warm_{i}.wav")
        e = envelope(x)
        for ratio in (0.2, 0.3, 0.4, 0.5, 0.15, 0.1):
            ev, snr = events(e, ratio)
            if len(ev) == N_BURSTS:
                break
        lat = None
        pos0 = ev[0] / REC_FS if len(ev) == N_BURSTS else None
        if len(ev) == N_BURSTS:
            ratio_ok = ratio_ok or ratio
            abs_t = [t0 + j / REC_FS for j in ev]
            exp_t = [t_play + WARM_LEAD + k * SPACING for k in range(N_BURSTS)]
            lat = float(np.median(np.array(abs_t) - np.array(exp_t)))
        warm.append({"i": i, "detected": len(ev), "snr_db": round(snr, 1),
                     "latency_ms_unreliable": None if lat is None else round(lat * 1000, 1), "ratio": ratio,
                     "first_burst_pos_s": None if pos0 is None else round(pos0, 4)})
        print(f"тёплая {i}: щелчков {len(ev)}/{N_BURSTS}, сигнал/шум {snr:.0f} дБ, задержка "
              f"{'—' if lat is None else f'{lat*1000:.0f} мс'}")
        time.sleep(0.3)
    lats = [w["latency_ms_unreliable"] for w in warm if w["latency_ms_unreliable"] is not None]
    poss = [w["first_burst_pos_s"] for w in warm if w["first_burst_pos_s"] is not None]
    # где в записи без 2-с вступления оказался бы щелчок № 0
    cold_expect0 = (float(np.median(poss)) - WARM_LEAD) if poss else None
    if not lats:
        print("\nДетектор не нашёл все щелчки в тёплых попытках. Причины: тихо (прибавь громкость экрана),"
              " шумно в комнате или сильное эхо. WAV сохранены — пришли их, разберу вручную.")
        lat_warm = None
    else:
        lat_warm = float(np.median(lats)) / 1000
        print(f"\nЭталон получен ({len(poss)} тёплых попыток). Абсолютная задержка этим методом не измеряется.\n")
    ratio_ok = ratio_ok or 0.3

    # 2. Холодные попытки после паузы
    cold = []
    gaps = [int(g) for g in a.gaps.split(",") if g.strip()]
    last_end = time.monotonic()
    for rep in range(a.repeats):
        for g in gaps:
            wait = max(0.0, g - (time.monotonic() - last_end) - PRE_ROLL)
            print(f"пауза {g} с ...", flush=True)
            time.sleep(wait)
            x, t0, t_play, t_end = trial(play_dev, rec_dev, cold_wav, out / f"cold_{g}s_{rep}.wav")
            last_end = t_end
            ev, snr = events(envelope(x), ratio_ok)
            item = {"gap_s": g, "rep": rep, "detected_raw": len(ev), "snr_db": round(snr, 1)}
            if cold_expect0 is not None:
                pos = [j / REC_FS for j in ev if j / REC_FS >= cold_expect0 - 0.025]
                item["detected"] = len(pos)
                if pos:
                    first_k = max(0, round((pos[0] - cold_expect0) / SPACING))
                    item["first_burst_index"] = int(first_k)
                    item["truncated_ms"] = int(first_k * SPACING * 1000)
                    item["first_offset_vs_warm_ms"] = round((pos[0] - cold_expect0) * 1000, 1)
            else:
                item["truncated_ms_by_count"] = int(max(0, N_BURSTS - len(ev)) * SPACING * 1000)
            cold.append(item)
            print(f"  после {g} с тишины: щелчков {item.get('detected', len(ev))}/{N_BURSTS}, "
                  f"съедено ≈ {item.get('truncated_ms', item.get('truncated_ms_by_count', '?'))} мс")

    res = {
        "play_dev": play_dev, "rec_dev": rec_dev,
        "method": "серия 20 щелчков 3 кГц по 5 мс через 50 мс; тёплая — после 2 с цифровой тишины в том же потоке",
        "accuracy_note": "обрезание: шаг 50 мс по положению в записи; абсолютная задержка не измеряется (см. docstring)",
        "warm_first_burst_pos_s": poss,
        "latency_ms_unreliable": lats,
        "warm": warm, "cold": cold,
    }
    (out / "hdmi.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
    os.remove(warm_wav)
    os.remove(cold_wav)
    print(f"\nСохранено: {out / 'hdmi.json'}")


if __name__ == "__main__":
    main()
