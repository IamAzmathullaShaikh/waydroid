# SPDX-License-Identifier: GPL-3.0-or-later
from tools.helpers import drivers


class _Args:
    pass


def test_loadBinderNodes_falls_back_when_config_missing_keys(tmp_path):
    # Configs predating the binder keys (or partial/corrupt ones) must not
    # crash the session service; fall back to the standard node names.
    cfg_file = tmp_path / "waydroid.cfg"
    cfg_file.write_text("[waydroid]\n")

    args = _Args()
    args.config = str(cfg_file)

    drivers.loadBinderNodes(args)

    assert args.BINDER_DRIVER == "binder"
    assert args.VNDBINDER_DRIVER == "vndbinder"
    assert args.HWBINDER_DRIVER == "hwbinder"
    assert args.BINDER_PROTOCOL is None
    assert args.SERVICE_MANAGER_PROTOCOL is None


def test_loadBinderNodes_uses_config_values(tmp_path):
    cfg_file = tmp_path / "waydroid.cfg"
    cfg_file.write_text(
        "[waydroid]\n"
        "binder = anbox-binder\n"
        "vndbinder = anbox-vndbinder\n"
        "hwbinder = anbox-hwbinder\n"
        "binder_protocol = 2\n"
        "service_manager_protocol = 3\n")

    args = _Args()
    args.config = str(cfg_file)

    drivers.loadBinderNodes(args)

    assert args.BINDER_DRIVER == "anbox-binder"
    assert args.VNDBINDER_DRIVER == "anbox-vndbinder"
    assert args.HWBINDER_DRIVER == "anbox-hwbinder"
    assert args.BINDER_PROTOCOL == "2"
    assert args.SERVICE_MANAGER_PROTOCOL == "3"
