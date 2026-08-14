# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for tools.helpers.mount."""

import io
import os

import pytest

import tools.helpers.mount as mount
from tools.helpers.version import kernel_version, versiontuple


def write_mounts(tmp_path, content):
    path = tmp_path / "mounts"
    path.write_text(content)
    return str(path)


def test_umount_all_list(tmp_path):
    content = "\n".join([
        "overlay /var/lib/waydroid/rootfs overlay rw 0 0",
        "/dev/sda1 /var/lib/waydroid/rootfs/vendor ext4 ro 0 0",
        "/dev/sdb1 /other ext4 rw 0 0",
    ]) + "\n"
    source = write_mounts(tmp_path, content)
    result = mount.umount_all_list("/var/lib/waydroid/rootfs", source)
    assert result == ["/var/lib/waydroid/rootfs/vendor",
                      "/var/lib/waydroid/rootfs"]


def test_umount_all_list_no_match(tmp_path):
    content = "/dev/sda1 /var/lib/waydroid/rootfs ext4 ro 0 0\n"
    source = write_mounts(tmp_path, content)
    assert mount.umount_all_list("/tmp", source) == []


def test_umount_all_list_deleted_suffix(tmp_path):
    # Deleted mount points have a "\040(deleted)" suffix that must be stripped
    content = "/dev/sda1 /var/lib/waydroid/rootfs\\040(deleted) ext4 ro 0 0\n"
    source = write_mounts(tmp_path, content)
    result = mount.umount_all_list("/var/lib/waydroid", source)
    assert result == ["/var/lib/waydroid/rootfs"]


def test_umount_all_list_bad_line(tmp_path):
    # A mount line with fewer than 2 fields is malformed
    content = "onlyonefield\n"
    source = write_mounts(tmp_path, content)
    with pytest.raises(RuntimeError):
        mount.umount_all_list("/var/lib/waydroid", source)


def test_ismount(monkeypatch, tmp_path):
    folder = "/var/lib/waydroid/rootfs"
    content = "overlay {} overlay rw 0 0\n".format(folder)

    class FakeOpen:
        def __call__(self, path, *args, **kwargs):
            return io.StringIO(content)

    monkeypatch.setattr("builtins.open", FakeOpen())
    assert mount.ismount(folder)
    assert not mount.ismount("/var/lib/waydroid/nonexistent")


def test_ismount_source_dest(monkeypatch):
    # ismount() also matches when the folder appears as the source of a bind
    source = "/dev/sda1"
    dest = "/var/lib/waydroid/rootfs"
    content = "{} {} ext4 rw 0 0\n".format(source, dest)

    class FakeOpen:
        def __call__(self, path, *args, **kwargs):
            return io.StringIO(content)

    monkeypatch.setattr("builtins.open", FakeOpen())
    assert mount.ismount(source)


def _mount_capturing_fake(calls):
    # Simulates the effect of a successful mount: after a `mount` command
    # runs, the destination counts as mounted for the ismount() verification.
    mounted = set()

    def fake_ismount(path):
        return path in mounted

    def fake_user(*args, **kwargs):
        command = args[1]
        calls.append((args, kwargs))
        if command[0] == "mount":
            mounted.add(command[-1])
        return 0
    return fake_ismount, fake_user


def test_bind_mounts_and_creates_destination(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    calls = []
    fake_ismount, fake_user = _mount_capturing_fake(calls)
    monkeypatch.setattr(mount, "ismount", fake_ismount)
    monkeypatch.setattr("tools.helpers.run.user", fake_user)

    mount.bind(object(), str(src), str(dst))

    commands = [c[0][1] for c in calls]
    assert ["mkdir", "-p", str(dst)] in commands
    assert ["mount", "-o", "bind", str(src), str(dst)] in commands


def test_mount_type_and_options(monkeypatch, tmp_path):
    dst = tmp_path / "dst"
    calls = []
    fake_ismount, fake_user = _mount_capturing_fake(calls)
    monkeypatch.setattr(mount, "ismount", fake_ismount)
    monkeypatch.setattr("tools.helpers.run.user", fake_user)

    mount.mount(object(), "overlay", str(dst), mount_type="overlay",
                options=["lowerdir=/a:/b"])

    commands = [c[0][1] for c in calls]
    assert ["mount", "-t", "overlay", "-o", "ro,lowerdir=/a:/b",
            "overlay", str(dst)] in commands


def test_versiontuple():
    assert versiontuple("1.2.3") == (1, 2, 3)
    assert versiontuple("0") == (0,)


def test_kernel_version(monkeypatch):
    class FakeUname:
        release = "6.8.0-arch1-1"

    monkeypatch.setattr(os, "uname", lambda: FakeUname())
    assert kernel_version() == (6, 8)
