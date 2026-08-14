# Copyright 2021 Erfan Abdi
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
import glob
import signal
import time
import tools.config
from contextlib import suppress
from shutil import which
from tools import helpers
from tools import services
from tools import actions
import dbus
import dbus.service
import dbus.exceptions
from gi.repository import GLib

# Host path of the schedtune cgroup hierarchy (Ubuntu Touch / Halium)
SCHEDTUNE_PATH = "/sys/fs/cgroup/schedtune"

# Script that sets up the container's private network
WAYDROID_NET_SCRIPT = tools.config.tools_src + "/data/scripts/waydroid-net.sh"

class DbusContainerManager(dbus.service.Object):
    def __init__(self, looper, bus, object_path, args):
        self.args = args
        self.looper = looper
        dbus.service.Object.__init__(self, bus, object_path)

    @helpers.logging.log_exceptions
    @dbus.service.method("id.waydro.ContainerManager", in_signature='a{ss}',
                         out_signature='', sender_keyword="sender",
                         connection_keyword="conn")
    def Start(self, session, sender, conn):
        dbus_info = dbus.Interface(
            conn.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus/Bus", False),
            "org.freedesktop.DBus")
        uid = dbus_info.GetConnectionUnixUser(sender)
        if str(uid) not in ["0", session["user_id"]]:
            raise RuntimeError("Cannot start a session on behalf of another user")
        pid = dbus_info.GetConnectionUnixProcessID(sender)
        if str(uid) != "0" and str(pid) != session["pid"]:
            raise RuntimeError("Invalid session pid")
        do_start(self.args, session)

    def _validate_session_owner(self, sender, conn):
        """
        Ensure the caller is either root or the user owning the currently
        tracked session, mirroring the check in Start().

        The PID check from Start() is intentionally not mirrored here: the
        tracked session is already validated at Start() time, and legitimate
        callers (e.g. "waydroid app install", "waydroid prop set", "waydroid
        session stop") run in different processes than the session process.

        :raises RuntimeError: when the caller is neither root nor the session
                              owner
        """
        dbus_info = dbus.Interface(
            conn.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus/Bus", False),
            "org.freedesktop.DBus")
        uid = str(dbus_info.GetConnectionUnixUser(sender))
        if uid == "0":
            return
        if "session" not in self.args or uid != self.args.session["user_id"]:
            raise RuntimeError("Cannot control a session on behalf of another user")

    @helpers.logging.log_exceptions
    @dbus.service.method("id.waydro.ContainerManager", in_signature='b',
                         out_signature='', sender_keyword="sender",
                         connection_keyword="conn")
    def Stop(self, quit_session, sender, conn):
        self._validate_session_owner(sender, conn)
        stop(self.args, quit_session)

    @helpers.logging.log_exceptions
    @dbus.service.method("id.waydro.ContainerManager", in_signature='',
                         out_signature='', sender_keyword="sender",
                         connection_keyword="conn")
    def Freeze(self, sender, conn):
        if not actions.initializer.is_initialized(self.args):
            raise RuntimeError("Waydroid is not initialized")
        self._validate_session_owner(sender, conn)
        freeze(self.args)

    @helpers.logging.log_exceptions
    @dbus.service.method("id.waydro.ContainerManager", in_signature='',
                         out_signature='', sender_keyword="sender",
                         connection_keyword="conn")
    def Unfreeze(self, sender, conn):
        if not actions.initializer.is_initialized(self.args):
            raise RuntimeError("Waydroid is not initialized")
        self._validate_session_owner(sender, conn)
        unfreeze(self.args)

    @helpers.logging.log_exceptions
    @dbus.service.method("id.waydro.ContainerManager", in_signature='',
                         out_signature='a{ss}', sender_keyword="sender",
                         connection_keyword="conn")
    def GetSession(self, sender, conn):
        if not actions.initializer.is_initialized(self.args):
            raise RuntimeError("Waydroid is not initialized")
        self._validate_session_owner(sender, conn)
        try:
            session = self.args.session
            session["state"] = helpers.lxc.status(self.args)
            return session
        except AttributeError:
            return {}

# Device nodes that only the container's root processes (vendor HALs)
# access. The container root holds DAC_OVERRIDE, so these can be tightened
# to owner access; Android app processes never open them directly.
SYSTEM_DEVICES = [
    "/dev/Vcodec",
    "/dev/MTK_SMI",
    "/dev/mdp_sync",
    "/dev/mtk_cmdq",
    "/dev/pvr_sync",
    "/sys/kernel/debug/sync/sw_sync",
]

# Device nodes Android app processes (arbitrary host UIDs without
# DAC_OVERRIDE) may open directly; these must stay world-accessible, but
# never executable.
APP_DEVICES = [
    "/dev/ashmem",
    "/dev/ion",
    "/dev/graphics",
    "/dev/sw_sync",
]


