# Copyright 2026 Waydroid Project
# SPDX-License-Identifier: GPL-3.0-or-later
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
    else:
        raise RuntimeError("Unsupported archive format: " + archive_path)


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

    if args.source:
        source = os.path.abspath(args.source)
        if not os.path.isdir(source):
            raise RuntimeError("Source is not a directory: " + args.source)
        os.makedirs(dest)
        shutil.copytree(source, dest, dirs_exist_ok=True)
    elif args.archive or args.url:
        archive = args.archive
        if args.url:
            archive = helpers.http.download(
                args, args.url, "arm_translation")
            if archive is None:
                raise RuntimeError(
                    "Failed to download the ARM translation archive")
        os.makedirs(dest)
        _extract_archive(archive, dest)
    else:
        raise RuntimeError(
            "Specify --source <dir>, --archive <file> or --url <url> with "
            "the ARM translation artifacts")

    if not arm_translation.is_installed():
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(
            "The provided files are missing the expected layout; expected "
            "at least system/lib64/libndk_translation.so, "
            "system/lib64/libndk_translation_proxy.so and "
            "system/lib64/ndk_translation/libarm64.so. Nothing was "
            "installed.")

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
