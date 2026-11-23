"""Устанавливает dev-релиз в /opt/gamebox/releases/<id> и атомарно переключает current.

Запуск на устройстве через sudo. Не включает сервисы-заглушки блока 2.
Полная самопроверка, миграции и автоматический откат по health — блок 19.

venv создаётся с --without-pip, а pip ставится из колеса в wheelhouse: так не нужен
системный пакет python3-venv с ensurepip, и установка остаётся полностью офлайн.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifacts(staging: Path) -> dict[str, object]:
    manifest = json.loads((staging / "release.json").read_text(encoding="utf-8"))
    release_id = str(manifest["release_id"])
    if not release_id or "/" in release_id or release_id.startswith("."):
        raise ValueError("Некорректный release_id")
    if ".." in release_id:
        raise ValueError("Некорректный release_id")
    for name, expected in manifest["artifacts"].items():
        if sha256(staging / name) != expected:
            raise ValueError(f"Хэш не совпадает: {name}")
    return manifest


def safe_extract(archive: Path, target: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(target, filter="data")


def atomic_switch(prefix: Path, release_id: str) -> str | None:
    current = prefix / "current"
    previous = os.readlink(current) if current.is_symlink() else None
    temporary = prefix / "current.new"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(f"releases/{release_id}")
    os.replace(temporary, current)
    return previous


def read_config_paths(config: Path) -> tuple[Path, Path]:
    """Каталог данных и runtime-каталог берутся из конфига, а не из hardcoded /run."""
    with config.open("rb") as stream:
        data = tomllib.load(stream)
    paths = data.get("paths", {})
    root = Path(paths.get("root", "/var/lib/gamebox"))
    runtime = Path(paths.get("runtime", "/run/gamebox"))
    return root, runtime


def ensure_service_dirs(root: Path, runtime: Path, uid: int, gid: int) -> None:
    """Готовит каталоги, которые сервис создаёт сам, но /run принадлежит root."""
    for directory in (root, runtime):
        directory.mkdir(parents=True, exist_ok=True)
        os.chown(directory, uid, gid)
        directory.chmod(0o750)


def resolve_user(name: str) -> tuple[int, int]:
    """pwd импортируется здесь: модуль Unix-only, а скрипт читается и на Windows."""
    import pwd

    entry = pwd.getpwnam(name)
    return entry.pw_uid, entry.pw_gid


def rewrite_shebangs(venv: Path, old_root: Path, new_root: Path) -> int:
    """Чинит абсолютные shebang после переноса venv.

    Console-scripts (gamebox, pip) содержат абсолютный путь к интерпретатору.
    После rename каталога релиза путь указывает на удалённый .pending-*, и ядро
    отвечает ENOENT на сам скрипт. Переписываем префикс в текстовых файлах bin/.
    """
    bin_dir = venv / "bin"
    if not bin_dir.is_dir():
        return 0
    # Абсолютные пути обязательны: относительный shebang сломался бы при запуске
    # сервиса из другого cwd.
    old_bytes = os.fsencode(str(old_root.resolve()))
    new_bytes = os.fsencode(str(new_root.resolve()))
    fixed = 0
    for path in sorted(bin_dir.iterdir()):
        if path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        if not data.startswith(b"#!") or old_bytes not in data:
            continue
        head, separator, rest = data.partition(b"\n")
        path.write_bytes(head.replace(old_bytes, new_bytes) + separator + rest)
        fixed += 1
    return fixed


def find_pip_wheel(wheelhouse: Path) -> Path:
    wheels = sorted(wheelhouse.glob("pip-*.whl"))
    if not wheels:
        raise SystemExit(
            f"В {wheelhouse} нет колеса pip. Пересоберите: make wheelhouse "
            "(pip входит в extras [device] и нужен для офлайн-установки)."
        )
    return wheels[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("staging", type=Path)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--prefix", type=Path, default=Path("/opt/gamebox"))
    parser.add_argument("--config-dir", type=Path, default=Path("/etc/gamebox"))
    parser.add_argument("--user", default="gamebox")
    parser.add_argument("--python", default="/usr/bin/python3")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--skip-services", action="store_true")
    args = parser.parse_args()
    manifest = verify_artifacts(args.staging)
    release_id = str(manifest["release_id"])
    target = args.prefix / "releases" / release_id
    print(json.dumps({"release_id": release_id, "target": str(target), "dry_run": args.dry_run}))
    if args.dry_run:
        return
    if not args.activate:
        raise SystemExit("Для установки нужен --activate")
    if target.exists():
        raise SystemExit(f"Релиз уже существует: {target}")
    (args.prefix / "releases").mkdir(parents=True, exist_ok=True)
    pending = Path(tempfile.mkdtemp(prefix=f".pending-{release_id}-", dir=args.prefix / "releases"))
    # mkdtemp даёт 0700; релиз должен читаться пользователем сервисов.
    pending.chmod(0o755)
    installed = pending
    try:
        safe_extract(args.staging / "source.tar.gz", pending / "source")
        safe_extract(args.staging / "ui.tar.gz", pending)
        safe_extract(args.staging / "wheelhouse.tar.gz", pending)
        requirements = pending / "device-requirements.txt"
        shutil.copy2(args.staging / "device-requirements.txt", requirements)

        wheelhouse = pending / "wheelhouse"
        pip_wheel = find_pip_wheel(wheelhouse)
        subprocess.run(
            [args.python, "-m", "venv", "--without-pip", str(pending / ".venv")], check=True
        )
        python = pending / ".venv" / "bin" / "python"
        # Запуск pip прямо из колеса: ensurepip в системе не нужен.
        subprocess.run(
            [
                str(python),
                f"{pip_wheel}/pip",
                "install",
                "--no-index",
                "--find-links",
                str(wheelhouse),
                "--no-deps",
                "--require-hashes",
                "-r",
                str(requirements),
            ],
            check=True,
        )
        wheels = sorted(wheelhouse.glob("gamebox-*.whl"))
        if not wheels:
            raise SystemExit(f"В {wheelhouse} нет колеса gamebox")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(wheels[0]),
            ],
            check=True,
        )

        entry_uid, entry_gid = resolve_user(args.user)
        args.config_dir.mkdir(parents=True, exist_ok=True)
        os.chown(args.config_dir, 0, entry_gid)
        args.config_dir.chmod(0o750)
        config = args.config_dir / "config.toml"
        if not config.exists():
            shutil.copyfile(pending / "source" / "deploy" / "config.example.toml", config)
            os.chown(config, 0, entry_gid)
            config.chmod(0o640)
        root, runtime = read_config_paths(config)
        if args.runtime_dir is not None:
            runtime = args.runtime_dir
        ensure_service_dirs(root, runtime, entry_uid, entry_gid)

        # Переносим ДО smoke: venv писался в .pending-*, а console-scripts хранят
        # абсолютный shebang. Без починки gamebox не запускается из релиза.
        pending.rename(target)
        installed = target
        target.chmod(0o755)
        fixed = rewrite_shebangs(target / ".venv", pending, target)
        print(json.dumps({"relocated": str(target), "shebangs_fixed": fixed}))

        subprocess.run(
            [
                "runuser",
                "-u",
                args.user,
                "--",
                str(target / ".venv" / "bin" / "gamebox"),
                "smoke",
                "--config",
                str(config),
            ],
            check=True,
        )
        previous = atomic_switch(args.prefix, release_id)
        restarted: list[str] = []
        services = () if args.skip_services else ("gamebox-llm", "gamebox-core", "gamebox-kiosk")
        for service in services:
            enabled = subprocess.run(["systemctl", "is-enabled", "--quiet", service], check=False)
            if enabled.returncode == 0:
                subprocess.run(["systemctl", "restart", service], check=True)
                restarted.append(service)
        print(
            json.dumps(
                {
                    "status": "activated",
                    "release_id": release_id,
                    "previous": previous,
                    "restarted": restarted,
                }
            )
        )
    except Exception:
        # После rename каталог релиза уже называется target; чистим актуальный путь,
        # иначе повторный деплой упрётся в "Релиз уже существует".
        shutil.rmtree(installed, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
