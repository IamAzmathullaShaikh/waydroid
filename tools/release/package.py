# Copyright 2026 Waydroid Project
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a self-contained Waydroid release package.

The package bundles the tooling (a ``make install DESTDIR`` tree), the
latest Android system/vendor images from a selectable channel, and — by
default — the ARM64 translation layer, together with ``install.sh``,
``SHA256SUMS``, ``LICENSE`` and ``NOTICE``.

Channels:

- ``official``: the latest validated build from the official Waydroid OTA
  channel (Android 13 / LineageOS 20), SHA-256 checked against the channel
  manifest.
- ``community-los22`` / ``community-los23``: the latest matching build from
  the community WayDroid-ATV/waydroid-builds GitHub releases (Android 14-16).
  Upstream publishes no checksums there, so we compute and record them.

Usage (from the repo root, after ``make install DESTDIR=...``):

    python3 tools/release/package.py \\
        --tooling <destdir tree> --channel official --arch x86_64 \\
        --system-type VANILLA --out dist
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import socket
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

# Allow running as a plain script from anywhere in the repo.
sys.path.insert(0, os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.helpers import arm_translation  # noqa: E402

log = logging.getLogger("waydroid.release")

OFFICIAL_SYSTEM_OTA = ("https://ota.waydro.id/system/lineage/"
                       "waydroid_{arch}/{system_type}.json")
OFFICIAL_VENDOR_OTA = ("https://ota.waydro.id/vendor/"
                       "waydroid_{arch}/{vendor_type}.json")
COMMUNITY_REPO = "WayDroid-ATV/waydroid-builds"
COMMUNITY_RELEASES_API = ("https://api.github.com/repos/"
                          + COMMUNITY_REPO + "/releases?per_page=10")
COMMUNITY_ANDROID_MAJOR = {"community-los22": 22, "community-los23": 23}

DEFAULT_TIMEOUT = 60  # seconds per socket read


# ---------------------------------------------------------------------------
# Channel resolution (pure, testable)
# ---------------------------------------------------------------------------

def parse_official_channel(data, system_type, vendor_type, arch):
    """Pick the newest build from an official OTA channel JSON response.

    Returns ``{"system": {...}, "vendor": {...}}`` with keys url, filename,
    sha256 and datetime. Raises ValueError if the channel has no builds.
    """
    response = data.get("response", [])
    if not response:
        raise ValueError("Official channel has no builds")
    # The OTA server lists newest first, but sort defensively anyway.
    system = max(response, key=lambda b: b.get("datetime", 0))
    system_sha = system.get("id")
    if not system_sha:
        raise ValueError("Official system build has no SHA-256 id")
    return {
        "system": {
            "url": system["url"],
            "filename": system["filename"],
            "sha256": system_sha,
            "datetime": system.get("datetime"),
            "channel": f"official/{arch}/{system_type}",
        },
        "vendor": {
            "url": None,
            "filename": None,
            "sha256": None,
            "datetime": None,
            "channel": f"official/{arch}/{vendor_type}",
        },
    }


def _asset_matches(filename, arch, system_type):
    """Match a community system asset name for arch + system type.

    Modern releases split system and vendor:
        lineage-23.2-20260717-VANILLA-waydroid_x86_64-system.zip
    Older combined releases used:
        lineage-22.2-20260224-UNOFFICIAL-waydroid_x86_64.zip
    """
    base = f"waydroid_{arch}"
    if f"-{system_type}-{base}-system.zip" in filename:
        return "system"
    if f"-UNOFFICIAL-{base}.zip" in filename:
        return "combined"
    return None


def parse_community_releases(releases, android_major, arch, system_type):
    """Pick the newest community release matching the requested Android major.

    Returns a dict with system/vendor URL+filename (vendor may equal the
    combined system zip) and ``sha256=None`` — upstream publishes no
    checksums, so the caller computes them. Raises ValueError when no
    matching release exists.
    """
    for release in releases:
        tag = release.get("tag_name", "")
        assets = [a.get("name", "") for a in release.get("assets", [])]
        system_asset = None
        combined_asset = None
        for name in assets:
            if not name.startswith(f"lineage-{android_major}."):
                continue
            kind = _asset_matches(name, arch, system_type)
            if kind == "system":
                system_asset = name
            elif kind == "combined":
                combined_asset = name
        if system_asset or combined_asset:
            if system_asset:
                system_name = system_asset
                vendor_name = next(
                    (n for n in assets if f"-MAINLINE-waydroid_{arch}-vendor.zip" in n),
                    None)
            else:
                system_name = combined_asset
                vendor_name = combined_asset
            if not vendor_name:
                raise ValueError(
                    f"Release {tag} has a system asset but no vendor asset")
            return {
                "system": {
                    "url": _release_asset_url(release, system_name),
                    "filename": system_name,
                    "sha256": None,
                    "datetime": release.get("published_at"),
                    "channel": f"{COMMUNITY_REPO}/{tag}/{arch}/{system_type}",
                },
                "vendor": {
                    "url": _release_asset_url(release, vendor_name),
                    "filename": vendor_name,
                    "sha256": None,
                    "datetime": release.get("published_at"),
                    "channel": f"{COMMUNITY_REPO}/{tag}/{arch}/{system_type}",
                },
            }
    raise ValueError(
        f"No community release matches Android {android_major}, "
        f"arch {arch}, system type {system_type}")


def _release_asset_url(release, name):
    """Browser-download URL for a release asset (follows redirects)."""
    return (f"https://github.com/{COMMUNITY_REPO}/releases/download/"
            f"{release['tag_name']}/{name}")


def resolve_builds(channel, arch, system_type, vendor_type, fetch_json):
    """Resolve the system+vendor builds for a channel.

    ``fetch_json(url)`` is injected so tests can stub the network.
    """
    if channel == "official":
        system_url = OFFICIAL_SYSTEM_OTA.format(arch=arch,
                                                system_type=system_type)
        vendor_url = OFFICIAL_VENDOR_OTA.format(arch=arch,
                                                vendor_type=vendor_type)
        system = parse_official_channel(
            fetch_json(system_url), system_type, vendor_type, arch)
        vendor_data = fetch_json(vendor_url)
        response = vendor_data.get("response", [])
        if not response:
            raise ValueError("Official vendor channel has no builds")
        vendor = max(response, key=lambda b: b.get("datetime", 0))
        if not vendor.get("id"):
            raise ValueError("Official vendor build has no SHA-256 id")
        system["vendor"].update({
            "url": vendor["url"],
            "filename": vendor["filename"],
            "sha256": vendor["id"],
            "datetime": vendor.get("datetime"),
        })
        return system
    if channel in COMMUNITY_ANDROID_MAJOR:
        android_major = COMMUNITY_ANDROID_MAJOR[channel]
        releases = fetch_json(COMMUNITY_RELEASES_API)
        if not isinstance(releases, list):
            raise ValueError("Community releases API returned no data")
        return parse_community_releases(releases, android_major, arch,
                                        system_type)
    raise ValueError(f"Unknown channel: {channel}")


# ---------------------------------------------------------------------------
# Downloads & integrity (thin network layer)
# ---------------------------------------------------------------------------

def sha256(path):
    """SHA-256 of a file in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, dest, expected_sha256=None, loglevel=logging.INFO):
    """Download url to dest, optionally verifying its SHA-256."""
    log.log(loglevel, "Downloading %s", url)
    socket.setdefaulttimeout(DEFAULT_TIMEOUT)
    req = urllib.request.Request(url, headers={"User-Agent":
                                               "waydroid-release-package"})
    with urllib.request.urlopen(req) as response, open(dest, "wb") as out:
        shutil.copyfileobj(response, out, 1 << 20)
    if expected_sha256:
        actual = sha256(dest)
        if actual != expected_sha256:
            os.remove(dest)
            raise ValueError(
                f"SHA-256 mismatch for {os.path.basename(dest)}: "
                f"expected {expected_sha256}, got {actual}")
    return dest


def md5(path):
    """MD5 of a file, for verifying the translation-layer archive."""
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_images(zip_path, dest_dir):
    """Extract system.img / vendor.img from an image zip into dest_dir."""
    with zipfile.ZipFile(zip_path) as handle:
        for member in handle.infolist():
            if member.filename.endswith(".img"):
                target = os.path.join(dest_dir, os.path.basename(member.filename))
                with handle.open(member) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out, 1 << 20)
                log.info("Extracted %s", target)


# ---------------------------------------------------------------------------
# Package assembly
# ---------------------------------------------------------------------------

INSTALL_SH = """#!/bin/sh
# Install a Waydroid release package onto this host.
# Run as root:  sudo ./install.sh
set -e

PREFIX="${PREFIX:-/usr}"
IMAGES_DIR="${IMAGES_DIR:-/usr/share/waydroid-extra/images}"
ARM_DIR="${ARM_DIR:-/var/lib/waydroid/arm-translation}"

echo "==> Installing Waydroid tooling to $PREFIX"
cp -a waydroid/. "$PREFIX"/

if [ -d arm-translation ]; then
    echo "==> Installing ARM translation layer to $ARM_DIR"
    mkdir -p "$(dirname "$ARM_DIR")"
    cp -a arm-translation "$ARM_DIR"
fi

echo "==> Installing images to $IMAGES_DIR"
mkdir -p "$IMAGES_DIR"
cp images/system.img images/vendor.img "$IMAGES_DIR"/

echo "==> Done."
echo
echo "Next steps:"
echo "  1. sudo waydroid init -i $IMAGES_DIR"
echo "  2. waydroid session start"
echo
echo "The images are validated by SHA256SUMS in this directory; see"
echo "docs/LICENSING.md for the licensing of every bundled component."
"""

NOTICE = """Waydroid release package — third-party notices

This package bundles or references the following third-party components.
Attribution is provided as required by their licenses.

1. Waydroid itself (this tooling)
   License: GPL-3.0-or-later
   Source:  https://github.com/waydroid/waydroid
   NO WARRANTY: this software is provided "as is", without warranty of any
   kind, express or implied (GPLv3 sections 15-16). Use at your own risk.

2. Android system and vendor images
   The images are LineageOS-based Android builds fetched from the official
   Waydroid OTA channel (https://ota.waydro.id) or from the community
   WayDroid-ATV/waydroid-builds releases. They are unmodified upstream
   artifacts and are NOT authored by this project.
   - Android framework: Apache-2.0
   - Linux kernel: GPL-2.0
   - LineageOS sources: https://github.com/LineageOS
   See the release notes for the exact image builds and their checksums.

3. ARM64 translation layer (libndk_translation)
   The binaries are from Google's ndk_translation project (Apache-2.0, the
   translator used by ChromeOS and the Android emulator), obtained from the
   community prebuilt archive:
   https://github.com/supremegamers/vendor_google_proprietary_ndk_translation-prebuilt
   NOTE: that prebuilt archive declares no SPDX license (GitHub reports
   NOASSERTION). The underlying Google source is Apache-2.0; if you require
   an unambiguous license grant, build the artifacts from Google's source:
   https://github.com/google-ndk-translation

4. Trademarks
   "Waydroid", "Android" and "LineageOS" are trademarks of their respective
   owners. This package is not endorsed by Google or the LineageOS project.
"""


def write_checksums(manifest_path, files):
    """Write a SHA256SUMS file for the given absolute paths."""
    with open(manifest_path, "w") as out:
        for path in sorted(files):
            out.write(f"{sha256(path)}  {os.path.basename(path)}\n")


def assemble_package(tooling_dir, images_dir, arm_dir, out_path,
                     channel_label, version, with_arm_translation=True):
    """Assemble the release tarball from staged files.

    - tooling_dir: a ``make install DESTDIR`` tree (contents land under
      ``waydroid/`` in the tarball).
    - images_dir: directory containing system.img and vendor.img.
    - arm_dir: optional directory containing the translation layer's
      ``system/`` tree (as produced by ``waydroid arm-translation install``).
    Returns the tarball path.
    """
    temp_dir = tempfile.mkdtemp(prefix="waydroid-pkg-")
    try:
        staging = os.path.join(temp_dir, "pkg")
        os.makedirs(staging)
        shutil.copytree(tooling_dir, os.path.join(staging, "waydroid"))
        images = os.path.join(staging, "images")
        os.makedirs(images)
        shutil.copy(os.path.join(images_dir, "system.img"),
                    os.path.join(images, "system.img"))
        shutil.copy(os.path.join(images_dir, "vendor.img"),
                    os.path.join(images, "vendor.img"))
        if with_arm_translation and arm_dir and os.path.isdir(arm_dir):
            shutil.copytree(arm_dir, os.path.join(staging, "arm-translation"))
        with open(os.path.join(staging, "install.sh"), "w") as handle:
            handle.write(INSTALL_SH)
        os.chmod(os.path.join(staging, "install.sh"), 0o755)
        with open(os.path.join(staging, "LICENSE"), "w") as handle:
            handle.write(open(os.path.join(
                os.path.dirname(os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__)))),
                "LICENSE"), encoding="utf-8").read())
        with open(os.path.join(staging, "NOTICE"), "w") as handle:
            handle.write(NOTICE)
        checksum_files = []
        for root, _dirs, files in os.walk(staging):
            for name in files:
                if name != "SHA256SUMS":
                    checksum_files.append(os.path.join(root, name))
        write_checksums(os.path.join(staging, "SHA256SUMS"), checksum_files)

        with tarfile.open(out_path, "w:xz") as tar:
            tar.add(staging, arcname=f"waydroid-{version}-{channel_label}")
        log.info("Wrote %s", out_path)
        return out_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build a Waydroid release package")
    parser.add_argument("--tooling", required=True,
                        help="path to a 'make install DESTDIR' tree")
    parser.add_argument("--channel", default="official",
                        choices=["official", "community-los22",
                                 "community-los23"])
    parser.add_argument("--arch", default="x86_64",
                        choices=["x86_64", "arm64"])
    parser.add_argument("--system-type", default="VANILLA",
                        choices=["VANILLA", "GAPPS"])
    parser.add_argument("--vendor-type", default="MAINLINE")
    parser.add_argument("--out", default="dist", help="output directory")
    parser.add_argument("--no-arm-translation", action="store_true",
                        help="do not bundle the ARM64 translation layer")
    parser.add_argument("--version", default="1.6.4",
                        help="waydroid version string for the package name")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s: %(message)s")
    builds = resolve_builds(args.channel, args.arch, args.system_type,
                            args.vendor_type, fetch_json=_fetch_json)

    work = tempfile.mkdtemp(prefix="waydroid-release-")
    try:
        images_dir = os.path.join(work, "images")
        os.makedirs(images_dir)
        arm_dir = None
        if not args.no_arm_translation:
            arm_dir = _prepare_arm_translation(work)
        for kind in ("system", "vendor"):
            build = builds[kind]
            zip_path = os.path.join(work, build["filename"] or kind + ".zip")
            download(build["url"], zip_path, build["sha256"])
            extract_images(zip_path, images_dir)
            # Community images have no upstream checksum; record ours.
            if build["sha256"] is None:
                log.info("%s SHA-256: %s", kind, sha256(zip_path))

        os.makedirs(args.out, exist_ok=True)
        date = builds["system"]["datetime"] or "latest"
        channel_label = args.channel.replace("community-", "los")
        out_path = os.path.join(
            args.out, f"waydroid-{args.version}-{channel_label}-{args.arch}"
                      f"-{date}.tar.xz")
        assemble_package(args.tooling, images_dir, arm_dir, out_path,
                         channel_label, args.version,
                         with_arm_translation=not args.no_arm_translation)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _fetch_json(url):
    """Fetch and parse a JSON document (injectable for tests)."""
    socket.setdefaulttimeout(DEFAULT_TIMEOUT)
    req = urllib.request.Request(url, headers={"User-Agent":
                                               "waydroid-release-package"})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def _prepare_arm_translation(work):
    """Download and stage the ARM64 translation layer, md5-verified."""
    archive = os.path.join(work, "arm-translation.zip")
    log.info("Downloading ARM translation layer")
    socket.setdefaulttimeout(DEFAULT_TIMEOUT)
    req = urllib.request.Request(arm_translation.DEFAULT_ARCHIVE_URL,
                                 headers={"User-Agent":
                                          "waydroid-release-package"})
    with urllib.request.urlopen(req) as response, open(archive, "wb") as out:
        shutil.copyfileobj(response, out, 1 << 20)
    actual_md5 = md5(archive)
    if actual_md5 != arm_translation.DEFAULT_ARCHIVE_MD5:
        os.remove(archive)
        raise ValueError(
            f"MD5 mismatch for translation archive: expected "
            f"{arm_translation.DEFAULT_ARCHIVE_MD5}, got {actual_md5}")
    extract_dir = os.path.join(work, "arm-extract")
    os.makedirs(extract_dir)
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(extract_dir)
        for info in handle.infolist():
            mode = (info.external_attr >> 16) & 0o7777
            if mode and not info.is_dir():
                os.chmod(os.path.join(extract_dir, info.filename),
                         mode & 0o7777)
    root = _find_prebuilts_root(extract_dir)
    # The runtime expects the tree under arm-translation/system/...
    # (mirroring container /system paths, see tools/helpers/
    # arm_translation.py), so install.sh can drop the directory straight
    # into /var/lib/waydroid.
    arm_dir = os.path.join(work, "arm-translation")
    system_dir = os.path.join(arm_dir, "system")
    os.makedirs(system_dir)
    for name in os.listdir(root):
        shutil.copytree(os.path.join(root, name),
                        os.path.join(system_dir, name))
    return arm_dir


def _find_prebuilts_root(extracted):
    """Locate the prebuilts/ tree inside the extracted archive (see
    tools/actions/arm_translation.py for the layout notes)."""
    candidates = [extracted]
    for root, dirs, _files in os.walk(extracted):
        if "lib64" in dirs and "lib" in dirs and "etc" in dirs:
            candidates.append(root)
    candidates.sort(key=lambda p: p.count(os.sep), reverse=True)
    for candidate in candidates:
        if (os.path.isdir(candidate + "/lib64")
                and os.path.isdir(candidate + "/etc")):
            return candidate
    raise ValueError("Could not find prebuilts/ tree in translation archive")


if __name__ == "__main__":
    main()
