#!/usr/bin/env python3
"""Общие помощники скриптов блока 1 (Game Box).

Как модуль: импортируется скриптами 20/30/40.
Как CLI:
  python3 b1common.py play-dev                 -> ALSA-устройство HDMI подключённого экрана
  python3 b1common.py rec-dev                  -> ALSA-устройство USB-кодека (запись)
  python3 b1common.py gen-noise <path.wav> [секунд]
  python3 b1common.py summarize-stress <каталог stress_*>
"""
import glob
import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

REC_FS = 16000


def report_dir() -> Path:
    """~/block1-report пользователя, который вызвал sudo (или текущего)."""
    if os.environ.get("OUT"):
        p = Path(os.environ["OUT"])
    else:
        user = os.environ.get("SUDO_USER") or os.environ.get("USER") or "pi"
        try:
            import pwd
            home = pwd.getpwnam(user).pw_dir
        except Exception:
            home = os.path.expanduser("~")
        p = Path(home) / "block1-report"
    p.mkdir(parents=True, exist_ok=True)
    return p


def detect_play_dev() -> str:
    """hdmi:CARD=vc4hdmiN,DEV=0 для разъёма, к которому подключён экран."""
    for st in sorted(glob.glob("/sys/class/drm/card*-HDMI-A-*/status")):
        try:
            if Path(st).read_text().strip() == "connected":
                m = re.search(r"HDMI-A-(\d+)", st)
                return f"hdmi:CARD=vc4hdmi{int(m.group(1)) - 1},DEV=0"
        except OSError:
            pass
    return "hdmi:CARD=vc4hdmi0,DEV=0"


def detect_rec_dev():
    """(alsa_dev, card_id, usb_id) первой USB-звуковой карты с записью."""
    for usbid in sorted(glob.glob("/proc/asound/card*/usbid")):
        card_dir = os.path.dirname(usbid)
        if glob.glob(os.path.join(card_dir, "pcm*c")):
            cid = Path(card_dir, "id").read_text().strip()
            return f"plughw:CARD={cid},DEV=0", cid, Path(usbid).read_text().strip()
    raise SystemExit("USB-кодек с записью не найден. Проверь `arecord -l`.")


def write_wav(path, samples_float, fs, channels=1):
    import numpy as np
    x = np.clip(np.asarray(samples_float, dtype=np.float64), -1, 1)
    if channels == 2 and x.ndim == 1:
        x = np.stack([x, x], axis=1)
    pcm = (x * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(pcm.tobytes())


def read_wav(path):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        fs = w.getframerate()
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    if ch > 1:
        data = data.reshape(-1, ch)[:, 0]
    return data, fs


def record(dev, seconds, path):
    subprocess.run(["arecord", "-q", "-D", dev, "-f", "S16_LE", "-r", str(REC_FS),
                    "-c", "1", "-d", str(int(seconds)), str(path)], check=True)


def fan_rpm():
    for f in glob.glob("/sys/devices/platform/cooling_fan/hwmon/*/fan1_input"):
        try:
            return int(Path(f).read_text().strip())
        except (OSError, ValueError):
            pass
    return None


THROTTLE_BITS = {
    0: "под-напряжение сейчас", 1: "частота ограничена сейчас", 2: "троттлинг сейчас",
    3: "мягкий темп. лимит сейчас", 16: "под-напряжение БЫЛО", 17: "ограничение частоты БЫЛО",
    18: "троттлинг БЫЛ", 19: "мягкий темп. лимит БЫЛ",
}


def decode_throttled(value: int):
    return [name for bit, name in THROTTLE_BITS.items() if value & (1 << bit)]


def summarize_stress(d: Path):
    import csv
    rows = list(csv.DictReader(open(d / "monitor.csv")))
    if not rows:
        raise SystemExit("monitor.csv пуст")
    def fl(r, k):
        try:
            return float(r[k])
        except (ValueError, KeyError, TypeError):
            return None
    temps = [t for t in (fl(r, "temp_c") for r in rows) if t is not None]
    volts = [v for v in (fl(r, "ext5v_v") for r in rows) if v is not None]
    clocks = [c for c in (fl(r, "arm_mhz") for r in rows) if c is not None]
    rpm = [c for c in (fl(r, "fan_rpm") for r in rows) if c is not None]
    th_or = 0
    for r in rows:
        try:
            th_or |= int(r["throttled"], 16)
        except (ValueError, KeyError):
            pass
    th_first = int(rows[0]["throttled"], 16) if rows[0].get("throttled") else 0
    hailo = {}
    hl = d / "hailo_loop.csv"
    if hl.exists():
        hr = list(csv.DictReader(open(hl)))
        ok = [r for r in hr if r.get("http") == "200"]
        secs = sorted(float(r["seconds"]) for r in ok)
        hailo = {"requests": len(hr), "ok": len(ok), "failed": len(hr) - len(ok),
                 "median_s": secs[len(secs) // 2] if secs else None}
    dm = ""
    if (d / "dmesg_new.txt").exists():
        dm = (d / "dmesg_new.txt").read_text()
    bad = [l for l in dm.splitlines()
           if re.search(r"under-?voltage|over-?current|hailo.*(error|fail)|reset", l, re.I)]
    summary = {
        "duration_s": int(fl(rows[-1], "elapsed_s") or 0),
        "samples": len(rows),
        "temp_max_c": max(temps) if temps else None,
        "temp_last_c": temps[-1] if temps else None,
        "temp_ok_lt_80": (max(temps) < 80) if temps else None,
        "arm_mhz_min": min(clocks) if clocks else None,
        "ext5v_min_v": min(volts) if volts else None,
        "ext5v_ok_ge_4_8": (min(volts) >= 4.8) if volts else None,
        "fan_rpm_max": max(rpm) if rpm else None,
        "throttled_at_start": hex(th_first),
        "throttled_or": hex(th_or),
        "throttled_flags": decode_throttled(th_or),
        "power_ok": not (th_or & ((1 << 0) | (1 << 16))) and not any(
            re.search(r"under-?voltage|over-?current", l, re.I) for l in bad),
        "hailo": hailo,
        "dmesg_suspicious": bad[:50],
    }
    (d / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "play-dev":
        print(detect_play_dev())
    elif cmd == "rec-dev":
        print(detect_rec_dev()[0])
    elif cmd == "gen-noise":
        import numpy as np
        secs = float(sys.argv[3]) if len(sys.argv) > 3 else 10
        fs = 48000
        rng = np.random.default_rng(1)
        white = rng.standard_normal(int(fs * secs))
        # розовый шум через спектр 1/sqrt(f), уровень около -10 dBFS RMS
        X = np.fft.rfft(white)
        f = np.fft.rfftfreq(len(white), 1 / fs)
        f[0] = f[1]
        y = np.fft.irfft(X / np.sqrt(f), len(white))
        y = y / (np.sqrt(np.mean(y ** 2)) + 1e-12) * 0.3
        write_wav(sys.argv[2], y, fs, channels=2)
    elif cmd == "summarize-stress":
        summarize_stress(Path(sys.argv[2]))
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
