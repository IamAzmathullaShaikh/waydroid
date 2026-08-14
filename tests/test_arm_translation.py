# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the ARM64 translation layer (libndk_translation)."""

import types

import pytest

import tools.config
from tools.helpers import arm_translation
import tools.actions.arm_translation as action


def _install_files(base, required=True):
    (base / "system/lib64/ndk_translation").mkdir(parents=True)
    for rel in arm_translation.REQUIRED:
        (base / rel).touch()
    if not required:
        (base / "system/lib64/libndk_translation.so").unlink()


def test_not_installed_when_dir_missing(monkeypatch):
    monkeypatch.setattr(arm_translation, "ARM_TRANSLATION_DIR",
                        "/nonexistent/arm-translation")
    assert not arm_translation.is_installed()


def test_installed_when_required_files_present(monkeypatch, tmp_path):
    base = tmp_path / "arm-translation"
    _install_files(base)
    monkeypatch.setattr(arm_translation, "ARM_TRANSLATION_DIR", str(base))
    assert arm_translation.is_installed()


def test_mount_entries_only_existing(monkeypatch, tmp_path):
    base = tmp_path / "arm-translation"
    (base / "system/lib64").mkdir(parents=True)
    (base / "system/lib64/libndk_translation.so").touch()
    monkeypatch.setattr(arm_translation, "ARM_TRANSLATION_DIR", str(base))

    entries = arm_translation.mount_entries()

    assert entries[0] == (str(base / "system/lib64/libndk_translation.so"),
                          "system/lib64/libndk_translation.so", "file")
    # Missing dir entries are skipped
    assert all(e[1] != "system/lib64/ndk_translation" for e in entries)


def _patch_install_env(monkeypatch, tmp_path, cfg=None):
    monkeypatch.setattr(arm_translation, "ARM_TRANSLATION_DIR",
                        str(tmp_path / "arm-translation"))
    monkeypatch.setattr(action.helpers.arch, "host", lambda: "x86_64")
    monkeypatch.setattr("tools.helpers.run.user", lambda *a, **k: None)
    monkeypatch.setattr(action.helpers.lxc, "make_base_props", lambda args: None)
    if cfg is None:
        cfg = {"waydroid": {"arch": "x86_64", "images_path": "/x",
                            "vendor_type": "MAINLINE", "system_ota": "s",
                            "vendor_ota": "v"}}
    monkeypatch.setattr(tools.config, "load", lambda args: cfg)
    return types.SimpleNamespace(source=None, archive=None, url=None)


def test_install_from_source_dir(monkeypatch, tmp_path):
    source = tmp_path / "source"
    _install_files(source)
    args = _patch_install_env(monkeypatch, tmp_path)
    args.source = str(source)

    action.install(args)

    assert arm_translation.is_installed()
    assert (tmp_path / "arm-translation/system/lib64/ndk_translation"
            / "libarm64.so").exists()


def test_install_rejects_missing_layout(monkeypatch, tmp_path):
    source = tmp_path / "source"
    _install_files(source, required=False)
    args = _patch_install_env(monkeypatch, tmp_path)
    args.source = str(source)

    with pytest.raises(RuntimeError):
        action.install(args)

    # Nothing must remain installed
    assert not arm_translation.is_installed()


def test_install_refuses_on_arm64_host(monkeypatch, tmp_path):
    source = tmp_path / "source"
    _install_files(source)
    args = _patch_install_env(monkeypatch, tmp_path)
    args.source = str(source)
    monkeypatch.setattr(action.helpers.arch, "host", lambda: "arm64")

    with pytest.raises(RuntimeError):
        action.install(args)


def test_install_requires_a_source(monkeypatch, tmp_path):
    args = _patch_install_env(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError):
        action.install(args)


def test_uninstall_removes_installed_layer(monkeypatch, tmp_path):
    base = tmp_path / "arm-translation"
    _install_files(base)
    args = _patch_install_env(monkeypatch, tmp_path)

    action.uninstall(args)

    assert not arm_translation.is_installed()
    assert not base.exists()


def test_uninstall_when_not_installed_is_quiet(monkeypatch, tmp_path):
    args = _patch_install_env(monkeypatch, tmp_path)

    action.uninstall(args)  # must not raise


def test_status_reports_installed(capsys, monkeypatch, tmp_path):
    base = tmp_path / "arm-translation"
    _install_files(base)
    monkeypatch.setattr(arm_translation, "ARM_TRANSLATION_DIR", str(base))

    action.status(None)

    out = capsys.readouterr().out
    assert "INSTALLED" in out
    assert "libndk_translation.so" in out


def test_status_reports_not_installed(capsys, monkeypatch):
    monkeypatch.setattr(arm_translation, "ARM_TRANSLATION_DIR",
                        "/nonexistent/arm-translation")

    action.status(None)

    out = capsys.readouterr().out
    assert "NOT INSTALLED" in out
