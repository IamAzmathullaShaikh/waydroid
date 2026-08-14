# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools.helpers.images."""

import hashlib
import io
import json
import types
import zipfile

import pytest

import tools.config
import tools.helpers.http
import tools.helpers.images as images


def make_args(tmp_path):
    return types.SimpleNamespace(work=str(tmp_path))


def test_sha256sum():
    data = b"hello world"
    f = io.BytesIO(data)
    assert images.sha256sum(f) == hashlib.sha256(data).hexdigest()
    # The file pointer must be rewound
    assert f.tell() == 0


def test_sha256sum_empty():
    assert images.sha256sum(io.BytesIO(b"")) == hashlib.sha256(b"").hexdigest()


def test_remove_overlay(monkeypatch, tmp_path):
    overlay_rw = tmp_path / "overlay_rw"
    overlay_work = tmp_path / "overlay_work"
    overlay_rw.mkdir()
    overlay_work.mkdir()
    monkeypatch.setitem(tools.config.defaults, "overlay_rw", str(overlay_rw))
    monkeypatch.setitem(tools.config.defaults, "overlay_work", str(overlay_work))
    images.remove_overlay(make_args(tmp_path))
    assert not overlay_rw.exists()
    assert not overlay_work.exists()


def test_remove_overlay_missing_dirs(monkeypatch, tmp_path):
    monkeypatch.setitem(tools.config.defaults, "overlay_rw",
                        str(tmp_path / "missing_rw"))
    monkeypatch.setitem(tools.config.defaults, "overlay_work",
                        str(tmp_path / "missing_work"))
    # Should not raise
    images.remove_overlay(make_args(tmp_path))


def test_make_prop(monkeypatch, tmp_path):
    args = make_args(tmp_path)
    with open(args.work + "/waydroid_base.prop", "w") as f:
        f.write("ro.foo=bar\nro.baz=qux\n")
    monkeypatch.setattr(images, "which", lambda name: None)

    cfg = {
        "user_name": "user",
        "user_id": "1000",
        "group_id": "1000",
        "waydroid_data": "/home/user/.local/share/waydroid/data",
        "background_start": "true",
        "lcd_density": "0",
    }
    full_props_path = args.work + "/waydroid.prop"
    images.make_prop(args, cfg, full_props_path)

    with open(full_props_path) as f:
        props = f.read()
    assert "ro.foo=bar" in props
    assert "waydroid.host.user=user" in props
    assert "waydroid.host.uid=1000" in props
    assert "waydroid.host.gid=1000" in props
    assert "waydroid.host_data_path=/home/user/.local/share/waydroid/data" in props
    assert "waydroid.background_start=true" in props
    assert "waydroid.stub_sensors_hal=1" in props
    assert "ro.sf.lcd_density=" not in props


def test_make_prop_lcd_density(monkeypatch, tmp_path):
    args = make_args(tmp_path)
    with open(args.work + "/waydroid_base.prop", "w") as f:
        f.write("ro.foo=bar\n")
    monkeypatch.setattr(images, "which", lambda name: None)

    cfg = {
        "user_name": "user",
        "user_id": "1000",
        "group_id": "1000",
        "waydroid_data": "/home/user/data",
        "background_start": "true",
        "lcd_density": "320",
    }
    full_props_path = args.work + "/waydroid.prop"
    images.make_prop(args, cfg, full_props_path)

    with open(full_props_path) as f:
        props = f.read()
    assert "ro.sf.lcd_density=320" in props


def test_make_prop_mnt_remap(monkeypatch, tmp_path):
    args = make_args(tmp_path)
    with open(args.work + "/waydroid_base.prop", "w") as f:
        f.write("ro.foo=bar\n")
    monkeypatch.setattr(images, "which", lambda name: None)

    cfg = {
        "user_name": "user",
        "user_id": "1000",
        "group_id": "1000",
        "waydroid_data": "/mnt/userdata",
        "background_start": "true",
        "lcd_density": "0",
    }
    full_props_path = args.work + "/waydroid.prop"
    images.make_prop(args, cfg, full_props_path)

    with open(full_props_path) as f:
        props = f.read()
    assert "waydroid.host_data_path=/mnt_extra/userdata" in props


