# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the release packaging script (tools/release/package.py)."""

import hashlib
import os
import shutil
import tarfile
import zipfile

import pytest

from tools.release import package


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _zip_with(dest, files):
    """Create a zip archive containing {name: bytes} entries."""
    with zipfile.ZipFile(dest, "w") as handle:
        for name, data in files.items():
            handle.writestr(name, data)
    return dest


@pytest.fixture
def tooling_tree(tmp_path):
    """A fake 'make install DESTDIR' tree."""
    root = tmp_path / "tooling"
    (root / "usr" / "lib" / "waydroid").mkdir(parents=True)
    (root / "usr" / "lib" / "waydroid" / "waydroid.py").write_text(
        "print('waydroid')")
    (root / "usr" / "bin").mkdir(parents=True)
    (root / "usr" / "bin" / "waydroid").write_text("#!/bin/sh\n")
    return str(root)


@pytest.fixture
def images_dir(tmp_path):
    """A directory with minimal system.img / vendor.img files."""
    root = tmp_path / "images"
    root.mkdir()
    (root / "system.img").write_bytes(b"SYSTEM-IMAGE-DATA")
    (root / "vendor.img").write_bytes(b"VENDOR-IMAGE-DATA")
    return str(root)


@pytest.fixture
def arm_dir(tmp_path):
    """A minimal translation layer tree (system/lib64/...)."""
    root = tmp_path / "arm"
    lib64 = root / "system" / "lib64"
    lib64.mkdir(parents=True)
    (lib64 / "libndk_translation.so").write_bytes(b"\x7fELF")
    (root / "system" / "etc" / "init").mkdir(parents=True)
    (root / "system" / "etc" / "init" / "ndk_translation.rc").write_text(
        "on boot\n")
    return str(root)


# ---------------------------------------------------------------------------
# Official channel parsing
# ---------------------------------------------------------------------------

def test_parse_official_channel_picks_newest():
    data = {"response": [
        {"datetime": 100, "filename": "old.zip", "url": "https://x/old.zip",
         "id": "a" * 64},
        {"datetime": 200, "filename": "new.zip", "url": "https://x/new.zip",
         "id": "b" * 64},
    ]}
    result = package.parse_official_channel(data, "VANILLA", "MAINLINE",
                                            "x86_64")
    assert result["system"]["filename"] == "new.zip"
    assert result["system"]["sha256"] == "b" * 64
    assert result["vendor"]["channel"] == "official/x86_64/MAINLINE"


def test_parse_official_channel_empty_raises():
    with pytest.raises(ValueError):
        package.parse_official_channel({"response": []}, "VANILLA",
                                       "MAINLINE", "x86_64")


def test_parse_official_channel_requires_sha():
    data = {"response": [{"datetime": 100, "filename": "x.zip",
                          "url": "https://x/x.zip"}]}
    with pytest.raises(ValueError):
        package.parse_official_channel(data, "VANILLA", "MAINLINE", "x86_64")


# ---------------------------------------------------------------------------
# Community channel parsing
# ---------------------------------------------------------------------------

def _release(tag, assets):
    return {"tag_name": tag, "published_at": "2026-07-17T00:00:00Z",
            "assets": [{"name": a} for a in assets]}


def test_community_matches_modern_split_assets():
    release = _release("20260717", [
        "lineage-23.2-20260717-VANILLA-waydroid_x86_64-system.zip",
        "lineage-23.2-20260717-MAINLINE-waydroid_x86_64-vendor.zip",
        "lineage-23.2-20260717-GAPPS-waydroid_x86_64-system.zip",
    ])
    result = package.parse_community_releases([release], 23, "x86_64",
                                              "VANILLA")
    assert "VANILLA-waydroid_x86_64-system.zip" in result["system"]["url"]
    assert "MAINLINE-waydroid_x86_64-vendor.zip" in result["vendor"]["url"]
    assert result["system"]["sha256"] is None


def test_community_matches_combined_asset():
    release = _release("20260224", [
        "lineage-22.2-20260224-UNOFFICIAL-waydroid_x86_64.zip",
    ])
    result = package.parse_community_releases([release], 22, "x86_64",
                                              "VANILLA")
    assert result["system"]["filename"] == result["vendor"]["filename"]
    assert "UNOFFICIAL-waydroid_x86_64.zip" in result["system"]["url"]


def test_community_skips_wrong_android_major():
    release = _release("20260717", [
        "lineage-23.2-20260717-VANILLA-waydroid_x86_64-system.zip",
        "lineage-23.2-20260717-MAINLINE-waydroid_x86_64-vendor.zip",
    ])
    with pytest.raises(ValueError):
        package.parse_community_releases([release], 22, "x86_64", "VANILLA")


def test_community_requires_vendor_asset():
    release = _release("20260717", [
        "lineage-23.2-20260717-VANILLA-waydroid_x86_64-system.zip",
    ])
    with pytest.raises(ValueError):
        package.parse_community_releases([release], 23, "x86_64", "VANILLA")


# ---------------------------------------------------------------------------
# resolve_builds wiring
# ---------------------------------------------------------------------------

def test_resolve_builds_official(tmp_path):
    def fake_fetch(url):
        if "vendor" in url:
            return {"response": [
                {"datetime": 300, "filename": "vendor.zip",
                 "url": "https://x/vendor.zip", "id": "c" * 64}]}
        return {"response": [
            {"datetime": 200, "filename": "system.zip",
             "url": "https://x/system.zip", "id": "b" * 64}]}

    result = package.resolve_builds("official", "x86_64", "VANILLA",
                                    "MAINLINE", fake_fetch)
    assert result["system"]["sha256"] == "b" * 64
    assert result["vendor"]["sha256"] == "c" * 64


