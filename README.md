<img align="left" src="data/AppIcon.png" width="64">

# Waydroid

Waydroid uses a container-based approach to boot a full Android system on a
regular GNU/Linux system.

## Overview

Waydroid uses Linux namespaces (user, pid, uts, net, mount, ipc) to run a
full Android system in a container and provide Android applications on
any GNU/Linux-based platform.

The Android system inside the container has direct access to any needed hardware.

The Android runtime environment ships with a minimal customized Android system
image based on [LineageOS](https://lineageos.org/). The tooling supports
Android 13 through Android 16 (API 36, LineageOS 20–23): the service-manager
protocol and HAL detection follow the image's API level at runtime
(`tools/helpers/protocol.py`, `tools/helpers/lxc.py`).

The official images on the Waydroid OTA channel are still built on Android 13;
newer LineageOS 22/23 (Android 15/16) images are available as community builds
(e.g. [waydroid-builds](https://github.com/supechicken/waydroid-builds)) and
can be installed with a custom channel:

```
waydroid init -c <system channel> -v <vendor channel> -r lineage
```

Upstream tracks the official image rebuild in
[waydroid/waydroid#2229](https://github.com/waydroid/waydroid/issues/2229).

## Install

See install instructions [here](https://docs.waydro.id/usage/install-on-desktops)

## Documentation

Our documentation can be found at [docs.waydro.id](https://docs.waydro.id)

See also [Host integration mechanisms](docs/host-integration.md) for how
Waydroid reaches into host services and hardware (networking, sensors, NFC).

## Host prerequisites

### Binder devices

Waydroid needs `/dev/binder`, `/dev/hwbinder` and `/dev/vndbinder`. Kernels
with binder built in (`CONFIG_ANDROID_BINDER_IPC=y`, `CONFIG_ANDROID_BINDERFS=y`)
still do not create the nodes until binderfs is mounted; on such systems
expose them with:

```sh
mkdir -p /dev/binderfs
mount -t binder binder /dev/binderfs
ln -sf /dev/binderfs/binder /dev/binder
ln -sf /dev/binderfs/hwbinder /dev/hwbinder
ln -sf /dev/binderfs/vndbinder /dev/vndbinder
```

To make this survive reboots, add the mount to `/etc/fstab`
(`binder /dev/binderfs binder defaults 0 0`) and a systemd-tmpfiles entry
that recreates the symlinks.

### Firewall

Waydroid's container requests its address via DHCP on the `waydroid0`
bridge. On hosts with a default-deny firewall (e.g. ufw), the DHCP
DISCOVER broadcast to port 67 and the FORWARD path are dropped before
Waydroid's own rules run, leaving the container with no address and no
routing. Allow the bridge explicitly:

```sh
ufw allow in on waydroid0 to any port 53,67 proto udp
ufw allow in on waydroid0 to any port 53,67 proto tcp
ufw route allow in on waydroid0
ufw route allow out on waydroid0
```

Without this, `waydroid status` reports `IP address: UNKNOWN` and the
container has no network even though the session and container are running.

## Running ARM-only apps on x86_64 hosts

On x86_64 hosts the image is x86_64, but many apps ship ARM-only binaries.
Waydroid supports Google's [libndk_translation](https://github.com/google-ndk-translation)
native bridge for those (Apache-2.0, the same translator ChromeOS uses):

```
waydroid arm-translation install
# or: waydroid arm-translation install --source /path/to/artifacts
# or: waydroid arm-translation install --archive libndk.tar.xz
# or: waydroid arm-translation install --url https://example.org/libndk.tar.xz
waydroid arm-translation status
```

With no arguments, `install` fetches a known-good prebuilt set (Android 13,
md5-verified) from the same source [waydroid_script](https://github.com/casualsnek/waydroid_script)
consumes; `--source`/`--archive`/`--url` accept your own artifacts. The
artifacts must mirror the container's `/system` layout (at least
`system/lib64/libndk_translation.so`, `system/lib64/arm64/libc.so` and
`system/etc/init/ndk_translation.rc`; see
`tools/helpers/arm_translation.py` for the full tree). They are synced into
the container's `/system` overlay at session start, before the overlay is
mounted, and `make_base_props` advertises the emulated ABIs
(`arm64-v8a,armeabi-v7a,armeabi`) so both the local PackageManager and
Google Play's delivery check accept ARM-only apps. After installing, restart
the container (`waydroid container restart`); remove it with
`waydroid arm-translation uninstall`.

## Release packages

The GitHub Actions workflow [build-release.yaml](.github/workflows/build-release.yaml)
builds a self-contained release package (tooling + latest Android images +
ARM64 translation layer) and publishes it under the repository's
[Releases](https://github.com/IamAzmathullaShaikh/waydroid/releases) page.
It runs weekly and can be triggered manually with the desired inputs:

- **channel**: `official` (latest validated build from ota.waydro.id,
  Android 13 / LineageOS 20) or `community-los22`/`community-los23` (latest
  matching WayDroid-ATV builds, Android 14–16).
- **arch**: `x86_64` or `arm64`.
- **system_type**: `VANILLA` or `GAPPS` (Play Services preinstalled).
- **include_arm_translation**: bundle the ARM64 translation layer (x86_64
  hosts only — the layer is x86-hosted).

Full LineageOS source builds (~300 GB disk, ~5 h) cannot run on
GitHub-hosted runners; the workflow therefore packages the upstream-published
images, validating their SHA-256 against the official channel manifest (or
computing and recording the checksums for community images). See
[docs/LICENSING.md](docs/LICENSING.md) for the licensing and liability
review of every bundled component.

### Using a release package

1. Download the latest `waydroid-*.tar.xz` from the
   [Releases](https://github.com/IamAzmathullaShaikh/waydroid/releases) page
   and verify its checksum against the release notes:

   ```sh
   echo "<sha256>  waydroid-*.tar.xz" | sha256sum -c -
   ```

2. Extract and install (root required):

   ```sh
   tar -xJf waydroid-*.tar.xz
   cd waydroid-*/
   sudo ./install.sh
   ```

   This installs the tooling to `/usr`, the images to
   `/usr/share/waydroid-extra/images`, and (if bundled) the ARM translation
   layer to `/var/lib/waydroid/arm-translation`.

3. Initialize with the preinstalled images — no download needed:

   ```sh
   sudo waydroid init -i /usr/share/waydroid-extra/images
   ```

4. Start the session:

   ```sh
   waydroid session start
   ```

5. (Optional) Verify the ARM translation layer is active on x86_64:

   ```sh
   waydroid arm-translation status
   ```

   If you installed a `GAPPS` image, log in to the Play Store on first boot.

## schedtune cgroup handling

`schedtune` is a cgroup controller used by Android for CPU-boost tuning. On
Ubuntu Touch / Halium devices it is mounted on the host and provides better
system-wide performance with very little effort, and Waydroid's Android keeps
using that mechanism inside the container.

### Why the mount is probed

The Waydroid container inherits the host's cgroup hierarchy read-only
(`lxc.mount.auto = cgroup:ro`). Android can only use schedtune if it can nest
its own cgroups inside the hierarchy, i.e. if new cgroups can be created
within it. That nesting capability requires a kernel patch that some devices
are missing; on those kernels, a read-only, non-nestable schedtune handed to
Android is simply broken.

At container start (`keep_schedtune_if_nestable` in
`tools/actions/container_manager.py`) Waydroid probes for nesting support:

1. If `/sys/fs/cgroup/schedtune` is not mounted, nothing happens.
2. Otherwise it creates a throwaway nested cgroup (`probe0/probe1`):
   - Creation succeeds — the kernel supports nesting — and the mount is kept,
     so Android in the container keeps access to the boost mechanism.
   - Creation fails — the kernel lacks the nesting patch — and the hierarchy
     is lazily unmounted (`umount -l`), letting Android set up its own
     schedtune inside the container.

### What you may observe

- After starting Waydroid, `/sys/fs/cgroup/schedtune` may no longer be mounted
  on the host. That is expected on kernels without the nesting patch.
- If the unmount fails (e.g. the hierarchy is busy), a warning is logged and
  the container inherits the non-nestable hierarchy; schedtune-based
  performance tuning will not work in that session.
- On kernels with nesting support the mount is preserved, so the host's
  schedtune CPU boosting keeps working both on the host and inside the
  container.

### Troubleshooting

The warning

```
Failed to unmount /sys/fs/cgroup/schedtune (umount exited with ...); the
container will inherit a non-nestable schedtune hierarchy
```

is logged when the nesting probe failed (or the hierarchy is otherwise
unusable) and the lazy unmount did not take effect. It is non-fatal: the
container still starts, but schedtune-based performance tuning will not work
inside it.

First check whether the mount is still present and test nesting support
manually as root:

```
findmnt /sys/fs/cgroup/schedtune
mkdir -p /sys/fs/cgroup/schedtune/probe0/probe1
rmdir /sys/fs/cgroup/schedtune/probe0/probe1 /sys/fs/cgroup/schedtune/probe0
```

- If the `mkdir` fails (e.g. `Operation not permitted` or `Read-only file
  system`), the kernel lacks the nesting patch and the probe behaved as
  designed — the remaining problem is the failed unmount. Try unmounting
  manually before starting the container (`umount -l
  /sys/fs/cgroup/schedtune`); if that fails too, something is holding the
  hierarchy (e.g. a bind mount or another container) and must be released
  first.
- If the `mkdir` succeeds but Waydroid still warns, the probe itself should
  have kept the mount — that is unexpected and worth reporting.

When reporting a bug about this warning, please include:

- the relevant section of `waydroid log` (the container service log)
- the Waydroid version and `uname -a`
- the output of `findmnt /sys/fs/cgroup/schedtune` before and after the probe
- the result of the manual probe above
- your device model, and whether the host runs Android init (Ubuntu Touch /
  Halium) or a regular GNU/Linux distribution

### History

Originally Waydroid unmounted schedtune unconditionally, which dropped
performance on devices whose kernels *did* support nesting. The probe was
added so the mount is kept whenever possible and removed only when it would
otherwise be handed to Android broken.

## Reporting bugs

If you have found an issue with Waydroid, please [file a bug](https://github.com/Waydroid/waydroid/issues/new/choose).

## Get in Touch

If you want to get in contact with the developers please feel free to join the
*Waydroid* groups in [Matrix](https://matrix.to/#/#waydroid:matrix.org) or [Telegram](https://t.me/WayDroid).

Our website can be found at [waydro.id](https://waydro.id/)
