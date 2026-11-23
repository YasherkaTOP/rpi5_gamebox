#!/usr/bin/env python3
"""Game Box, блок 1. Проверка микрофона: шум вентилятора, речь с 0,5 м, клиппинг.

Запуск:  sudo python3 30_mic_check.py [--rec-dev plughw:CARD=Device,DEV=0] [--distance 0.5]
Нужно:   sudo apt install python3-numpy stress-ng
Результат: ~/block1-report/mic/  (WAV-файлы + mic.json)

Порядок:
 1. Раскручивает вентилятор (принудительно или нагревом CPU) и пишет 10 с тишины.
 2. Ты читаешь вслух фразы с экрана терминала с указанного расстояния (15 с).
 3. Ты громко произносишь одну фразу (6 с) — проверка клиппинга.
 4. Считает пики, уровни, отношение речь/шум, число клиппированных отсчётов.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from b1common import detect_rec_dev, fan_rpm, read_wav, record, report_dir  # noqa: E402

PHRASES = [
    "Давай поиграем в викторину.",
    "Бэ пять.",
    "Да.  Нет.  Не знаю.",
    "Сорок два.",
    "Расскажи правила, пожалуйста.",
    "Я думаю, это была собака.",
]


def frames_db(x, fs, ms=30):
    n = int(fs * ms / 1000)
    k = len(x) // n
    f = x[: k * n].astype(np.float64).reshape(k, n) / 32768.0
    rms = np.sqrt(np.mean(f ** 2, axis=1)) + 1e-9
    return 20 * np.log10(rms)


def stats(path):
    x, fs = read_wav(path)
    a = np.abs(x.astype(np.int32))
    peak = int(a.max()) if len(a) else 0
    db = frames_db(x, fs)
    return {
        "file": Path(path).name,
        "seconds": round(len(x) / fs, 2),
        "peak_dbfs": round(20 * np.log10(max(peak, 1) / 32768.0), 1),
        "clipped_samples": int(np.sum(a >= 32700)),
        "frame_db_p10": round(float(np.percentile(db, 10)), 1),
        "frame_db_median": round(float(np.median(db)), 1),
        "frame_db_p95": round(float(np.percentile(db, 95)), 1),
    }


class Fan:
    """Принудительно крутит вентилятор; если не вышло — греет CPU stress-ng."""

    def __init__(self):
        self.dev = None
        self.old = None
        self.stress = None

    def start(self):
        for c in glob.glob("/sys/class/thermal/cooling_device*"):
            try:
                if Path(c, "type").read_text().strip() == "pwm-fan":
                    self.dev = Path(c)
                    self.old = Path(c, "cur_state").read_text().strip()
                    mx = Path(c, "max_state").read_text().strip()
                    Path(c, "cur_state").write_text(mx)
            except OSError:
                pass
        time.sleep(4)
        rpm = fan_rpm()
        if rpm is not None and rpm > 500:
            return rpm, "принудительно"
        print("Вентилятор не раскрутился принудительно — грею CPU (до 2 минут)...")
        self.stress = subprocess.Popen(["stress-ng", "--cpu", "4", "--quiet"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            time.sleep(2)
            rpm = fan_rpm()
            if rpm is not None and rpm > 500:
                return rpm, "нагревом CPU"
        return rpm, "не раскрутился"

    def stop(self):
        if self.stress:
            self.stress.terminate()
        if self.dev is not None and self.old is not None:
            try:
                Path(self.dev, "cur_state").write_text(self.old)
            except OSError:
                pass


def countdown(msg, n=3):
    print(msg)
    for i in range(n, 0, -1):
        print(f"  {i}...", flush=True)
        time.sleep(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec-dev")
    ap.add_argument("--distance", default="0.5", help="расстояние до микрофона, м (для подписи файлов)")
    args = ap.parse_args()
    if args.rec_dev:
        dev, cid, usbid = args.rec_dev, None, None
    else:
        dev, cid, usbid = detect_rec_dev()
    out = report_dir() / "mic"
    out.mkdir(exist_ok=True)
    tag = args.distance.replace(".", "")
    print(f"Запись с {dev} (карта {cid}, USB {usbid})")

    fan = Fan()
    try:
        rpm, how = fan.start()
        print(f"Вентилятор: {rpm} об/мин ({how})")
        countdown("\n[1/3] Тишина 10 с: не говори, просто слушаем вентилятор.")
        rpm_before = fan_rpm()
        record(dev, 10, out / "noise_fan.wav")
        rpm_noise = fan_rpm()

        print(f"\n[2/3] Встань (сядь) на {args.distance} м от микрофона, лицом к экрану.")
        print("Через 3 секунды начнётся запись 15 с. Читай обычным голосом, с паузами:")
        for p in PHRASES:
            print("    " + p)
        countdown("")
        print("  ● ЗАПИСЬ — говори")
        record(dev, 15, out / f"speech_{tag}m.wav")
        rpm_speech = fan_rpm()

        countdown(f"\n[3/3] Громко, почти крикни с {args.distance} м: «Ура! Победа!» (6 с)")
        print("  ● ЗАПИСЬ — громко")
        record(dev, 6, out / f"loud_{tag}m.wav")
    finally:
        fan.stop()

    n = stats(out / "noise_fan.wav")
    s = stats(out / f"speech_{tag}m.wav")
    lo = stats(out / f"loud_{tag}m.wav")
    snr = round(s["frame_db_p95"] - n["frame_db_median"], 1)
    clip = s["clipped_samples"] + lo["clipped_samples"]
    verdict = []
    verdict.append("клиппинга нет" if clip == 0 else f"КЛИППИНГ: {clip} отсчётов — убавь усиление")
    if snr >= 20:
        verdict.append(f"речь выше шума на {snr} дБ — хорошо")
    elif snr >= 12:
        verdict.append(f"речь выше шума на {snr} дБ — терпимо, лучше прибавить усиление или отодвинуть микрофон от вентилятора")
    else:
        verdict.append(f"речь выше шума всего на {snr} дБ — ПЛОХО")
    if s["peak_dbfs"] < -20:
        verdict.append(f"речь тихая (пик {s['peak_dbfs']} dBFS) — прибавь усиление")
    res = {
        "rec_dev": dev, "card_id": cid, "usb_id": usbid, "distance_m": float(args.distance),
        "fan": {"how": how, "rpm_start": rpm, "rpm_noise": rpm_noise, "rpm_speech": rpm_speech,
                "rpm_before_noise": rpm_before},
        "noise": n, "speech": s, "loud": lo,
        "snr_db_p95_vs_noise_median": snr,
        "verdict": verdict,
    }
    (out / "mic.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print("\n" + "\n".join(verdict))
    print(f"Сохранено: {out}")


if __name__ == "__main__":
    main()
