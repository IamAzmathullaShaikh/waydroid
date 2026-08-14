# Debugging app installs from Aurora Store on x86_64 Waydroid

Date: 2026-08-14 · Environment: x86_64 host, Waydroid 1.6.4 (fork installed over the
system 1.6.3), Android 13 / SDK 33 image (`/usr/share/waydroid-extra/images`, the
freshest OTA builds: system 2026-04-03, vendor 2026-04-28), real binderfs + Wayland.

Update 2026-08-14: after a fresh `make install` of the fork + `waydroid init -f`
re-init, the exact same behavior reproduces on the clean container — confirming the
diagnosis is image/ABI-level, not a stale-install artifact.

## Symptom

"Most apps fail to install from Aurora Store" — some install fine, most fail silently
(or with a generic "Installation failed" in Aurora).

## Root cause (confirmed)

The container has **no ARM support at all**:

```
$ adb shell getprop ro.product.cpu.abilist
x86_64,x86
$ adb shell getprop ro.dalvik.vm.native.bridge
0
```

Aurora Store (4.8.4, `primaryCpuAbi=x86_64`) downloads APKs from Google Play's CDN.
Most popular apps ship only **ARM native libraries** (`lib/arm64-v8a/`, `lib/armeabi-v7a/`).
With no `arm64-v8a` in the ABI list and no native bridge, Android's PackageManager refuses
to extract the native libs and fails the install with:

```
INSTALL_FAILED_NO_MATCHING_ABIS: Failed to extract native libraries, res=-113
```

Apps that are pure Java (no native libs) or that ship `x86_64` builds install fine —
which is why *some* apps work.

## Evidence

### Install-session history (`adb shell dumpsys package installer`)

```
Session 965424118:  mFinalStatus=-113  INSTALL_FAILED_NO_MATCHING_ABIS: Failed to extract native libraries, res=-113
Session 2120647823: mFinalStatus=-113  ... res=-113
Session 617097453:  mFinalStatus=-113  ... res=-113
Session 499792685:  mSessionApplied=true  mSessionFailed=false   ← the one success
```

### Logcat

```
D PackageInstallerSession: Marking session 230758616 as failed: INSTALL_FAILED_NO_MATCHING_ABIS: Failed to extract native libraries, res=-113
E PackageInstallerSession: Failed to verify session 230758616
```

### Controlled experiment (deterministic, locally built test APKs)

- ARM64-only APK (`lib/arm64-v8a/libarmonly.so`, signed, zipaligned): `adb install` →
  `INSTALL_FAILED_NO_MATCHING_ABIS` (`res=-113`). Never appears in `pm list packages`.
- Identical app rebuilt with `lib/x86_64/libarmonly.so`: installs cleanly,
  shows up in `app list`.

This matches Aurora's own troubleshooting wiki: the error means the downloaded APK's
architecture doesn't match the device.

## The real fix

Install **libndk_translation** (the ARM translation layer) — the fork's `arm-translation`
action does exactly this. It adds `arm64-v8a` to the effective ABI list so ARM apps both
install *and* run:

```bash
# needs root (the container D-Bus service runs as root; user-side commands don't)
sudo make install                                 # install the fork over /usr/lib/waydroid
sudo waydroid arm-translation install --source /path/to/libndk-artifacts
sudo waydroid container restart
waydroid app install <arm-only.apk>               # now succeeds
```

Artifacts: `system/lib64/libndk_translation.so`, `system/lib64/libndk_translation_proxy.so`,
`system/lib64/ndk_translation/libarm64.so` (Apache-2.0). Community sources: ChromeOS
"guybrush" firmware images or Android-x86 images (what `waydroid_script` uses).

## Workarounds until the translation layer is installed

1. **Check an APK's ABIs before installing** (no root needed):
   ```bash
   aapt2 dump badging app.apk | grep -E "native-code|package"
   # native-code: 'arm64-v8a'   → will fail on this box
   # native-code: 'x86_64' or no native-code line → installs fine
   ```
2. **Prefer F-Droid or pure-Java apps** — they install and run without any translation layer.
3. **Aurora → Settings → device spoofing**: pick an x86_64-capable profile so Play serves
   universal/x86 builds where they exist (partial fix — cannot create x86 builds that don't exist).

## Note on "fresh install with all fixes"

All of the fork's fixes (ServiceRunner hardening, dispatch guards, `@BINDIR@` substitution,
`arm-translation`, 1.6.4 batch) live in the **tooling**, not in the Android image.
The x86_64 Android 13 image is built and served on the OTA side (upstream
waydroid/waydroid#2229 tracks the Android 15/16 rebuild). A fresh install therefore means:
reinstall the fork's code + re-init the container with fresh images from
`waydroid init` — the image itself is unchanged by this fork.