def set_permissions(args, perm_list=None, mode="666", session=None):
    """
    Give the container access to host devices.

    The container bind-mounts these host nodes read-write and runs without
    user namespaces, so the mode bits are the boundary between Android and
    the host. The container's root holds DAC_OVERRIDE and bypasses them;
    Android app processes are ordinary host UIDs, so nodes they open
    directly (ashmem, ion, DRM render nodes, framebuffers, video,
    dma-heaps) get 0666 - world read/write, never executable. Nodes only
    the container's root processes (vendor HALs) use get 0660. When a
    session is available the nodes are also owned by the session user.
    Only paths that exist are touched, and failures are non-fatal.
    """
    # Nodes list
    if not perm_list:
        perm_list = list(APP_DEVICES)

        # DRM render nodes
        perm_list.extend(glob.glob("/dev/dri/renderD*"))
        # Framebuffers
        perm_list.extend(glob.glob("/dev/fb*"))
        # Videos
        perm_list.extend(glob.glob("/dev/video*"))
        # DMA-BUF Heaps
        perm_list.extend(glob.glob("/dev/dma_heap/*"))

        perm_list.extend(SYSTEM_DEVICES)

    for path in perm_list:
        if not os.path.exists(path):
            continue
        if session:
            command = ["chown", session["user_id"] + ":" + session["group_id"],
                       "-R", path]
            tools.helpers.run.user(args, command, check=False)
        path_mode = "660" if path in SYSTEM_DEVICES else mode
        tools.helpers.run.user(args, ["chmod", path_mode, "-R", path], check=False)

def wait_for_status(args, status, timeout=30):
    """
    Wait for the container to reach the given LXC status.

    Polls the container status once per second instead of busy-waiting, and
    raises a RuntimeError if the status is not reached within ``timeout``
    seconds.
    """
    tries = 0
    while helpers.lxc.status(args) != status:
        if tries >= timeout:
            raise RuntimeError(
                "WayDroid container did not reach {} state within {} seconds".format(status, timeout))
        tries += 1
        time.sleep(1)

def start(args):
    mainloop = GLib.MainLoop()

    def sigint_handler(data):
        with suppress(Exception):
            stop(args)
        mainloop.quit()

    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, sigint_handler, None)
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, sigint_handler, None)

    initializer = actions.initializer.DbusInitializer(mainloop, dbus.SystemBus(), '/Initializer', args)
    _container_manager = DbusContainerManager(mainloop, dbus.SystemBus(), '/ContainerManager', args)

    try:
        _name = dbus.service.BusName("id.waydro.Container", dbus.SystemBus(), do_not_queue=True)
    except dbus.exceptions.NameExistsException:
        logging.error("Container service is already running")
        return

    mainloop.run()

    if initializer.worker_thread is not None:
        initializer.worker_thread.kill()
        initializer.worker_thread.join()

prepared_drivers = False
def prepare_drivers_once(args):
    global prepared_drivers
    if prepared_drivers:
        return

    # Load binder and ashmem drivers
    cfg = tools.config.load(args)
    if cfg["waydroid"]["vendor_type"] == "MAINLINE":
        if helpers.drivers.probeBinderDriver(args) != 0:
            logging.error("Failed to load Binder driver")
        helpers.drivers.probeAshmemDriver(args)
    helpers.drivers.loadBinderNodes(args)
    set_permissions(args, [
        "/dev/" + args.BINDER_DRIVER,
        "/dev/" + args.VNDBINDER_DRIVER,
        "/dev/" + args.HWBINDER_DRIVER
    ], "666")
    prepared_drivers = True

def start_cgroup_lite_if_available(args):
    """
    Start Android init's "cgroup-lite" service on Halium hosts.

    On Halium / Ubuntu Touch devices the host runs Android's init, which is
    normally responsible for mounting the cgroup hierarchies. Waydroid
    makes sure that service is running before the container starts, so the
    container does not inherit a half-set-up cgroup tree. The command only
    exists when Android init's ``start`` binary is on PATH; on regular
    GNU/Linux hosts this is a no-op, as the host init system already
    mounted cgroups.
    """
    if which("start"):
        tools.helpers.run.user(args, ["start", "cgroup-lite"], check=False)

def keep_schedtune_if_nestable(args):
    """
    Keep the host schedtune cgroup mounted only if the container can nest
    its own cgroups inside it, and unmount it otherwise.

    Ubuntu Touch hosts use the schedtune cgroup for CPU-boost tuning, and
    Waydroid's Android keeps using that mechanism inside the container. LXC
    mounts the host cgroup hierarchy into the container read-only
    (lxc.mount.auto), which Android can only use if the hierarchy supports
    nesting, i.e. if new cgroups can be created inside it. Some kernels
    lack the nesting patch, and a non-nestable schedtune handed to Android
    read-only would be broken.

    Nesting support is probed by creating a throwaway subgroup hierarchy
    (probe0/probe1). If creation succeeds the mount is kept; otherwise the
    hierarchy is lazily unmounted so Android sets up its own schedtune in
    the container. The probe directories are always removed afterwards.
    """
    if not os.path.ismount(SCHEDTUNE_PATH):
        return

    probe = SCHEDTUNE_PATH + "/probe0"
    try:
        os.makedirs(probe + "/probe1")
    except OSError:
        logging.debug("Host schedtune cgroup does not support nesting, unmounting it")
        # The hierarchy may be busy for a moment (in-flight processes or a
        # lingering child cgroup), so retry the lazy unmount briefly before
        # giving up and handing the non-nestable hierarchy to the container.
        code = 1
        for attempt in range(3):
            code = tools.helpers.run.user(
                args, ["umount", "-l", SCHEDTUNE_PATH], check=False)
            if code == 0:
                break
            time.sleep(1)
        if code != 0:
            logging.warning(
                "Failed to unmount {} (last umount exited with {}); the container will "
                "inherit a non-nestable schedtune hierarchy. See the README's "
                "schedtune troubleshooting section.".format(SCHEDTUNE_PATH, code))
    finally:
        with suppress(OSError):
            os.rmdir(probe + "/probe1")
        with suppress(OSError):
            os.rmdir(probe)

