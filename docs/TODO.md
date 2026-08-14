# TODO — status

All action items derived from the repository's bugs, patches, and
implementations have been addressed in the 1.6.4 batch. This page records
what was done and what remains genuinely open (hardware-dependent
verification that cannot be done in this repository).

## Completed in 1.6.4

### Bugs

- **Activation paths follow `PREFIX`** — `systemd/waydroid-container.service`
  and `dbus/id.waydro.Container.service` are now `@BINDIR@` templates
  substituted at install time (`make install PREFIX=/usr/local` works).
  See `docs/makefile-walkthrough.md`.
- **schedtune lazy unmount** — `keep_schedtune_if_nestable` now retries the
  lazy unmount (3 attempts, 1s apart) before warning, and the warning points
  at the README troubleshooting section.
- **`enableNFC`/`enableBluetooth`** — the intentional no-ops now log at
  WARNING level when Android actually toggles them, so the limitation
  surfaces in `waydroid log` instead of being invisible at debug level.
- **nftables-only hosts** — `waydroid-net.sh` now defaults `LXC_USE_NFT` to
  `auto`: nftables when `nft` exists and no iptables tooling is installed;
  the Makefile's `USE_NFTABLES=1` still forces `"true"`.
- **IPv6 NAT** — the `LXC_IPV6_*` variables are now read from the
  environment (were hardcoded empty), enabling per-session IPv6 without
  editing the script; documented in `docs/host-integration.md`.
- **Binder config migration** — `upgrader.migration()` persists
  binder/vndbinder/hwbinder keys for installs older than 1.6.4, so the
  runtime fallback in `drivers.loadBinderNodes` is no longer needed every
  boot.
- **`waydroid log` path selection** — extracted `_log_path()` in
  `tools/__init__.py` and unit-tested the root-log preference / explicit
  `-l` precedence.

### Patches / release

- **Version 1.6.4** — `tools/config/__init__.py` and a new
  `debian/changelog` entry.
- **Upstream triage** — see `docs/upstream.md` (what to send to
  `waydroid/waydroid`, what stays fork-specific, housekeeping for PRs).
- **Halium 15+ / gralloc5 drift** — `get_vendor_type` hardened against
  non-numeric props (was a hard crash on `int()`), the AIDL protocol table
  was already pinned by tests (`tests/test_protocol.py`); image-dependent
  behavior is documented as a re-verify item in `docs/upstream.md`.

### Implementations — follow-ups

- **ServiceRunner stop ordering** — session stop quits all three service
  loops plus the main loop; covered by
  `test_session_stop_quits_all_service_loops`.
- **Test coverage** — new suites for LXC config generation, mount helpers,
  net lease parsing, upgrader migration, `get_vendor_type`,
  `get_session_defaults`, and `_log_path` (92 tests total).
- **Line length enforced** — `E501` removed from the ruff ignore list; all
  25 long lines wrapped to ≤131 columns.
- **`get_session_defaults()` env precedence** — pinned, including the
  `"None"` string behavior for unset env and the pulse fallback.
- **`set_permissions` split** — the 0660/0666 vendor-HAL vs app split was
  already unit-tested; hardware verification remains (below).
- **Distro prerequisites** — see `docs/distro-packaging.md` (binderfs
  tmpfiles/fstab, ufw rules, network backend, schedtune).
- **ARM64 translation layer** — new `waydroid arm-translation` action
  (install from `--source`/`--archive`/`--url`, status, uninstall) with
  session LXC bind mounts into the container `/system` and the
  `ro.dalvik.vm.native.bridge` prop in the generated base props; artifacts
  follow the container `/system` layout under
  `/var/lib/waydroid/arm-translation` (see `tools/helpers/arm_translation.py`
  and the README section).

## Still open (needs hardware / external action)

1. **schedtune on real Halium/Ubuntu-Touch kernels** — validate the retry
   and the keep/unmount decision on devices; the manual probe steps are in
   the README.
2. **`set_permissions` 0660/0666 split on real binderfs hardware** — confirm
   no HAL breaks with owner-only access on actual devices.
3. **Halium 15+ version detection and AIDL gralloc5 detection against
   current shipped images** — the code is verified against the API levels
   (protocol table pinned through API 36/Android 16; `get_vendor_type`
   hardened), but not against actual images. Official OTA images are still
   Android 13 (upstream issue #2229); community LineageOS 22/23 images are
   available for manual verification.
4. **NFC/Bluetooth data plane** — if container NFC/Bluetooth should ever
   control host hardware, that belongs in a session-scoped
   hardware-adaptation layer (currently documented no-ops).
5. **Distro outreach** — landing `docs/distro-packaging.md` content in
   docs.waydro.id and distro packaging notes.
