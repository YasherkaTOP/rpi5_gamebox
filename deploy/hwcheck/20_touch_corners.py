#!/usr/bin/env python3
"""Game Box, блок 1. Проверка сенсора: касание четырёх углов и центра.

Запуск:  sudo python3 20_touch_corners.py
Нужно:   sudo apt install python3-evdev
Результат: ~/block1-report/touch.json

Скрипт сам находит сенсорное устройство, просит коснуться углов экрана и
по координатам определяет: совпадают ли оси с картинкой, нет ли поворота
(обмен осей) или зеркального отражения.
"""
import json
import select
import sys
import time

import evdev
from evdev import ecodes

sys.path.insert(0, __import__("os").path.dirname(__file__))
from b1common import report_dir  # noqa: E402

POINTS = [
    ("левый верхний угол", (0.0, 0.0)),
    ("правый верхний угол", (1.0, 0.0)),
    ("правый нижний угол", (1.0, 1.0)),
    ("левый нижний угол", (0.0, 1.0)),
    ("центр экрана", (0.5, 0.5)),
]


def find_touch():
    found = []
    for path in evdev.list_devices():
        d = evdev.InputDevice(path)
        caps = d.capabilities(absinfo=False)
        absc = caps.get(ecodes.EV_ABS, [])
        keys = caps.get(ecodes.EV_KEY, [])
        if (ecodes.ABS_MT_POSITION_X in absc or ecodes.ABS_X in absc) and ecodes.BTN_TOUCH in keys:
            found.append(d)
    return found


def axis_codes(d):
    absc = d.capabilities(absinfo=False).get(ecodes.EV_ABS, [])
    if ecodes.ABS_MT_POSITION_X in absc:
        return ecodes.ABS_MT_POSITION_X, ecodes.ABS_MT_POSITION_Y
    return ecodes.ABS_X, ecodes.ABS_Y


def wait_tap(d, cx, cy, timeout=40):
    x = y = None
    down = False
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([d.fd], [], [], 0.5)
        if not r:
            continue
        for ev in d.read():
            if ev.type == ecodes.EV_ABS:
                if ev.code == cx:
                    x = ev.value
                elif ev.code == cy:
                    y = ev.value
            elif ev.type == ecodes.EV_KEY and ev.code == ecodes.BTN_TOUCH:
                if ev.value == 1:
                    down = True
                elif ev.value == 0 and down and x is not None and y is not None:
                    return x, y
    return None


def main():
    devs = find_touch()
    if not devs:
        print("Сенсорное устройство не найдено. Проверь USB-кабель сенсора и `cat /proc/bus/input/devices`.")
        sys.exit(1)
    d = devs[0]
    cx, cy = axis_codes(d)
    ix, iy = d.absinfo(cx), d.absinfo(cy)
    print(f"Сенсор: {d.name}  ({d.path})  USB {d.info.vendor:04x}:{d.info.product:04x}")
    print(f"Диапазон X {ix.min}..{ix.max}, Y {iy.min}..{iy.max}")
    res = {"device": d.name, "path": d.path, "usb_id": f"{d.info.vendor:04x}:{d.info.product:04x}",
           "phys": d.phys, "x_range": [ix.min, ix.max], "y_range": [iy.min, iy.max],
           "axes": "MT" if cx == ecodes.ABS_MT_POSITION_X else "ABS", "points": []}
    for name, expect in POINTS:
        hint = "" if expect == (0.5, 0.5) else " (как можно ближе к краю)"
        print(f"\n→ Коснись пальцем: {name}{hint} и отпусти...")
        p = wait_tap(d, cx, cy)
        if p is None:
            print("  не дождался касания, пропускаю")
            res["points"].append({"name": name, "expect": expect, "raw": None})
            continue
        nx = (p[0] - ix.min) / max(1, ix.max - ix.min)
        ny = (p[1] - iy.min) / max(1, iy.max - iy.min)
        print(f"  raw=({p[0]}, {p[1]})  норм.=({nx:.2f}, {ny:.2f})")
        res["points"].append({"name": name, "expect": expect, "raw": p, "norm": [round(nx, 3), round(ny, 3)]})

    pts = [q for q in res["points"] if q.get("norm") and q["expect"] != (0.5, 0.5)]
    verdict = "недостаточно данных"
    if len(pts) == 4:
        def err(tf):
            return sum(abs(a - b) for q in pts for a, b in zip(tf(*q["norm"]), q["expect"]))
        cands = {
            "как есть": lambda x, y: (x, y),
            "зеркально по X": lambda x, y: (1 - x, y),
            "зеркально по Y": lambda x, y: (x, 1 - y),
            "поворот 180°": lambda x, y: (1 - x, 1 - y),
            "оси переставлены": lambda x, y: (y, x),
            "поворот 90° по часовой": lambda x, y: (1 - y, x),
            "поворот 90° против часовой": lambda x, y: (y, 1 - x),
            "оси переставлены + 180°": lambda x, y: (1 - y, 1 - x),
        }
        scores = {k: round(err(f), 3) for k, f in cands.items()}
        best = min(scores, key=scores.get)
        res["transform_scores"] = scores
        verdict = "совпадает с картинкой" if best == "как есть" else f"НЕ совпадает: {best}"
        res["best_transform"] = best
    res["verdict"] = verdict
    out = report_dir() / "touch.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\nИтог: {verdict}\nСохранено: {out}")


if __name__ == "__main__":
    main()