def start_networking(args):
    """
    Bring up the container's private network (bridge, dnsmasq, NAT).

    Runs ``data/scripts/waydroid-net.sh start``; failures raise, because
    the container cannot function without networking.
    """
    tools.helpers.run.user(args, [WAYDROID_NET_SCRIPT, "start"])

def stop_networking(args):
    """Tear down the container's private network (best-effort)."""
    tools.helpers.run.user(args, [WAYDROID_NET_SCRIPT, "stop"], check=False)

def start_sensors(args):
    """
    Launch the host-side sensor daemon for the container.

    ``waydroid-sensord`` forwards the device's sensors to Android over the
    shared hwbinder. It is optional: if it is not installed, nothing runs.
    """
    if which("waydroid-sensord"):
        tools.helpers.run.user(
            args, ["waydroid-sensord", "/dev/" + args.HWBINDER_DRIVER], output="background")

def stop_sensors(args):
    """Stop the sensor daemon, killing every instance (best-effort)."""
    if which("waydroid-sensord"):
        command = ["pidof", "waydroid-sensord"]
        pids = tools.helpers.run.user(args, command, check=False, output_return=True).strip()
        if pids:
            # pidof may return multiple PIDs (e.g. a stale daemon from a
            # crashed session); kill them all.
            command = ["kill", "-9"] + pids.split()
            tools.helpers.run.user(args, command, check=False)

def do_start(args, session):
    if not actions.initializer.is_initialized(args):
        raise RuntimeError("Waydroid is not initialized")

    if "session" in args:
        raise RuntimeError("Already tracking a session")

    prepare_drivers_once(args)

    logging.info("Starting up container for a new session")

    start_networking(args)
    start_sensors(args)
    start_cgroup_lite_if_available(args)

    keep_schedtune_if_nestable(args)

    # Set permissions
    set_permissions(args, session=session)

    # Create session-specific LXC config file
    helpers.lxc.generate_session_lxc_config(args, session)
    # Backwards compatibility
    with open(tools.config.defaults["lxc"] + "/waydroid/config") as f:
        if "config_session" not in f.read():
            helpers.mount.bind(args, session["waydroid_data"],
                               tools.config.defaults["data"])

    # Mount rootfs
    cfg = tools.config.load(args)
    helpers.images.mount_rootfs(args, cfg["waydroid"]["images_path"], session)

    helpers.protocol.set_aidl_version(args)

    helpers.lxc.start(args)
    services.hardware_manager.start(args)

    args.session = session

def stop(args, quit_session=True):
    if not actions.initializer.is_initialized(args):
        raise RuntimeError("Waydroid is not initialized")

    logging.info("Stopping container")

    try:
        services.hardware_manager.stop(args)
        status = helpers.lxc.status(args)
        if status != "STOPPED":
            helpers.lxc.stop(args)
            try:
                wait_for_status(args, "STOPPED")
            except RuntimeError as e:
                # Best-effort teardown: keep cleaning up even if the container
                # did not stop in time (the rootfs umount below will fail with
                # EBUSY in that case, and is caught by the outer handler).
                logging.error("%s; continuing with cleanup", e)

        stop_networking(args)
        stop_sensors(args)

        # Umount rootfs
        helpers.images.umount_rootfs(args)

        # Backwards compatibility
        with suppress(Exception):
            helpers.mount.umount_all(args, tools.config.defaults["data"])

        if "session" in args:
            if quit_session:
                logging.info("Terminating session because the container was stopped")
                with suppress(OSError):
                    os.kill(int(args.session["pid"]), signal.SIGUSR1)
            del args.session
    except Exception as e:
        logging.debug("Error while stopping container: %s", e)

def restart(args):
    status = helpers.lxc.status(args)
    if status == "RUNNING":
        helpers.lxc.stop(args)
        helpers.lxc.start(args)
    else:
        logging.error("WayDroid container is {}".format(status))

def freeze(args):
    status = helpers.lxc.status(args)
    if status == "RUNNING":
        helpers.lxc.freeze(args)
        wait_for_status(args, "FROZEN")
    else:
        logging.error("WayDroid container is {}".format(status))

def unfreeze(args):
    status = helpers.lxc.status(args)
    if status == "FROZEN":
        helpers.lxc.unfreeze(args)
        wait_for_status(args, "RUNNING")
    else:
        logging.error("WayDroid container is {}".format(status))
