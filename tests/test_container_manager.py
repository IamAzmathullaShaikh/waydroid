# SPDX-License-Identifier: GPL-3.0-or-later
import os

import tools.actions.container_manager as container_manager


class _Args:
    pass


def _fake_user(calls):
    def fake_user(*args, **kwargs):
        calls.append((args, kwargs))
        return 0  # successful command exit code
    return fake_user


def _failing_makedirs(path):
    # Simulate a kernel without the nesting patch: creating the first probe
    # level succeeds but the nested one fails (EPERM).
    os.mkdir(os.path.dirname(path))
    raise OSError("simulated EPERM")


def test_start_networking_runs_script(monkeypatch):
    monkeypatch.setattr(container_manager, "WAYDROID_NET_SCRIPT", "/x/waydroid-net.sh")
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))

    container_manager.start_networking(_Args())

    assert len(calls) == 1
    assert calls[0][0][1] == ["/x/waydroid-net.sh", "start"]
    # No check kwarg: failures must raise so do_start aborts
    assert "check" not in calls[0][1]


def test_stop_networking_best_effort(monkeypatch):
    monkeypatch.setattr(container_manager, "WAYDROID_NET_SCRIPT", "/x/waydroid-net.sh")
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))

    container_manager.stop_networking(_Args())

    assert len(calls) == 1
    assert calls[0][0][1] == ["/x/waydroid-net.sh", "stop"]
    assert calls[0][1]["check"] is False


def test_start_sensors_when_installed(monkeypatch):
    monkeypatch.setattr(
        container_manager, "which", lambda name: "/usr/bin/waydroid-sensord" if name == "waydroid-sensord" else None)
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))
    args = _Args()
    args.HWBINDER_DRIVER = "hwbinder"

    container_manager.start_sensors(args)

    assert len(calls) == 1
    assert calls[0][0][1] == ["waydroid-sensord", "/dev/hwbinder"]
    assert calls[0][1]["output"] == "background"


def test_start_sensors_when_missing(monkeypatch):
    monkeypatch.setattr(container_manager, "which", lambda name: None)
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))

    container_manager.start_sensors(_Args())

    assert calls == []


def _stop_sensors_fake(calls, pidof_output):
    def fake_user(*args, **kwargs):
        calls.append((args, kwargs))
        if args[1][0] == "pidof":
            return pidof_output
        return 0
    return fake_user


def test_stop_sensors_none_running(monkeypatch):
    monkeypatch.setattr(
        container_manager, "which", lambda name: "/usr/bin/waydroid-sensord")
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _stop_sensors_fake(calls, ""))

    container_manager.stop_sensors(_Args())

    assert len(calls) == 1  # only the pidof probe, no kill
    assert calls[0][0][1] == ["pidof", "waydroid-sensord"]


def test_stop_sensors_single_pid(monkeypatch):
    monkeypatch.setattr(
        container_manager, "which", lambda name: "/usr/bin/waydroid-sensord")
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _stop_sensors_fake(calls, "1234"))

    container_manager.stop_sensors(_Args())

    assert calls[1][0][1] == ["kill", "-9", "1234"]


def test_stop_sensors_multiple_pids(monkeypatch):
    # A stale daemon from a crashed session results in multiple pids; all
    # of them must be killed, not passed as one invalid string.
    monkeypatch.setattr(
        container_manager, "which", lambda name: "/usr/bin/waydroid-sensord")
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _stop_sensors_fake(calls, "1234 5678"))

    container_manager.stop_sensors(_Args())

    assert calls[1][0][1] == ["kill", "-9", "1234", "5678"]


def test_set_permissions_system_and_app_modes(monkeypatch, tmp_path):
    system = tmp_path / "sysnode"
    app = tmp_path / "appnode"
    system.touch()
    app.touch()
    monkeypatch.setattr(container_manager, "SYSTEM_DEVICES", [str(system)])
    monkeypatch.setattr(container_manager, "APP_DEVICES", [str(app)])
    monkeypatch.setattr("glob.glob", lambda pattern: [])
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))
    session = {"user_id": "1000", "group_id": "1000"}

    container_manager.set_permissions(_Args(), session=session)

    chmods = [c[0][1] for c in calls if c[0][1][0] == "chmod"]
    chowns = [c[0][1] for c in calls if c[0][1][0] == "chown"]
    assert ["chmod", "660", "-R", str(system)] in chmods
    assert ["chmod", "666", "-R", str(app)] in chmods
    assert ["chown", "1000:1000", "-R", str(system)] in chowns
    assert ["chown", "1000:1000", "-R", str(app)] in chowns