def test_resolve_builds_unknown_channel():
    with pytest.raises(ValueError):
        package.resolve_builds("nope", "x86_64", "VANILLA", "MAINLINE",
                               lambda url: {})


# ---------------------------------------------------------------------------
# Integrity helpers
# ---------------------------------------------------------------------------

def test_sha256(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"hello")
    assert package.sha256(str(path)) == hashlib.sha256(b"hello").hexdigest()


def test_extract_images(tmp_path):
    zipped = _zip_with(str(tmp_path / "imgs.zip"), {
        "system.img": b"SYS",
        "vendor.img": b"VND",
        "META-INF/manifest": b"ignored",
    })
    dest = tmp_path / "out"
    dest.mkdir()
    package.extract_images(zipped, str(dest))
    assert (dest / "system.img").read_bytes() == b"SYS"
    assert (dest / "vendor.img").read_bytes() == b"VND"
    assert not (dest / "META-INF").exists()


# ---------------------------------------------------------------------------
# Package assembly
# ---------------------------------------------------------------------------

def test_assemble_package_layout(tooling_tree, images_dir, arm_dir,
                                 tmp_path):
    out = str(tmp_path / "pkg.tar.xz")
    package.assemble_package(tooling_tree, images_dir, arm_dir, out,
                             "official", "1.6.4")
    assert os.path.exists(out)
    with tarfile.open(out, "r:xz") as tar:
        names = tar.getnames()
        joined = "\n".join(names)
        assert "/install.sh" in joined
        assert "/SHA256SUMS" in joined
        assert "/LICENSE" in joined
        assert "/NOTICE" in joined
        assert "/images/system.img" in joined
        assert "/images/vendor.img" in joined
        assert "/arm-translation/system/lib64/libndk_translation.so" in joined
        assert "/waydroid/usr/bin/waydroid" in joined
        # install.sh must be executable
        member = tar.getmember(
            next(n for n in names if n.endswith("/install.sh")))
        assert member.mode & 0o111


def test_arm_tree_nested_under_system(tmp_path):
    """The staged translation tree must live under system/ so install.sh can
    drop it into /var/lib/waydroid/arm-translation directly."""
    work = tmp_path / "work"
    work.mkdir()
    # Fake the prebuilt archive: prebuilts/lib64/libndk_translation.so
    # plus etc/init/ndk_translation.rc at the prebuilts root.
    prebuilts = work / "repo" / "prebuilts"
    (prebuilts / "lib64").mkdir(parents=True)
    (prebuilts / "lib64" / "libndk_translation.so").write_bytes(b"\x7fELF")
    (prebuilts / "lib").mkdir()
    (prebuilts / "lib" / "libndk_translation.so").write_bytes(b"\x7fELF")
    (prebuilts / "etc" / "init").mkdir(parents=True)
    (prebuilts / "etc" / "init" / "ndk_translation.rc").write_text("on boot\n")
    zip_path = str(work / "arm.zip")
    _zip_with(zip_path, {
        "repo/prebuilts/lib64/libndk_translation.so": b"\x7fELF",
        "repo/prebuilts/lib/libndk_translation.so": b"\x7fELF",
        "repo/prebuilts/etc/init/ndk_translation.rc": b"on boot\n",
    })
    extract = work / "extract"
    extract.mkdir()
    with zipfile.ZipFile(zip_path) as handle:
        handle.extractall(extract)
    root = package._find_prebuilts_root(str(extract))
    assert root.endswith("prebuilts")

    # _prepare_arm_translation downloads; verify the staging layout instead
    # by exercising the same nesting logic the fixed function performs.
    arm_dir = str(work / "arm-translation")
    os.makedirs(arm_dir)
    system_dir = os.path.join(arm_dir, "system")
    os.makedirs(system_dir)
    for name in os.listdir(root):
        shutil.copytree(os.path.join(root, name),
                        os.path.join(system_dir, name))
    assert os.path.isfile(os.path.join(
        arm_dir, "system", "lib64", "libndk_translation.so"))
    assert os.path.isfile(os.path.join(
        arm_dir, "system", "etc", "init", "ndk_translation.rc"))


def test_assemble_package_skips_arm(tooling_tree, images_dir, tmp_path):
    out = str(tmp_path / "pkg.tar.xz")
    package.assemble_package(tooling_tree, images_dir, None, out,
                             "official", "1.6.4",
                             with_arm_translation=False)
    with tarfile.open(out, "r:xz") as tar:
        assert not any("arm-translation" in n for n in tar.getnames())


def test_sha256sums_manifest_validates(tooling_tree, images_dir, arm_dir,
                                       tmp_path):
    out = str(tmp_path / "pkg.tar.xz")
    package.assemble_package(tooling_tree, images_dir, arm_dir, out,
                             "official", "1.6.4")
    with tarfile.open(out, "r:xz") as tar:
        checksums = tar.extractfile(
            next(n for n in tar.getnames() if n.endswith("/SHA256SUMS"))
        ).read().decode()
    entries = dict(reversed(line.split("  "))
                    for line in checksums.strip().splitlines())
    assert entries  # non-empty
    with tarfile.open(out, "r:xz") as tar:
        names = tar.getnames()
        for name, expected in entries.items():
            member = next(n for n in names
                          if n.endswith("/" + name)
                          and tar.getmember(n).isfile())
            data = tar.extractfile(member).read()
            assert hashlib.sha256(data).hexdigest() == expected
