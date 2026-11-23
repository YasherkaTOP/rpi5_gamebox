"""Готовит артефакты dev-деплоя из текущего рабочего дерева, без требования коммита."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".build",
    "var",
    "wheelhouse",
    "node_modules",
    "dist",
    "__pycache__",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_files() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    )
    files: list[Path] = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        path = Path(raw.decode())
        if EXCLUDED_PARTS.intersection(path.parts) or not (ROOT / path).is_file():
            continue
        files.append(path)
    return sorted(files)


def make_tar(entries: list[tuple[Path, str]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path, name in entries:
            info = tarfile.TarInfo(name)
            data = path.read_bytes()
            info.size = len(data)
            info.mode = 0o755 if path.suffix == ".sh" else 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / ".build")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    files = source_files()
    source_tar = make_tar([(ROOT / path, path.as_posix()) for path in files])
    ui_dist = ROOT / "ui" / "dist"
    ui_tar = make_tar(
        [
            (path, f"ui/dist/{path.relative_to(ui_dist).as_posix()}")
            for path in sorted(ui_dist.rglob("*"))
            if path.is_file()
        ]
    )
    wheelhouse = ROOT / "wheelhouse"
    wheel_tar = make_tar(
        [
            (path, f"wheelhouse/{path.name}")
            for path in sorted(wheelhouse.iterdir())
            if path.is_file()
        ]
    )
    artifacts = {"source.tar.gz": source_tar, "ui.tar.gz": ui_tar, "wheelhouse.tar.gz": wheel_tar}
    hashes = {name: sha256(data) for name, data in artifacts.items()}
    release_id = (
        f"{version}-{sha256(b''.join(hashes[name].encode() for name in sorted(hashes)))[:12]}"
    )
    for name, data in artifacts.items():
        (args.output / name).write_bytes(data)
    requirements = ROOT / ".build" / "device-requirements.txt"
    (args.output / "device-requirements.txt").write_bytes(requirements.read_bytes())
    manifest = {"release_id": release_id, "version": version, "artifacts": hashes}
    (args.output / "release.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