def test_set_permissions_without_session_skips_chown(monkeypatch, tmp_path):
    node = tmp_path / "node"
    node.touch()
    monkeypatch.setattr(container_manager, "SYSTEM_DEVICES", [str(node)])
    monkeypatch.setattr(container_manager, "APP_DEVICES", [])
    monkeypatch.setattr("glob.glob", lambda pattern: [])
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))

    container_manager.set_permissions(_Args())

    assert all(c[0][1][0] != "chown" for c in calls)
    assert ["chmod", "660", "-R", str(node)] in [c[0][1] for c in calls]


def test_set_permissions_explicit_list_uses_mode(monkeypatch, tmp_path):
    node = tmp_path / "node"
    node.touch()
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))

    container_manager.set_permissions(_Args(), perm_list=[str(node)], mode="660")

    assert [c[0][1] for c in calls] == [["chmod", "660", "-R", str(node)]]


def test_cgroup_lite_started_when_init_available(monkeypatch):
    monkeypatch.setattr(
        container_manager, "which", lambda name: "/usr/bin/start" if name == "start" else None)
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))

    container_manager.start_cgroup_lite_if_available(_Args())

    assert len(calls) == 1
    assert calls[0][0][1] == ["start", "cgroup-lite"]
    assert calls[0][1]["check"] is False


def test_cgroup_lite_skipped_when_init_unavailable(monkeypatch):
    monkeypatch.setattr(container_manager, "which", lambda name: None)
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))

    container_manager.start_cgroup_lite_if_available(_Args())

    assert calls == []


def test_schedtune_not_mounted_is_noop(monkeypatch):
    monkeypatch.setattr(container_manager, "SCHEDTUNE_PATH", "/nonexistent/schedtune")
    monkeypatch.setattr(os.path, "ismount", lambda path: False)
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))

    container_manager.keep_schedtune_if_nestable(_Args())

    assert calls == []


def test_schedtune_nestable_is_kept(monkeypatch, tmp_path):
    schedtune = str(tmp_path / "schedtune")
    os.mkdir(schedtune)
    monkeypatch.setattr(container_manager, "SCHEDTUNE_PATH", schedtune)
    monkeypatch.setattr(os.path, "ismount", lambda path: path == schedtune)
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))

    container_manager.keep_schedtune_if_nestable(_Args())

    assert calls == []
    assert not os.path.exists(os.path.join(schedtune, "probe0"))


def test_schedtune_not_nestable_is_unmounted(monkeypatch, tmp_path):
    schedtune = str(tmp_path / "schedtune")
    os.mkdir(schedtune)
    monkeypatch.setattr(container_manager, "SCHEDTUNE_PATH", schedtune)
    monkeypatch.setattr(os.path, "ismount", lambda path: path == schedtune)
    calls = []
    monkeypatch.setattr("tools.helpers.run.user", _fake_user(calls))
    monkeypatch.setattr(os, "makedirs", _failing_makedirs)

    container_manager.keep_schedtune_if_nestable(_Args())

    assert len(calls) == 1
    assert calls[0][0][1] == ["umount", "-l", schedtune]
    # Partially created probe must still be cleaned up
    assert not os.path.exists(os.path.join(schedtune, "probe0"))


def test_schedtune_umount_failure_is_logged(monkeypatch, tmp_path, caplog):
    schedtune = str(tmp_path / "schedtune")
    os.mkdir(schedtune)
    monkeypatch.setattr(container_manager, "SCHEDTUNE_PATH", schedtune)
    monkeypatch.setattr(os.path, "ismount", lambda path: path == schedtune)
    monkeypatch.setattr(os, "makedirs", _failing_makedirs)
    monkeypatch.setattr("tools.helpers.run.user", lambda *a, **k: 32)
    monkeypatch.setattr(container_manager.time, "sleep", lambda s: None)

    with caplog.at_level("WARNING"):
        container_manager.keep_schedtune_if_nestable(_Args())

    assert any("Failed to unmount" in record.message for record in caplog.records)
    assert not os.path.exists(os.path.join(schedtune, "probe0"))


def test_schedtune_umount_retried_then_succeeds(monkeypatch, tmp_path):
    # The lazy unmount is retried: a busy hierarchy that frees up on the
    # second attempt must not end up in a warning.
    schedtune = str(tmp_path / "schedtune")
    os.mkdir(schedtune)
    monkeypatch.setattr(container_manager, "SCHEDTUNE_PATH", schedtune)
    monkeypatch.setattr(os.path, "ismount", lambda path: path == schedtune)
    monkeypatch.setattr(os, "makedirs", _failing_makedirs)
    monkeypatch.setattr(container_manager.time, "sleep", lambda s: None)
    attempts = []

    def flaky_umount(*args, **kwargs):
        attempts.append(args)
        return 1 if len(attempts) == 1 else 0

    monkeypatch.setattr("tools.helpers.run.user", flaky_umount)

    container_manager.keep_schedtune_if_nestable(_Args())

    assert len(attempts) == 2
    assert not os.path.exists(os.path.join(schedtune, "probe0"))
