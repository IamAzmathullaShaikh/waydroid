# Copyright 2026 Waydroid Project
# SPDX-License-Identifier: GPL-3.0-or-later
"""
ARM64 translation layer (libndk_translation) support.

On x86_64 hosts the Android image is x86_64, but many apps ship ARM-only
binaries. libndk_translation (Google's open-source ARM translator, used by
ChromeOS and the Android emulator) runs them through Android's native
bridge mechanism. The artifacts live under ``work/arm-translation`` and are
bind-mounted into the container's /system at session start.

Artifact layout (mirrors the container paths under /system; this is the
layout of the community prebuilt used by waydroid_script, hosted at
supremegamers/vendor_google_proprietary_ndk_translation-prebuilt):

    arm-translation/system/lib64/libndk_translation.so
    arm-translation/system/lib64/libndk_translation_proxy_lib*.so
    arm-translation/system/lib64/libndk_translation_exec_region.so
    arm-translation/system/lib64/arm64/*.so        (ARM64 system libs)
    arm-translation/system/lib/libndk_translation.so
    arm-translation/system/lib/arm/*.so            (ARM32 system libs)
    arm-translation/system/bin/arm{,64}/            (ARM linker/app_process)
    arm-translation/system/etc/init/ndk_translation.rc
    arm-translation/system/etc/binfmt_misc/
    arm-translation/system/etc/{cpuinfo,ld.config}.arm{,64}.txt

libndk_translation is Apache-2.0.
"""

import os
import shutil

import tools.config

# Directory under work/ holding the artifacts (mirrors container /system)
ARM_TRANSLATION_DIR = tools.config.defaults["work"] + "/arm-translation"

# Default source of prebuilt artifacts (Android 13, i.e. the current
# official Waydroid image). Hosted on GitHub by the same project that
# waydroid_script consumes; md5 verified below before installing.
DEFAULT_ARCHIVE_URL = ("https://github.com/supremegamers/"
                       "vendor_google_proprietary_ndk_translation-prebuilt/"
                       "archive/68734c52556d3d7a6db34c603dd9276915c29f2f.zip")
DEFAULT_ARCHIVE_MD5 = "0b2207c490fcb400aa5c87fcf0d52d38"

# Files that must be present for the layer to be considered installed.
REQUIRED = [
    "system/lib64/libndk_translation.so",
    "system/lib64/arm64/libc.so",
    "system/etc/init/ndk_translation.rc",
]

# Native bridge properties that must be set for the layer to work.
# ro.dalvik.vm.isa.arm{,64} map the emulated ISA to the host ISA; ART and
# the ndk_translation.rc binfmt_misc registration depend on them.
NATIVE_BRIDGE_PROPS = [
    "ro.dalvik.vm.native.bridge=libndk_translation.so",
    "ro.product.cpu.abilist=x86_64,x86,arm64-v8a,armeabi-v7a,armeabi",
    "ro.product.cpu.abilist64=x86_64,arm64-v8a",
    "ro.product.cpu.abilist32=x86,armeabi-v7a,armeabi",
    "ro.product.cpu.abi=x86_64",
    "ro.dalvik.vm.isa.arm=x86",
    "ro.dalvik.vm.isa.arm64=x86_64",
    "ro.enable.native.bridge.exec=1",
    "ro.vendor.enable.native.bridge.exec=1",
    "ro.vendor.enable.native.bridge.exec64=1",
    "ro.ndk_translation.version=0.2.3",
]

# (relative path under ARM_TRANSLATION_DIR, container path)
# Directory entries are bind-mounted with create=dir so the mount target is
# created inside the container; files use create=file. Everything under the
# two lib trees is covered by the dir mounts plus the per-file entries here.
MOUNT_ENTRIES = [
    ("system/lib64/libndk_translation.so",
     "system/lib64/libndk_translation.so", "file"),
    ("system/lib64/libndk_translation_exec_region.so",
     "system/lib64/libndk_translation_exec_region.so", "file"),
    ("system/lib64/arm64", "system/lib64/arm64", "dir"),
    ("system/lib/libndk_translation.so",
     "system/lib/libndk_translation.so", "file"),
    ("system/lib/libndk_translation_exec_region.so",
     "system/lib/libndk_translation_exec_region.so", "file"),
    ("system/lib/arm", "system/lib/arm", "dir"),
    ("system/bin/arm", "system/bin/arm", "dir"),
    ("system/bin/arm64", "system/bin/arm64", "dir"),
    ("system/etc/init/ndk_translation.rc",
     "system/etc/init/ndk_translation.rc", "file"),
    ("system/etc/binfmt_misc", "system/etc/binfmt_misc", "dir"),
    ("system/etc/cpuinfo.arm.txt",
     "system/etc/cpuinfo.arm.txt", "file"),
    ("system/etc/cpuinfo.arm64.txt",
     "system/etc/cpuinfo.arm64.txt", "file"),
    ("system/etc/ld.config.arm.txt",
     "system/etc/ld.config.arm.txt", "file"),
    ("system/etc/ld.config.arm64.txt",
     "system/etc/ld.config.arm64.txt", "file"),
]

# Proxy libs in lib/ and lib64/ are synced into the overlay individually.
# They carry libndk_translation_proxy_lib*.so; globbed at session start.
PROXY_LIB_DIRS = ["system/lib", "system/lib64"]


def is_installed():
    """True when a usable ARM64 translation layer is present."""
    return all(os.path.isfile(ARM_TRANSLATION_DIR + "/" + rel)
               for rel in REQUIRED)


def sync_to_overlay():
    """Copy the installed artifacts into the container's /system overlay.

    The container's /system overlay is mounted read-only, so bind-mounting
    into it at session start fails silently (the mount targets cannot be
    created on a ro filesystem). Instead, mirror waydroid_script: copy the
    artifact tree into the overlay lowerdir (defaults["overlay"]/system),
    which is host-writable while the container is stopped, before the
    overlay is mounted at container start.

    Must run as root before mount_rootfs(). No-ops when nothing is
    installed.
    """
    if not is_installed():
        return
    overlay_dir = tools.config.defaults["overlay"] + "/system"
    os.makedirs(overlay_dir, exist_ok=True)
    source = ARM_TRANSLATION_DIR + "/system"
    for name in os.listdir(source):
        src_path = os.path.join(source, name)
        dst_path = os.path.join(overlay_dir, name)
        if os.path.isdir(src_path):
            shutil.rmtree(dst_path, ignore_errors=True)
            shutil.copytree(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)


def mount_entries():
    """(host path, container path, kind) triples for the session LXC config."""
    ret = []
    for rel, container_path, kind in MOUNT_ENTRIES:
        host_path = ARM_TRANSLATION_DIR + "/" + rel
        if os.path.exists(host_path):
            ret.append((host_path, container_path, kind))
    # The many libndk_translation_proxy_lib*.so files
    for rel_dir in PROXY_LIB_DIRS:
        host_dir = ARM_TRANSLATION_DIR + "/" + rel_dir
        if not os.path.isdir(host_dir):
            continue
        for name in sorted(os.listdir(host_dir)):
            if name.startswith("libndk_translation_proxy_lib"):
                host_path = host_dir + "/" + name
                ret.append((host_path, rel_dir + "/" + name, "file"))
    return ret
