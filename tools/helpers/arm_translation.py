# Copyright 2026 Waydroid Project
# SPDX-License-Identifier: GPL-3.0-or-later
"""
ARM64 translation layer (libndk_translation) support.

On x86_64 hosts the Android image is x86_64, but many apps ship ARM-only
binaries. libndk_translation (Google's open-source ARM translator, used by
ChromeOS and the Android emulator) runs them through Android's native
bridge mechanism. The artifacts live under ``work/arm-translation`` and are
bind-mounted into the container's /system at session start; the
``ro.dalvik.vm.native.bridge`` property is set by
``tools/helpers/lxc.py:make_base_props`` when they are installed.

Artifact layout (mirrors the container paths under /system):

    arm-translation/system/lib64/libndk_translation.so
    arm-translation/system/lib64/libndk_translation_proxy.so
    arm-translation/system/lib64/ndk_translation/libarm.so     (32-bit)
    arm-translation/system/lib64/ndk_translation/libarm64.so   (64-bit)
    arm-translation/system/lib/ndk_translation/...             (optional)

libndk_translation is Apache-2.0. Common sources for prebuilt sets are
ChromeOS "guybrush" firmware images (what waydroid_script uses) or
Android-x86 images that ship the translator.
"""

import os

import tools.config

# Directory under work/ holding the artifacts (mirrors container /system)
ARM_TRANSLATION_DIR = tools.config.defaults["work"] + "/arm-translation"

# Files that must be present for the layer to be considered installed.
# libarm64.so is the core; libarm.so (32-bit apps) and the rest are optional.
REQUIRED = [
    "system/lib64/libndk_translation.so",
    "system/lib64/libndk_translation_proxy.so",
    "system/lib64/ndk_translation/libarm64.so",
]

# (relative path under ARM_TRANSLATION_DIR, container path, mount kind)
# Only paths that exist are mounted; "dir" entries use create=dir so the
# mount target is created inside the container.
MOUNT_ENTRIES = [
    ("system/lib64/libndk_translation.so",
     "system/lib64/libndk_translation.so", "file"),
    ("system/lib64/libndk_translation_proxy.so",
     "system/lib64/libndk_translation_proxy.so", "file"),
    ("system/lib64/ndk_translation",
     "system/lib64/ndk_translation", "dir"),
    ("system/lib/ndk_translation",
     "system/lib/ndk_translation", "dir"),
]


def is_installed():
    """True when a usable ARM64 translation layer is present."""
    return all(os.path.isfile(ARM_TRANSLATION_DIR + "/" + rel)
               for rel in REQUIRED)


def mount_entries():
    """(host path, container path, kind) triples for the session LXC config."""
    ret = []
    for rel, container_path, kind in MOUNT_ENTRIES:
        host_path = ARM_TRANSLATION_DIR + "/" + rel
        if os.path.exists(host_path):
            ret.append((host_path, container_path, kind))
    return ret
