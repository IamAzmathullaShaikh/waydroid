# Upstreaming plan

This repo (a Waydroid fork) carries a batch of work on top of upstream
`waydroid/waydroid` 1.6.3. This page triages what is worth proposing
upstream, what should stay fork-specific, and the housekeeping needed
before opening PRs.

## The batch

Recent commits (newest first):

| Commit | Summary | Verdict |
| --- | --- | --- |
| `6827900` | ServiceRunner + DISPATCH table, harden set_permissions, README host prerequisites | **Split before upstreaming**: ServiceRunner and the dispatch refactor are upstream-worthy; the README additions are fine as an upstream PR too, but the commit is too big — split into (1) ServiceRunner, (2) dispatch table + derived guards, (3) set_permissions modes. |
| `bc83cda` | `get_session_defaults()` factory, fix upgrade images path | **Upstream-worthy** as-is (the images_path `AttributeError` fix is a real bug). |
| `20305f1` | Networking/sensors helpers, `make check` | **Upstream-worthy**; `make check` mirrors their CI and should be easy to accept. |
| `fdd0b5d` | `-l/--log` fix, binder config fallbacks, sensord multi-pid kill | **Upstream-worthy** — all three are genuine bug fixes. |
| `94173b9` | Binder settings transaction fix, container control hardening, tests, docs | **Split**: the TRANSACTION_settingsGetInt fix and the Stop/Freeze/Unfreeze session-owner validation are upstream-worthy; the schedtune probe and cgroup-lite helpers may overlap with upstream's own schedtune handling — check first. |

## Fork-specific (do NOT send upstream as-is)

- **`docs/makefile-walkthrough.md`, `docs/TODO.md`, `docs/distro-packaging.md`** —
  fork-internal documentation.
- **`docs/host-integration.md` and the README sections about the schedtune
  probe / ufw rules / binderfs** — upstream maintains its own README and
  documentation site; port the *content* into an upstream PR rather than
  the files.
- **`debian/changelog` 1.6.4 entry** — rewritten for this fork's release;
  upstream will write their own.
- **Codebuff commit footer** (`🤖 Generated with Codebuff` /
  `Co-Authored-By: Codebuff`) — strip when preparing upstream commits.

## Housekeeping before opening PRs

1. Rebase onto upstream `main` (this fork's history diverged around 1.6.3).
2. Split `6827900` and `94173b9` along the lines above.
3. Drop the Codebuff footer and keep upstream's commit-message style
   (imperative, `area:` prefix).
4. Verify the schedtune probe doesn't conflict with upstream's schedtune
   handling (upstream historically unmounts schedtune; this fork keeps it
   when nestable).
5. Confirm the test suite dependencies: upstream CI would need
   `pip install ruff pytest` (the `make check` target and
   `.github/workflows/check.yaml` already assume this).

## Drift risks to re-verify at PR time

Current image status: the official OTA images are still Android 13
(LineageOS 20), while community builds at LineageOS 22/23 (Android 15/16)
exist (upstream issue #2229 tracks the official rebuild). The code paths
below are verified against the API levels, not the images themselves:

- **Protocol table** (`set_aidl_version` in `tools/helpers/protocol.py`):
  pinned by tests for API 27–40, including Android 16 (API 36+) using
  aidl6 for the service manager.
- **Halium 15+ version detection** (`get_vendor_type` in
  `tools/actions/initializer.py`): uses `ro.vndk.version` with a
  `ro.vendor.build.version.sdk` fallback; hardened against non-numeric
  props. Re-check the prop values on current Halium images.
- **AIDL gralloc5 detection** (`make_base_props` in `tools/helpers/lxc.py`):
  matches `android.hardware.graphics.allocator.IAllocator/default` on the
  vendor binder — the standard for Android 15/16 vendor images. Re-check
  against current LineageOS/Halium vendor images.
- **`ro.vendor.arm.egl.*` prop forwarding**: needed for newer Mali devices;
  confirm it doesn't leak unwanted host props into the container.
