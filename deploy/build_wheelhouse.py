"""Собирает offline wheelhouse для Raspberry Pi OS aarch64 строго по uv.lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--project-wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python-version", default="3.13")
    args = parser.parse_args()
    abi = "cp" + args.python_version.replace(".", "")
    args.output.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--only-binary=:all:",
        "--implementation",
        "cp",
        "--python-version",
        args.python_version,
        "--abi",
        abi,
        "--abi",
        "abi3",
        "--abi",
        "none",
        "--platform",
        "manylinux2014_aarch64",
        "--platform",
        "manylinux_2_17_aarch64",
        "--platform",
        "manylinux_2_24_aarch64",
        "--platform",
        "manylinux_2_28_aarch64",
        "--require-hashes",
        "-r",
        str(args.requirements),
        "-d",
        str(args.output),
    ]
    subprocess.run(command, check=True)
    wheels = sorted(args.project_wheel.glob("gamebox-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Ожидалось ровно одно колесо gamebox в --project-wheel")
    shutil.copy2(wheels[0], args.output / wheels[0].name)
    manifest = {
        "target": {"os": "linux", "arch": "aarch64", "python": args.python_version},
        "requirements_sha256": sha256(args.requirements),
        "project_wheel": wheels[0].name,
        "wheels": {path.name: sha256(path) for path in sorted(args.output.glob("*.whl"))},
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wheelhouse: {len(manifest['wheels'])} wheels, target aarch64/Python {args.python_version}"
    )


if __name__ == "__main__":
    main()
