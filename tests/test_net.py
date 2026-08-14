# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools.helpers.net."""

import io

import tools.helpers.net as net


def test_get_device_ip_address(monkeypatch):
    lease = ("1692540000 00:16:3e:00:00:01 192.168.240.2 "
             "waydroid 00:16:3e:00:00:01\n")
    monkeypatch.setattr("builtins.open", lambda *a, **kw: io.StringIO(lease))

    assert net.get_device_ip_address() == "192.168.240.2"


def test_get_device_ip_address_no_lease(monkeypatch):
    def raise_ioerror(*a, **kw):
        raise IOError("no lease file")

    monkeypatch.setattr("builtins.open", raise_ioerror)

    assert net.get_device_ip_address() is None


def test_get_device_ip_address_no_match(monkeypatch):
    monkeypatch.setattr("builtins.open",
                        lambda *a, **kw: io.StringIO("no ip here\n"))

    assert net.get_device_ip_address() is None
