# Copyright 2026 Waydroid Project
# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import logging
import os
import shutil
import tarfile
import zipfile

import tools.config
from tools import helpers
from tools.helpers import arm_translation


def get_config(args):
    """Load the config-derived args needed to regenerate the base props."""
    cfg = tools.config.load(args)
    args.arch = cfg["waydroid"]["arch"]
    args.images_path = cfg["waydroid"]["images_path"]
    args.vendor_type = cfg["waydroid"]["vendor_type"]
    args.system_ota = cfg["waydroid"]["system_ota"]
    args.vendor_ota = cfg["waydroid"]["vendor_ota"]
    args.session = None


def _extract_archive(archive_path, dest):
    """Extract a .tar/.tar.gz/.tar.xz or .zip archive into dest."""
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as handle:
            try:
                handle.extractall(dest, filter="data")
            except TypeError:
                # Python < 3.12 has no filter parameter
                handle.extractall(dest)
    elif zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as handle:
            handle.extractall(dest)
            # zipfile does not restore the unix permission bits that
            # tarfile keeps; the prebuilt's bin/ executables must stay
            # executable for binfmt_misc to run them.
            for info in handle.infolist():
                mode = (info.external_attr >> 16) & 0o7777
                if mode and not info.is_dir():
                    os.chmod(os.path.join(dest, info.filename),
                             mode & 0o7777)
    else:
        raise RuntimeError("Unsupported archive format: " + archive_path)


def _md5(path):
    """md5 of a file, for verifying downloaded archives."""
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_prebuilts_root(extracted):
    """Locate the directory holding the artifacts inside an extracted tree.

    The community prebuilt archive (supremegamers/vendor_google_...)
    nests the files under ``prebuilts/`` inside a repo-name directory; plain
    user-made archives may put them directly at the top. Returns the path
    whose children look like a /system tree (lib/lib64/etc/bin).
    """
    candidates = [extracted]
    for root, dirs, files in os.walk(extracted):
        if "lib64" in dirs and "lib" in dirs and "etc" in dirs:
            candidates.append(root)
    # Deepest match first: a prebuilts/ dir wins over the archive root.
    candidates.sort(key=lambda p: p.count(os.sep), reverse=True)
    for candidate in candidates:
        if (os.path.isdir(candidate + "/lib64")
                and os.path.isdir(candidate + "/etc")):
            return candidate
    return None


def _copy_to_system_tree(root, dest):
    """Copy a /system artifact tree into dest/system/.

    The helper stores artifacts as ``work/arm-translation/system/...``
    (mirroring the container /system paths); ``root`` is a directory whose
    children are the top-level /system entries (lib/lib64/etc/bin).
    """
    system_dir = dest + "/system"
    os.makedirs(system_dir, exist_ok=True)
    for name in os.listdir(root):
        source_path = os.path.join(root, name)
        target_path = os.path.join(system_dir, name)
        if os.path.isdir(source_path):
            shutil.copytree(source_path, target_path, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, target_path)


def _regenerate_base_props(args):
    """Rewrite waydroid_base.prop so the native-bridge property updates."""
    get_config(args)
    helpers.lxc.make_base_props(args)


def install(args):
    if helpers.arch.host() not in ("x86", "x86_64"):
        raise RuntimeError(
            "ARM translation is only needed on x86/x86_64 hosts, this host "
            "is " + helpers.arch.host())

    dest = arm_translation.ARM_TRANSLATION_DIR
    if os.path.isdir(dest) and os.listdir(dest):
        logging.warning("An ARM translation layer is already installed, "
                        "replacing it")

    # The action always runs as root (ROOT_ACTIONS), so plain rmtree works.
    shutil.rmtree(dest, ignore_errors=True)

    extracted = None
    if args.source:
        source = os.path.abspath(args.source)
        if not os.path.isdir(source):
            raise RuntimeError("Source is not a directory: " + args.source)
        root = _find_prebuilts_root(source)
        if root is None:
            raise RuntimeError(
                "Source does not look like a /system artifact tree (no "
                "lib64/ and etc/ directories): " + args.source)
        _copy_to_system_tree(root, dest)
    elif args.archive or args.url:
        archive = args.archive
        if args.url:
            archive = helpers.http.download(
                args, args.url, "arm_translation")
            if archive is None:
                raise RuntimeError(
                    "Failed to download the ARM translation archive")
        if (args.url and args.url == arm_translation.DEFAULT_ARCHIVE_URL
                and _md5(archive) != arm_translation.DEFAULT_ARCHIVE_MD5):
            raise RuntimeError("Downloaded archive failed the integrity "
                               "check; refusing to install")
        extracted = dest + ".extract"
        shutil.rmtree(extracted, ignore_errors=True)
        os.makedirs(extracted)
        _extract_archive(archive, extracted)
        root = _find_prebuilts_root(extracted)
        if root is None:
            shutil.rmtree(extracted, ignore_errors=True)
            raise RuntimeError(
                "The archive does not contain a /system artifact tree "
                "(no lib64/ and etc/ directories)")
        _copy_to_system_tree(root, dest)
        shutil.rmtree(extracted, ignore_errors=True)
    elif not args.default:
        # Nothing was given and --default was not requested: the prebuilt
        # URL is a third-party artifact, so fetching it is opt-in.
        raise RuntimeError(
            "No artifacts given: pass --source, --archive or --url, or "
            "--default to fetch the standard libndk_translation prebuilt")
    else:
        # --default: fetch the known-good prebuilt (md5-verified).
        logging.info("Downloading the standard libndk_translation prebuilt "
                     "(Android 13)...")
        archive = helpers.http.download(
            args, arm_translation.DEFAULT_ARCHIVE_URL, "arm_translation")
        if archive is None:
            raise RuntimeError(
                "Failed to download the ARM translation archive")
        if _md5(archive) != arm_translation.DEFAULT_ARCHIVE_MD5:
            raise RuntimeError("Downloaded archive failed the integrity "
                               "check; refusing to install")
        extracted = dest + ".extract"
        shutil.rmtree(extracted, ignore_errors=True)
        os.makedirs(extracted)
        _extract_archive(archive, extracted)
        root = _find_prebuilts_root(extracted)
        if root is None:
            shutil.rmtree(extracted, ignore_errors=True)
            raise RuntimeError(
                "The default archive does not contain a /system artifact "
                "tree (no lib64/ and etc/ directories)")
        _copy_to_system_tree(root, dest)
        shutil.rmtree(extracted, ignore_errors=True)

    if not arm_translation.is_installed():
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(
            "The provided files are missing the expected layout; expected "
            "at least system/lib64/libndk_translation.so, "
            "system/lib64/arm64/libc.so and "
            "system/etc/init/ndk_translation.rc. Nothing was installed.")

    _regenerate_base_props(args)
    logging.info("ARM translation layer installed; restart the container "
                 "(waydroid container restart) for it to take effect")


def uninstall(args):
    dest = arm_translation.ARM_TRANSLATION_DIR
    if not os.path.isdir(dest):
        logging.info("ARM translation layer is not installed")
        return
    # The action always runs as root (ROOT_ACTIONS), so plain rmtree works.
    shutil.rmtree(dest, ignore_errors=True)
    _regenerate_base_props(args)
    logging.info("ARM translation layer removed")


def status(args):
    if arm_translation.is_installed():
        print("ARM translation:\tINSTALLED (libndk_translation)")
        for host, container_path, kind in arm_translation.mount_entries():
            print("  -> " + container_path)
    else:
        print("ARM translation:\tNOT INSTALLED")
