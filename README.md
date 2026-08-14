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
image based on [LineageOS](https://lineageos.org/). The image is currently based
on Android 13.

## Install

See install instructions [here](https://docs.waydro.id/usage/install-on-desktops)

## Documentation

Our documentation can be found at [docs.waydro.id](https://docs.waydro.id)

## Running ARM-only apps on x86_64 hosts

On x86_64 hosts the image is x86_64, but many apps ship ARM-only binaries.
Waydroid supports Google's [libndk_translation](https://github.com/google-ndk-translation)
native bridge for those (Apache-2.0, the same translator ChromeOS uses):

```
waydroid arm-translation install --source /path/to/artifacts
# or: waydroid arm-translation install --archive libndk.tar.xz
# or: waydroid arm-translation install --url https://example.org/libndk.tar.xz
# or: waydroid arm-translation install --default
waydroid arm-translation status
```

`--source`/`--archive`/`--url` accept your own artifacts; `--default`
fetches a third-party prebuilt (Android 13, md5-verified) that
[waydroid_script](https://github.com/casualsnek/waydroid_script) also
consumes. The artifacts must mirror the container's `/system` layout (at
least `system/lib64/libndk_translation.so`, `system/lib64/arm64/libc.so`
and `system/etc/init/ndk_translation.rc`; see
`tools/helpers/arm_translation.py` for the full tree). They are synced into
the container's `/system` overlay at session start, before the overlay is
mounted, and `make_base_props` advertises the emulated ABIs
(`arm64-v8a,armeabi-v7a,armeabi`) so both the local PackageManager and
Google Play's delivery check accept ARM-only apps. After installing, restart
the container (`waydroid container restart`); remove it with
`waydroid arm-translation uninstall`.

## Reporting bugs

If you have found an issue with Waydroid, please [file a bug](https://github.com/Waydroid/waydroid/issues/new/choose).

## Get in Touch

If you want to get in contact with the developers please feel free to join the
*Waydroid* groups in [Matrix](https://matrix.to/#/#waydroid:matrix.org) or [Telegram](https://t.me/WayDroid).

Our website can be found at [waydro.id](https://waydro.id/)
