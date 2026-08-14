# TODO — status

Action items derived from the repository's bugs, patches, implementations,
and the live verification session (2026-08-14, x86_64 host running the fork
1.6.4 with libndk_translation installed).

## Recently completed

### ARM64 translation layer (the big one)

- **`waydroid arm-translation`** — install/status/uninstall action,
  root-gated via the DISPATCH table.
- **One-command install** — `waydroid arm-translation install` with no
  flags downloads the known-good community prebuilt
  (supremegamers/vendor_google_proprietary_ndk_translation-prebuilt,
  Android 13, 17.8 MB, md5-verified), auto-detects the `prebuilts/` tree,
  validates, installs. `--source/--archive/--url` still work.
- **Real artifact layout** — matches the actual prebuilt (`prebuilts/` →
  `/system` with `lib64/arm64/`, `lib/arm/`, `bin/arm{,64}`, `etc/init/
  ndk_translation.rc`, `etc/binfmt_misc/`, `etc/{cpuinfo,ld.config}.arm{,
  64}.txt`) instead of the previously assumed `ndk_translation/` tree that
  the real artifacts do not contain.
- **Overlay sync, not bind mounts** — the container's `/system` overlay is
  mounted read-only, so bind-mounting in failed silently. Artifacts are now
  copied into the overlay lowerdir (`overlay/system/`) at session start,
  before `mount_rootfs()` mounts it — the waydroid_script approach.
- **Exec bits preserved** — zipfile drops unix modes; `_extract_archive`
  restores them so binfmt_misc can run the translator binaries.
- **Full native-bridge prop set** — `make_base_props` writes
  `ro.dalvik.vm.native.bridge`, the emulated `ro.product.cpu.abilist*`
  (fixes both Play delivery and local `-113`), plus `ro.dalvik.vm.isa.arm{,
  64}` and `ro.enable.native.bridge.exec` (required by ART and the
  binfmt_misc registration). `[properties]` in waydroid.cfg still
  overrides.
- **Verified live** — ARM-only APK installs (was `INSTALL_FAILED_
  NO_MATCHING_ABIS`); a test app with a real AArch64 `.so`
  (`mov w0,#42; ret`) rendered its activity with
  `ndk_translation: Initialized NDK translation (aarch64)` in logcat.
- Tests: layout validation, nested `prebuilts/` source, default-URL +
  integrity check, overlay sync, exec-bit preservation, ABI prop
  advertising. Suite: **113 passed, 1 skipped**, ruff clean.

### Release packages (new)

- **`tools/release/package.py`** — builds a self-contained release package
  (tooling install tree + latest Android images + optional ARM64
  translation layer) with `install.sh`, `SHA256SUMS`, `LICENSE` and
  `NOTICE`.
- **Channel selection** — `official` (latest validated ota.waydro.id
  build, sha256-checked against the manifest) or `community-los22` /
  `community-los23` (latest matching WayDroid-ATV build; checksums
  computed and recorded since upstream publishes none). Verified live
  against both endpoints.
- **GitHub Actions** — `build-release.yaml`: weekly + manual dispatch
  (channel/arch/system_type/arm-translation/version inputs), runs
  `make check`, stages `make install DESTDIR`, builds the package,
  publishes it as a GitHub Release asset. Full LOS source builds (~300 GB,
  ~5 h) can't run on hosted runners, so it packages upstream images.
- **Licensing review** — `docs/LICENSING.md`: project GPL-3.0-or-later,
  debian BSD-3-clause, metainfo CC0/GPL, images LineageOS (Apache-2.0 /
  GPL-2.0 kernel), and the key finding: the `supremegamers` translation
  prebuilt declares NOASSERTION — mitigation: optional bundling + explicit
  NOTICE provenance + no-warranty statement.
- Tests: channel parsing (official/community/combined), sha256 integrity,
  image extraction, tarball layout, exec-bit checksums. Suite now
  **128 passed, 1 skipped**, ruff clean.

### Earlier batch (still in the tree)

- ServiceRunner + dispatch-derived root/init guards; `@BINDIR@` PREFIX
  substitution; LOS 13→16 (Android 13–16) doc/support update; 1.6.4
  hardening batch (schedtune retry, NFC/BT warnings, nftables auto-detect,
  IPv6 env vars, binder config migration, `_log_path`); E501 enforced at
  131; docs: `makefile-walkthrough.md`, `upstream.md`,
  `distro-packaging.md`, `aurora-install-debug.md`.

## Open — needs action

### 1. Aurora Store re-check-in verification (in progress)

- [ ] After `pm clear com.aurora.store`, confirm the fresh anonymous
      check-in now advertises `arm64-v8a` (read `PREFERENCE_AUTH_DATA`
      `Platforms` back from the container's Aurora prefs). Requires root;
      sudo was locked out at the end of the session.
- [ ] Install a previously-failing real app from Aurora Store end-to-end
      (delivery no longer `AppNotSupported`, install no longer `-113`).
- [ ] If still `AppNotSupported`: use Aurora device spoofing (Settings →
      Apps → ARM64 profile) to force a clean re-check-in, then re-test.
- [ ] Update `docs/aurora-install-debug.md` with the re-check-in outcome.

### 2. Real-device / community testing (can't be done on this box)

- [ ] Run a real ARM-only app (not the synthetic test APK) on this box
      under libndk_translation and note any crashes/quirks; feed findings
      back to the artifact source.
- [ ] schedtune probe retry + warning — validate on real Halium /
      Ubuntu-Touch hardware.
- [ ] Halium 15+ / AIDL gralloc5 detection — validate against actual
      Halium 15+ devices.
- [ ] Android 15/16 (LineageOS 22/23) images — when upstream
      waydroid/waydroid#2229 ships official images, test this fork's
      runtime detection against them.

### 3. Upstream / release

- [ ] Version-bump to 1.6.5 when the next release batch lands (changelog
      entry already tracks 1.6.4).
- [ ] `docs/upstream.md` triage: the arm-translation overlay-sync + prop
      set is PR-worthy for `waydroid/waydroid`; the `--url` default (third-
      party prebuilt) is fork-specific — decide whether to ship it
      upstream gated behind a flag.
- [x] `make check` now falls back to `uvx --from ruff/--from pytest`
      when the tools are missing from PATH (CI still installs them
      explicitly, which takes precedence).

### 4. Housekeeping

- [ ] Run the release workflow once on GitHub (dispatch) and sanity-check
      the produced package on a clean host before pointing users at it.
- [ ] Remove the leftover test APKs under `/tmp/armonly/` and `/tmp/armapp/`
      and the `armonly`/`armapp` packages from the running container
      (`adb uninstall`).
- [ ] Consider documenting the ARM translation overlay-sync design (why
      bind mounts can't work into a ro `/system`) in the module docstring
      — partially done in `arm_translation.py`; extend if needed.
- [ ] The sudo lockout experienced during verification: if reproducible,
      worth a note — repeated `sudo -S` with the same password should not
      lock out; check `pam_tally`/`faillock` config on this box.
