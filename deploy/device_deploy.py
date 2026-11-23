"""Кроссплатформенная SSH-доставка уже собранных .build/* на устройство.

Требует только `ssh` и `scp` в PATH (OpenSSH Client в Windows, openssh-client в Linux,
или Git Bash/WSL). Не использует bash и POSIX-присваивание переменных в Makefile.

Установка идёт через `ssh -tt`, чтобы sudo мог запросить пароль в терминале.
Уборка временного каталога выполняется той же удалённой командой, поэтому
пароль SSH спрашивается три раза, а не пять.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = (
    "source.tar.gz",
    "ui.tar.gz",
    "wheelhouse.tar.gz",
    "release.json",
    "device-requirements.txt",
)


def run(cmd: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(cmd, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def require_tools() -> None:
    missing = [tool for tool in ("ssh", "scp") if shutil.which(tool) is None]
    if missing:
        raise SystemExit(
            "Не найдены: " + ", ".join(missing) + ". Установите OpenSSH Client (Windows: "
            "Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0) "
            "или запускайте из WSL/Git Bash с ssh/scp в PATH."
        )


def install_command(remote_dir: str) -> str:
    """Установка и уборка в одной сессии; код возврата берётся от установщика."""
    quoted_dir = shlex.quote(remote_dir)
    installer = shlex.quote(f"{remote_dir}/install_release.py")
    return (
        f"sudo python3 {installer} {quoted_dir} --activate; "
        f"status=$?; rm -rf -- {quoted_dir}; exit $status"
    )


def deploy(device: str, build: Path, root: Path) -> None:
    if not (build / "release.json").exists():
        raise SystemExit("Сначала make device-package")
    for name in ARTIFACTS:
        if not (build / name).exists():
            raise SystemExit(f"Нет артефакта {build / name}; сначала make device-package")

    remote_dir = run(["ssh", device, "mktemp -d /tmp/gamebox-deploy.XXXXXX"], capture=True)
    if not remote_dir.startswith("/tmp/gamebox-deploy."):
        raise SystemExit(f"Неожиданный ответ mktemp: {remote_dir!r}")
    quoted_dir = shlex.quote(remote_dir)
    installation_started = False
    try:
        run(
            [
                "scp",
                *[str(build / name) for name in ARTIFACTS],
                str(root / "deploy" / "install_release.py"),
                f"{device}:{remote_dir}/",
            ]
        )
        installation_started = True
        run(["ssh", "-tt", device, install_command(remote_dir)])
    finally:
        if not installation_started:
            subprocess.run(
                ["ssh", device, f"rm -rf -- {quoted_dir}"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device",
        default=os.environ.get("DEVICE", "admin@gamebox.local"),
        help="SSH-адрес устройства, например admin@gamebox.local",
    )
    parser.add_argument("--build", type=Path, default=ROOT / ".build")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    require_tools()
    try:
        deploy(args.device, args.build.resolve(), args.root.resolve())
    except subprocess.CalledProcessError as exc:
        print(f"Команда завершилась с кодом {exc.returncode}: {exc.cmd}", file=sys.stderr)
        raise SystemExit(exc.returncode) from exc


if __name__ == "__main__":
    main()
