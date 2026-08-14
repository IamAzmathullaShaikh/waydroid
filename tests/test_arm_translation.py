# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the ARM64 translation layer (libndk_translation)."""

import types

import pytest

import tools.config
from tools.helpers import arm_translation
import tools.actions.arm_translation as action


def _install_files(base, required=True):
    """Create the real prebuilt layout under base (a /system tree)."""
    (base / "system/lib64/arm64").mkdir(parents=True)
    (base / "system/lib/arm").mkdir(parents=True)
    (base / "system/etc/init").mkdir(parents=True)
    (base / "system/etc/binfmt_misc").mkdir(parents=True)
    for rel in arm_translation.REQUIRED:
        (base / rel).touch()
    (base / "system/lib64/libndk_translation_proxy_libc.so").touch()
    (base / "system/lib/libndk_translation_proxy_libc.so").touch()
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
    assert all(e[1] != "system/lib64/arm64" for e in entries)
    assert all(e[1] != "system/etc/init/ndk_translation.rc" for e in entries)


def test_mount_entries_include_proxy_libs(monkeypatch, tmp_path):
    base = tmp_path / "arm-translation"
    _install_files(base)
    monkeypatch.setattr(arm_translation, "ARM_TRANSLATION_DIR", str(base))

    entries = arm_translation.mount_entries()
    container_paths = [e[1] for e in entries]

    assert ("system/lib64/arm64", "dir") in [
        (e[1], e[2]) for e in entries]
    assert "system/lib64/libndk_translation_proxy_libc.so" in container_paths
    assert "system/lib/libndk_translation_proxy_libc.so" in container_paths
    assert "system/etc/init/ndk_translation.rc" in container_paths


def test_sync_to_overlay_copies_artifacts(monkeypatch, tmp_path):
    base = tmp_path / "arm-translation"
    _install_files(base)
    overlay = tmp_path / "overlay"
    monkeypatch.setattr(arm_translation, "ARM_TRANSLATION_DIR", str(base))
    monkeypatch.setitem(tools.config.defaults, "overlay", str(overlay))

    arm_translation.sync_to_overlay()

    assert (overlay / "system/lib64/libndk_translation.so").exists()
    assert (overlay / "system/lib64/arm64/libc.so").exists()
    assert (overlay / "system/etc/init/ndk_translation.rc").exists()
    assert (overlay / "system/lib64/libndk_translation_proxy_libc.so").exists()


def test_sync_to_overlay_noop_when_not_installed(monkeypatch, tmp_path):
    overlay = tmp_path / "overlay"
    monkeypatch.setattr(arm_translation, "ARM_TRANSLATION_DIR",
                        "/nonexistent/arm-translation")
    monkeypatch.setitem(tools.config.defaults, "overlay", str(overlay))

    arm_translation.sync_to_overlay()  # must not raise

    assert not (overlay / "system").exists()


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
    return types.SimpleNamespace(source=None, archive=None, url=None,
                                 default=False)


def test_install_from_source_dir(monkeypatch, tmp_path):
    source = tmp_path / "source"
    _install_files(source)
    args = _patch_install_env(monkeypatch, tmp_path)
    args.source = str(source)

    action.install(args)

    assert arm_translation.is_installed()
    assert (tmp_path / "arm-translation/system/lib64/arm64/libc.so").exists()


def test_install_from_source_nested_prebuilts_dir(monkeypatch, tmp_path):
    # The community archive nests artifacts under prebuilts/ inside a
    # repo-name directory; install must find and use that tree.
    source = tmp_path / "source"
    nested = source / "vendor_google_proprietary_ndk_translation-prebuilt-x" \
                    / "prebuilts"
    _install_files(nested)
    args = _patch_install_env(monkeypatch, tmp_path)
    args.source = str(source)

    action.install(args)

    assert arm_translation.is_installed()


def test_install_rejects_missing_layout(monkeypatch, tmp_path):
    source = tmp_path / "source"
    _install_files(source, required=False)
    args = _patch_install_env(monkeypatch, tmp_path)
    args.source = str(source)

    with pytest.raises(RuntimeError):
        action.install(args)

    # Nothing must remain installed
    assert not arm_translation.is_installed()


def test_install_rejects_non_system_tree(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "random.txt").touch()
    args = _patch_install_env(monkeypatch, tmp_path)
    args.source = str(source)

    with pytest.raises(RuntimeError):
        action.install(args)


def test_install_refuses_on_arm64_host(monkeypatch, tmp_path):
    source = tmp_path / "source"
    _install_files(source)
    args = _patch_install_env(monkeypatch, tmp_path)
    args.source = str(source)
    monkeypatch.setattr(action.helpers.arch, "host", lambda: "arm64")

    with pytest.raises(RuntimeError):
        action.install(args)


def test_install_default_url_without_source(monkeypatch, tmp_path):
    """--default with no --source/--archive/--url fetches the prebuilt."""
    args = _patch_install_env(monkeypatch, tmp_path)
    args.default = True

    archive = tmp_path / "default.zip"
    # Build a tiny zip with the prebuilt layout so extraction + validation
    # succeed without network.
    import zipfile
    with zipfile.ZipFile(archive, "w") as zf:
        for rel in arm_translation.REQUIRED:
            zf.writestr("repo/prebuilts/" + rel, "x")
        zf.writestr("repo/prebuilts/system/lib64/libndk_translation_proxy_libc.so", "x")
        zf.writestr("repo/prebuilts/system/lib/libndk_translation_proxy_libc.so", "x")
        zf.writestr("repo/README.md", "x")

    monkeypatch.setattr(action.helpers.http, "download",
                        lambda *a, **k: str(archive))
    monkeypatch.setattr(action, "_md5",
                        lambda path: arm_translation.DEFAULT_ARCHIVE_MD5)

    action.install(args)

    assert arm_translation.is_installed()


def test_install_without_source_requires_default(monkeypatch, tmp_path):
    """No artifacts and no --default: refuse (prebuilt fetch is opt-in)."""
    args = _patch_install_env(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError, match="--default"):
        action.install(args)


def test_extract_archive_preserves_zip_exec_bits(monkeypatch, tmp_path):
    """zipfile drops unix modes; extraction must restore exec bits so
    binfmt_misc can run the ARM translator binaries."""
    import stat
    import zipfile
    archive = tmp_path / "x.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        info = zipfile.ZipInfo("prebuilts/bin/arm64/linker64")
        info.external_attr = (0o755 << 16)
        zf.writestr(info, b"\x7fELF")
        info2 = zipfile.ZipInfo("prebuilts/etc/ndk_translation.rc")
        info2.external_attr = (0o644 << 16)
        zf.writestr(info2, b"on early-init")

    dest = tmp_path / "out"
    dest.mkdir()
    action._extract_archive(str(archive), str(dest))

    linker = dest / "prebuilts/bin/arm64/linker64"
    rc = dest / "prebuilts/etc/ndk_translation.rc"
    assert linker.stat().st_mode & stat.S_IXUSR
    assert not rc.stat().st_mode & stat.S_IXUSR


def test_install_default_url_checks_integrity(monkeypatch, tmp_path):
    args = _patch_install_env(monkeypatch, tmp_path)

    archive = tmp_path / "default.zip"
    archive.write_bytes(b"not a real archive")

    monkeypatch.setattr(action.helpers.http, "download",
                        lambda *a, **k: str(archive))
    monkeypatch.setattr(action, "_md5",
                        lambda path: "00000000000000000000000000000000")

    with pytest.raises(RuntimeError):
        action.install(args)

    assert not arm_translation.is_installed()


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
