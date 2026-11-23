from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from deploy import device_deploy


def make_build(tmp_path: Path) -> tuple[Path, Path]:
    build = tmp_path / ".build"
    build.mkdir()
    for name in device_deploy.ARTIFACTS:
        (build / name).write_bytes(b"x")
    root = tmp_path / "repo"
    (root / "deploy").mkdir(parents=True)
    (root / "deploy" / "install_release.py").write_text("# installer", encoding="utf-8")
    return build, root


def test_install_command_uses_tty_and_cleans_up() -> None:
    cmd = device_deploy.install_command("/tmp/gamebox-deploy.abc123")
    assert cmd.startswith("sudo python3 /tmp/gamebox-deploy.abc123/install_release.py ")
    assert "--activate" in cmd
    assert "status=$?" in cmd
    assert "rm -rf -- /tmp/gamebox-deploy.abc123" in cmd
    assert cmd.endswith("exit $status")


def test_deploy_sends_one_scp_and_uses_ssh_tt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    build, root = make_build(tmp_path)
    calls: list[tuple[list[str], bool]] = []
    cleanup: list[list[str]] = []

    def fake_run(cmd: list[str], *, capture: bool = False) -> str:
        calls.append((cmd, capture))
        if len(cmd) == 3 and cmd[0] == "ssh" and cmd[2].startswith("mktemp"):
            return "/tmp/gamebox-deploy.abc123"
        return ""

    def fake_cleanup(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cleanup.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(device_deploy, "run", fake_run)
    monkeypatch.setattr(device_deploy.subprocess, "run", fake_cleanup)
    device_deploy.deploy("admin@gamebox.local", build, root)

    mktemp = "mktemp -d /tmp/gamebox-deploy.XXXXXX"
    assert calls[0] == (["ssh", "admin@gamebox.local", mktemp], True)
    assert len(calls) == 3
    scp = calls[1][0]
    assert scp[0] == "scp"
    assert str(root / "deploy" / "install_release.py") in scp
    assert scp[-1] == "admin@gamebox.local:/tmp/gamebox-deploy.abc123/"
    assert scp[:2] == ["scp", str(build / "source.tar.gz")]
    assert calls[2][0][:3] == ["ssh", "-tt", "admin@gamebox.local"]
    # Установка и уборка идут одной сессией, отдельный cleanup-ssh не нужен.
    assert cleanup == []


def test_deploy_forces_tty_for_sudo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    build, root = make_build(tmp_path)
    seen: list[list[str]] = []

    def fake_run(cmd: list[str], *, capture: bool = False) -> str:
        seen.append(cmd)
        if len(cmd) == 3 and cmd[2].startswith("mktemp"):
            return "/tmp/gamebox-deploy.tty001"
        return ""

    monkeypatch.setattr(device_deploy, "run", fake_run)
    device_deploy.deploy("admin@gamebox.local", build, root)
    assert seen[-1][:3] == ["ssh", "-tt", "admin@gamebox.local"]


def test_deploy_cleans_up_if_upload_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    build, root = make_build(tmp_path)
    cleanup: list[list[str]] = []

    def fake_run(cmd: list[str], *, capture: bool = False) -> str:
        if len(cmd) == 3 and cmd[0] == "ssh" and cmd[2].startswith("mktemp"):
            return "/tmp/gamebox-deploy.fail01"
        raise subprocess.CalledProcessError(1, cmd)

    def fake_cleanup(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cleanup.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(device_deploy, "run", fake_run)
    monkeypatch.setattr(device_deploy.subprocess, "run", fake_cleanup)
    with pytest.raises(subprocess.CalledProcessError):
        device_deploy.deploy("admin@gamebox.local", build, root)
    assert cleanup == [["ssh", "admin@gamebox.local", "rm -rf -- /tmp/gamebox-deploy.fail01"]]


def test_deploy_requires_artifacts(tmp_path: Path) -> None:
    build = tmp_path / ".build"
    build.mkdir()
    (build / "release.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="device-package"):
        device_deploy.deploy("admin@gamebox.local", build, tmp_path)


def test_require_tools_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device_deploy.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="ssh, scp"):
        device_deploy.require_tools()
