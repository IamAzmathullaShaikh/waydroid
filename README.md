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

## Release packages

The GitHub Actions workflow [build-release.yaml](.github/workflows/build-release.yaml)
builds a self-contained release package (tooling + latest Android images +
optional ARM64 translation layer) and publishes it under the repository's
Releases page. It runs weekly and can be triggered manually with the desired
inputs:

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

1. Download the latest `waydroid-*.tar.xz` from the Releases page and verify
   its checksum against the release notes:

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

## Reporting bugs

If you have found an issue with Waydroid, please [file a bug](https://github.com/Waydroid/waydroid/issues/new/choose).

## Get in Touch

If you want to get in contact with the developers please feel free to join the
*Waydroid* groups in [Matrix](https://matrix.to/#/#waydroid:matrix.org) or [Telegram](https://t.me/WayDroid).

Our website can be found at [waydro.id](https://waydro.id/)
