# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the LXC config generation in tools.helpers.lxc."""

import types

import pytest

import tools.config
import tools.helpers.lxc as lxc


class _Args:
    vendor_type = "MAINLINE"
    BINDER_DRIVER = "binder"
    VNDBINDER_DRIVER = "vndbinder"
    HWBINDER_DRIVER = "hwbinder"


def _fake_glob(pattern):
    return {
        "/dev/fb*": ["/dev/fb0"],
        "/dev/graphics/fb*": [],
        "/dev/video*": [],
        "/dev/dma_heap/*": [],
    }.get(pattern, [])


def _build_nodes(monkeypatch, exists=None):
    monkeypatch.setattr("glob.glob", _fake_glob)
    monkeypatch.setattr(tools.helpers.gpu, "getDriNode",
                        lambda args: ("/dev/dri/renderD128", ""))
    if exists is None:
        monkeypatch.setattr("os.path.exists", lambda path: True)
    else:
        monkeypatch.setattr("os.path.exists", exists)
    return lxc.generate_nodes_lxc_config(_Args())


def test_nodes_include_core_entries(monkeypatch):
    text = "\n".join(_build_nodes(monkeypatch))

    assert "lxc.mount.entry = tmpfs dev tmpfs nosuid 0 0" in text
    assert ("lxc.mount.entry = /dev/dri/renderD128 dev/dri/renderD128 "
            "none bind,create=file,optional 0 0") in text
    assert ("lxc.mount.entry = /dev/binder dev/binder "
            "none bind,create=file,optional 0 0") in text
    assert ("lxc.mount.entry = /dev/vndbinder dev/vndbinder "
            "none bind,create=file,optional 0 0") in text
    assert ("lxc.mount.entry = /dev/hwbinder dev/hwbinder "
            "none bind,create=file,optional 0 0") in text
    assert ("lxc.mount.entry = /dev/net/tun dev/tun "
            "none bind,create=file,optional 0 0") in text
    assert "lxc.mount.entry = /dev/fb0 dev/fb0" in text


def test_nodes_skip_missing_check_nodes(monkeypatch):
    # Only /dev/zero exists; everything else with check=True is skipped.
    text = "\n".join(_build_nodes(
        monkeypatch, exists=lambda path: path == "/dev/zero"))

    # check=False entries are always present (binder, tmpfs)
    assert "lxc.mount.entry = /dev/binder dev/binder" in text
    assert "lxc.mount.entry = tmpfs dev tmpfs nosuid 0 0" in text
    # check=True entries for missing nodes are skipped
    assert "/dev/ion" not in text
    assert "/dev/ashmem" not in text
    assert "/dev/sw_sync" not in text
    assert "/dev/null" not in text


def test_session_config_binds_wayland_and_userdata(monkeypatch, tmp_path):
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    session = {
        "user_id": "1000",
        "xdg_runtime_dir": str(xdg),
        "wayland_display": "wayland-0",
        "pulse_runtime_path": str(xdg) + "/pulse",
        "waydroid_data": str(data),
    }
    work = tmp_path / "work"
    work.mkdir()
    args = types.SimpleNamespace(work=str(work))
    monkeypatch.setitem(tools.config.defaults, "container_xdg_runtime_dir",
                        "/run/xdg")
    monkeypatch.setitem(tools.config.defaults, "container_wayland_display",
                        "wayland-0")
    monkeypatch.setitem(tools.config.defaults,
                        "container_pulse_runtime_path", "/run/xdg/pulse")
    monkeypatch.setattr("tools.helpers.run.user", lambda *a, **k: None)

    lxc.generate_session_lxc_config(args, session)

    content = (work / "config_session").read_text()
    assert "lxc.mount.entry = tmpfs /run/xdg none create=dir 0 0" in content
    assert ("lxc.mount.entry = {0}/wayland-0 run/xdg/wayland-0 "
            "none rbind,create=file 0 0".format(xdg)) in content
    assert ("lxc.mount.entry = {0}/pulse/native run/xdg/pulse/native "
            "none rbind,create=file 0 0".format(xdg)) in content
    assert ("lxc.mount.entry = {0} data none rbind 0 0".format(data)) in content


def test_session_config_arm_translation_entries(monkeypatch, tmp_path):
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    session = {
        "user_id": "1000",
        "xdg_runtime_dir": str(xdg),
        "wayland_display": "wayland-0",
        "pulse_runtime_path": str(xdg) + "/pulse",
        "waydroid_data": str(tmp_path / "data"),
    }
    work = tmp_path / "work"
    work.mkdir()
    args = types.SimpleNamespace(work=str(work))
    monkeypatch.setitem(tools.config.defaults, "container_xdg_runtime_dir",
                        "/run/xdg")
    monkeypatch.setitem(tools.config.defaults, "container_wayland_display",
                        "wayland-0")
    monkeypatch.setitem(tools.config.defaults,
                        "container_pulse_runtime_path", "/run/xdg/pulse")
    monkeypatch.setattr("tools.helpers.run.user", lambda *a, **k: None)
    monkeypatch.setattr(
        tools.helpers.arm_translation, "mount_entries",
        lambda: [("/var/lib/waydroid/arm-translation/system/lib64/"
                  "libndk_translation.so",
                  "system/lib64/libndk_translation.so", "file"),
                 ("/var/lib/waydroid/arm-translation/system/lib64/"
                  "ndk_translation",
                  "system/lib64/ndk_translation", "dir")])

    lxc.generate_session_lxc_config(args, session)

    content = (work / "config_session").read_text()
    assert ("lxc.mount.entry = /var/lib/waydroid/arm-translation/system/lib64/"
            "libndk_translation.so system/lib64/libndk_translation.so "
            "none bind,create=file,optional 0 0") in content
    assert ("lxc.mount.entry = /var/lib/waydroid/arm-translation/system/lib64/"
            "ndk_translation system/lib64/ndk_translation "
            "none bind,create=dir,optional 0 0") in content


def test_session_config_rejects_newline_in_mount_path(monkeypatch, tmp_path):
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    session = {
        "user_id": "1000",
        "xdg_runtime_dir": str(xdg),
        "wayland_display": "bad\npath",
        "pulse_runtime_path": str(xdg) + "/pulse",
        "waydroid_data": str(tmp_path / "data"),
    }
    work = tmp_path / "work"
    work.mkdir()
    args = types.SimpleNamespace(work=str(work))
    monkeypatch.setitem(tools.config.defaults, "container_xdg_runtime_dir",
                        "/run/xdg")
    monkeypatch.setitem(tools.config.defaults, "container_wayland_display",
                        "wayland-0")
    monkeypatch.setitem(tools.config.defaults,
                        "container_pulse_runtime_path", "/run/xdg/pulse")

    with pytest.raises(OSError):
        lxc.generate_session_lxc_config(args, session)