def test_make_prop_missing_base_prop(tmp_path):
    args = make_args(tmp_path)
    with pytest.raises(RuntimeError):
        images.make_prop(args, {}, args.work + "/waydroid.prop")


def test_make_prop_empty_base_prop(tmp_path):
    args = make_args(tmp_path)
    open(args.work + "/waydroid_base.prop", "w").close()
    with pytest.raises(RuntimeError):
        images.make_prop(args, {}, args.work + "/waydroid.prop")


def test_validate(monkeypatch, tmp_path):
    args = make_args(tmp_path)
    data = b"some image data"
    chksum = hashlib.sha256(data).hexdigest()
    # Channel response with matching id
    monkeypatch.setattr(
        tools.helpers.http, "retrieve",
        lambda url: (200, json.dumps({"response": [{"id": chksum}]}).encode()))
    monkeypatch.setattr(
        tools.config, "load",
        lambda args: {"waydroid": {"system_ota": "https://example.test/system"}})

    image_path = tmp_path / "system.zip"
    image_path.write_bytes(data)
    with open(image_path, "rb") as f:
        assert images.validate(args, "system_ota", f) is True


def test_validate_no_match(monkeypatch, tmp_path):
    args = make_args(tmp_path)
    data = b"some image data"
    monkeypatch.setattr(
        tools.helpers.http, "retrieve",
        lambda url: (200, json.dumps({"response": [{"id": "other"}]}).encode()))
    monkeypatch.setattr(
        tools.config, "load",
        lambda args: {"waydroid": {"system_ota": "https://example.test/system"}})

    image_path = tmp_path / "system.zip"
    image_path.write_bytes(data)
    with open(image_path, "rb") as f:
        assert images.validate(args, "system_ota", f) is False


def test_validate_channel_error(monkeypatch, tmp_path):
    args = make_args(tmp_path)
    monkeypatch.setattr(tools.helpers.http, "retrieve",
                        lambda url: (404, b""))
    monkeypatch.setattr(
        tools.config, "load",
        lambda args: {"waydroid": {"system_ota": "https://example.test/system"}})

    image_path = tmp_path / "system.zip"
    image_path.write_bytes(b"data")
    with open(image_path, "rb") as f:
        assert images.validate(args, "system_ota", f) is False


def test_replace(monkeypatch, tmp_path):
    args = make_args(tmp_path)
    images_path = tmp_path / "images"
    images_path.mkdir()

    system_zip = tmp_path / "system.zip"
    with zipfile.ZipFile(system_zip, "w") as zf:
        zf.writestr("system.img", "fake image contents")

    cfg = {
        "waydroid": {
            "images_path": str(images_path),
            "system_datetime": "0",
            "vendor_datetime": "0",
        }
    }
    monkeypatch.setattr(tools.config, "load", lambda args: cfg)
    saved = {}
    monkeypatch.setattr(tools.config, "save", lambda args, c: saved.update(c))
    monkeypatch.setattr(images, "validate", lambda *a, **kw: True)
    monkeypatch.setattr(images, "remove_overlay", lambda args: None)

    images.replace(args, str(system_zip), 1234, str(tmp_path / "missing.zip"), 0)

    assert (images_path / "system.img").read_text() == "fake image contents"
    assert cfg["waydroid"]["system_datetime"] == "1234"
    assert not system_zip.exists()
    assert saved == cfg


def test_replace_invalid_image(monkeypatch, tmp_path):
    args = make_args(tmp_path)
    images_path = tmp_path / "images"
    images_path.mkdir()

    system_zip = tmp_path / "system.zip"
    system_zip.write_bytes(b"not a valid image")

    cfg = {
        "waydroid": {
            "images_path": str(images_path),
            "system_datetime": "0",
            "vendor_datetime": "0",
        }
    }
    monkeypatch.setattr(tools.config, "load", lambda args: cfg)
    saved = {}
    monkeypatch.setattr(tools.config, "save", lambda args, c: saved.update(c))
    monkeypatch.setattr(images, "validate", lambda *a, **kw: False)
    monkeypatch.setattr(images, "remove_overlay", lambda args: None)

    images.replace(args, str(system_zip), 1234, str(tmp_path / "missing.zip"), 0)

    assert not (images_path / "system.img").exists()
    assert cfg["waydroid"]["system_datetime"] == "0"
    assert not system_zip.exists()
