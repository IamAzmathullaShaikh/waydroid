# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools.helpers.protocol."""

import types

import tools.config
import tools.helpers.props
import tools.helpers.protocol as protocol


def make_args():
    return types.SimpleNamespace()


def test_set_aidl_version(monkeypatch):
    cfg = {"waydroid": {}}
    monkeypatch.setattr(tools.config, "load", lambda args: cfg)
    saved = {}
    monkeypatch.setattr(tools.config, "save", lambda args, c: saved.update(c))
    # (sdk, binder_protocol, service_manager_protocol)
    cases = [
        (0, "aidl", "aidl"),
        (27, "aidl", "aidl"),
        (28, "aidl2", "aidl2"),
        (29, "aidl2", "aidl2"),
        (30, "aidl3", "aidl3"),
        (31, "aidl4", "aidl3"),
        (32, "aidl4", "aidl3"),
        (33, "aidl3", "aidl3"),
        (34, "aidl3", "aidl3"),
        (35, "aidl3", "aidl5"),
        (36, "aidl3", "aidl6"),
        # Android 16 (API 36) and newer stay on aidl6 for the service manager
        (37, "aidl3", "aidl6"),
        (40, "aidl3", "aidl6"),
    ]
    for sdk, binder, sm in cases:
        monkeypatch.setattr(tools.helpers.props, "file_get",
                            lambda *args, **kwargs: str(sdk))
        protocol.set_aidl_version(make_args())
        assert cfg["waydroid"]["binder_protocol"] == binder, \
            "binder protocol for sdk {}".format(sdk)
        assert cfg["waydroid"]["service_manager_protocol"] == sm, \
            "service manager protocol for sdk {}".format(sdk)


def test_set_aidl_version_parse_error(monkeypatch):
    """A failing build.prop read falls back to the lowest protocol."""
    cfg = {"waydroid": {}}
    monkeypatch.setattr(tools.config, "load", lambda args: cfg)
    saved = {}
    monkeypatch.setattr(tools.config, "save", lambda args, c: saved.update(c))

    def raise_file_get(*args, **kwargs):
        raise Exception("no build.prop")

    monkeypatch.setattr(tools.helpers.props, "file_get", raise_file_get)
    protocol.set_aidl_version(make_args())
    assert cfg["waydroid"]["binder_protocol"] == "aidl"
    assert cfg["waydroid"]["service_manager_protocol"] == "aidl"
