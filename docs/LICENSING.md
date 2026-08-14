# Licensing & liability review

This document is a review of the licenses and terms that apply to this
repository and to everything its release packages bundle or fetch. It was
written before adding the GitHub Actions image-build/release workflow, so
the release packaging can be designed to comply with each component's terms
from day one.

This is **not legal advice**. When in doubt about redistribution, consult a
lawyer familiar with software licensing in your jurisdiction.

---

## 1. The Waydroid project itself (this repository)

| Item | License | Evidence |
|------|---------|----------|
| `waydroid.py`, `tools/`, `dbus/`, `systemd/`, `tests/` | **GPL-3.0-or-later** | SPDX headers on every source file; `LICENSE` is the GPLv3 text |
| `debian/*` packaging files | **BSD-3-clause** | `debian/copyright` |
| `data/id.waydro.waydroid.metainfo.xml` | metadata **CC0-1.0**, project **GPL-3.0-only** | `metadata_license` / `project_license` fields |
| `data/AppIcon.png`, desktop/menu files | GPL-3.0-or-later (project default) | part of the project |

### What the GPL-3.0-or-later means for redistribution

- Anyone who conveys the software (or a modified version) must offer the
  **source code** under the same license, include the license text, and mark
  modified files. The Makefile install and our release packages ship
  `LICENSE` alongside the code, and the source is the repo itself — both
  requirements are satisfied by publishing on GitHub.
- GPLv3 §15–17: **no warranty** unless a distributor explicitly provides
  one, and a limitation-of-liability notice is part of the license. We
  redistribute under those exact terms — nothing more, nothing less.
- **No contributor license agreement** exists for this project. Copyright
  stays with each contributor (headers name the authors). That is normal for
  GPL projects and does not block redistribution, but it means the project
  cannot be re-licensed by any single author.

### Liability posture for the project itself

- The project provides no warranty and accepts no liability for damages
  (GPLv3 §15–16). Release notes and README should repeat the "no warranty,
  use at your own risk" notice so downstream users see it without reading
  the license text.
- Trademarks: "Waydroid", "Android" (Google), "LineageOS" are trademarks of
  their owners. Using the names to *describe* compatibility is fine; the
  release artwork/names must not imply endorsement by Google or the
  LineageOS project.

---

## 2. Android images (system.img / vendor.img)

### Official OTA channel (`https://ota.waydro.id`)

The official images are LineageOS-based Android builds published by the
Waydroid project. LineageOS is distributed under the **Apache-2.0** license
for the Android framework and **GPL-2.0** for the Linux kernel parts; the
vendor image contains Mesa/Gallium drivers (MIT) and other third-party
components under their own permissive licenses.

Implications for our release package:

- The images are **already published for redistribution** by their upstream
  (Waydroid OTA / SourceForge). We do not modify them; we only *fetch and
  re-package* the latest build, validating its SHA-256 against the channel
  manifest so we never ship a tampered or mismatched artifact.
- The license obligations that matter are **attribution** (Apache-2.0
  requires retaining notices) and, for the kernel, the GPL-2.0 source offer
  — which is satisfied because the images are built from public LineageOS
  sources and we link to those sources in the release notes.
- We must **not claim** the images are ours or that we built them. Release
  notes will state "LineageOS-based images fetched from the official
  Waydroid OTA channel, unmodified."

### Community channel (WayDroid-ATV / supechicken builds)

Community-built Android 14–16 images are also LineageOS-based, published as
GitHub release assets by third parties under the same underlying licenses.
The same attribution rules apply. Because these builds are *not* published
with a checksum manifest, our packaging script **computes and records**
SHA-256 checksums at build time and includes them in the package's
`SHA256SUMS` — this gives users integrity verification even though upstream
does not provide one.

---

## 3. ARM translation layer (libndk_translation)

| Artifact | License | Notes |
|----------|---------|-------|
| Google's `ndk_translation` **source** | **Apache-2.0** (Google) | The translator used by ChromeOS/Android emulator; the README already states this |
| Community **prebuilt** archive we fetch by default (`supremegamers/vendor_google_proprietary_ndk_translation-prebuilt`) | **unclear — GitHub reports NOASSERTION** | The repo declares no SPDX license; the files are Google's Apache-2.0 binaries but the *packaging* has no explicit grant |

This is the **single most important liability finding** in this review:

1. We do not *commit* the prebuilt into this repository — `waydroid
   arm-translation install` downloads it at runtime, and the release
   workflow downloads it at build time and bundles it into the package.
2. The upstream prebuilt repo has **no explicit license** (GitHub:
   `NOASSERTION`). Redistribution of binaries whose packaging license is
   unclear carries legal risk: the recipient has no explicit permission to
   redistribute, even though the underlying Google source is Apache-2.0.
3. **Mitigation adopted:**
   - The release workflow makes bundling the translation layer **optional**
     (default on, but the operator can disable it with one input).
   - The package's `NOTICE` file states the provenance precisely: binaries
     are from Google's Apache-2.0 ndk_translation, obtained from the
     `supremegamers` prebuilt archive, and that the archive itself declares
     no SPDX license. Users who need an unambiguous license grant should
     build the artifacts from Google's source instead.
   - Nothing in the package hides the origin — attribution is explicit.

---

## 4. Third-party components in the tooling

| Component | License | Where |
|-----------|---------|-------|
| Python `dbus`/`gi` bindings | LGPL-2.1+ | runtime dependency, not bundled |
| `lxc` userspace tools | LGPL-2.1+ | host package dependency |
| `python3` itself | PSF-2.0 | host package dependency |
| Mesa / Wayland / PulseAudio in the image | MIT / various | inside the Android image, see §2 |

None of these are *bundled* into the release package; they are declared as
host dependencies (see `debian/control`), which avoids any copyleft
triggering from static inclusion.

---

## 5. GitHub Actions & release publishing

- The workflow uses only official `actions/checkout`, `actions/setup-python`
  and the `softprops/action-gh-release` action, all standard and
  permissively licensed (MIT).
- GitHub's Terms of Service apply to the runner environment and release
  hosting; we do not upload anything that GitHub's ToS forbids (no malware,
  no copyrighted media we don't have rights to).
- Releases are tagged and published to the fork's own repository. Publishing
  to the *upstream* `waydroid/waydroid` repo would require upstream
  maintainer approval — the workflow targets the fork by default.

---

## 6. Summary of obligations our release packages must satisfy

1. **Ship `LICENSE`** (GPLv3) with the tooling — done by `make install`
   (the `LICENSE` file is part of the repo and lands in the install tree).
2. **Ship `NOTICE`** with third-party attribution: Apache-2.0 ndk_translation,
   LineageOS/AOSP images, the `supremegamers` prebuilt provenance, and the
   "no warranty" disclaimer — new, implemented in the packaging script.
3. **Ship `SHA256SUMS`** so every artifact (images, translation layer,
   tooling) can be integrity-checked — implemented in the packaging script.
4. **Link to sources** in release notes (LineageOS sources, Google
   ndk_translation source, upstream prebuilt archive).
5. **Never claim authorship** of upstream images or binaries; state their
   origin in the release notes.
6. **No warranty / no liability** statement in the release notes, matching
   GPLv3 §15–16.
