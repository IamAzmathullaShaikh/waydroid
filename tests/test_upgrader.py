# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools.actions.upgrader.migration()."""

import types

import tools.config
import tools.actions.upgrader as upgrader


def make_args():
    return types.SimpleNamespace(work="/var/lib/waydroid")


def test_migration_adds_missing_binder_keys(monkeypatch):
    cfg = {"waydroid": {}}
    # Old tools version 1.6.3: only the 1.6.3 migration step runs.
    monkeypatch.setattr(tools.helpers.props, "file_get",
                        lambda *a, **kw: "1.6.3")
    monkeypatch.setattr(tools.config, "load", lambda args: cfg)
    saved = {}
    monkeypatch.setattr(tools.config, "save", lambda args, c: saved.update(c))

    upgrader.migration(make_args())

    assert cfg["waydroid"]["binder"] == "binder"
    assert cfg["waydroid"]["vndbinder"] == "vndbinder"
    assert cfg["waydroid"]["hwbinder"] == "hwbinder"
    assert saved == cfg


def test_migration_keeps_existing_binder_keys(monkeypatch):
    cfg = {"waydroid": {"binder": "anbox-binder",
                        "vndbinder": "anbox-vndbinder",
                        "hwbinder": "anbox-hwbinder"}}
    monkeypatch.setattr(tools.helpers.props, "file_get",
                        lambda *a, **kw: "1.6.3")
    monkeypatch.setattr(tools.config, "load", lambda args: cfg)
    saved = {}
    monkeypatch.setattr(tools.config, "save", lambda args, c: saved.update(c))

    upgrader.migration(make_args())

    assert cfg["waydroid"]["binder"] == "anbox-binder"
    # Nothing changed, so the config must not be rewritten.
    assert saved == {}


def test_migration_new_install_is_noop(monkeypatch):
    cfg = {"waydroid": {}}
    monkeypatch.setattr(tools.helpers.props, "file_get",
                        lambda *a, **kw: "1.6.4")
    monkeypatch.setattr(tools.config, "load", lambda args: cfg)
    saved = {}
    monkeypatch.setattr(tools.config, "save", lambda args, c: saved.update(c))

    upgrader.migration(make_args())

    assert saved == {}
    assert "binder" not in cfg["waydroid"]
