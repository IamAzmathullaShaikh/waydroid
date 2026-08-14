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

## Second failure mode: AppNotSupported (code=2) — Play delivery gate

Aurora can also fail with `AppNotSupported(code=2, reason=App not supported)`
from `PurchaseHelper.purchase` — this happens **before any APK downloads**
and is a different gate than the local `-113`:

```
AppNotSupported(code=2, reason=App not supported)
    at com.aurora.gplayapi.helpers.PurchaseHelper.purchase(...)
    at com.aurora.store.data.work.DownloadWorker(...)
```

**Mechanism:** Aurora presents the device profile stored in its auth data
(`com.aurora.store_preferences.xml`, `PREFERENCE_AUTH_DATA`):

```json
"Platforms": "x86_64,x86",
"Build.MODEL": "WayDroid x86_64 Device",
"Build.FINGERPRINT": "waydroid/lineage_waydroid_x86_64/..."
```

Google Play's delivery check reads the device's ABI list and **refuses to
serve** apps that have no x86 build — the APK never reaches the device.
Unlike `-113` (APK downloaded but ARM libs can't be extracted), this one is
rejected server-side.

### Why the fork's arm-translation now fixes BOTH gates

Original fork implementation only set `ro.dalvik.vm.native.bridge` — which
fixes local extraction but not Play's delivery gate, because the device still
advertised `x86_64,x86` only. Real native-bridge setups (ChromeOS, redroid)
also put the emulated ABIs in `ro.product.cpu.abilist`. The fork now does
that too (`tools/helpers/lxc.py:make_base_props`), so with the layer
installed the device advertises:

```
ro.dalvik.vm.native.bridge=libndk_translation.so
ro.product.cpu.abilist=x86_64,x86,arm64-v8a,armeabi-v7a,armeabi
ro.product.cpu.abilist64=x86_64,arm64-v8a
ro.product.cpu.abilist32=x86,armeabi-v7a,armeabi
```

After a container restart, Aurora re-checks in with the new profile
(`Platforms` now includes arm64-v8a) and Play delivers ARM-only apps;
the native bridge then runs them.

Aurora's own troubleshooting wiki confirms the fix direction: the error
means the device config's architecture doesn't match the app; the container
must advertise the ARM ABIs (or the user spoofs an ARM device profile in
Aurora — which only moves the failure to `-113` unless the translation
layer is also installed).

## Resolution: one-command install + verified ARM execution

`waydroid arm-translation install` now works with **no flags**: it fetches the
known-good community prebuilt (supremegamers/vendor_google_proprietary_
ndk_translation-prebuilt, Android 13, md5-verified), extracts it, validates
the /system tree, and writes the full native-bridge prop set. The artifacts
are synced into the container's /system overlay at session start (before the
overlay mounts — bind-mounting into the read-only /system fails silently),
which mirrors how waydroid_script does it.

Verified end-to-end on this box (2026-08-14):

```
$ sudo waydroid arm-translation install      # downloads 17.8 MB, md5-checked
$ waydroid container restart

# in the container:
ro.product.cpu.abilist  = x86_64,x86,arm64-v8a,armeabi-v7a,armeabi
ro.dalvik.vm.native.bridge = libndk_translation.so
ro.dalvik.vm.isa.arm64 = x86_64
binfmt_misc arm64_exe = enabled (magic 7f454c4602010100...0200b7)

$ adb install armonly.apk                     # previously -113 → Success
$ adb shell am start -n com.example.armapp/.MainActivity
08-14 09:14:45.992  1990  1990 I ndk_translation: Initialized NDK translation (aarch64), version 0.2.3
08-14 09:14:46.072  261  279 I ActivityTaskManager: Displayed com.example.armapp/.MainActivity: +100ms
```

The test app carried a real AArch64 `.so` (`mov w0, #42; ret`) loaded via
`System.loadLibrary`; its activity rendered, proving the ARM64 code actually
executed through libndk_translation (a missing layer crashes with
`UnsatisfiedLinkError` before onCreate). Aurora Store should now both serve
ARM-only apps (delivery gate fixed via abilist advertising) and install them
(-113 fixed via the native bridge).

## Note on "fresh install with all fixes"

All of the fork's fixes (ServiceRunner hardening, dispatch guards, `@BINDIR@` substitution,
`arm-translation`, 1.6.4 batch) live in the **tooling**, not in the Android image.
The x86_64 Android 13 image is built and served on the OTA side (upstream
waydroid/waydroid#2229 tracks the Android 15/16 rebuild). A fresh install therefore means:
reinstall the fork's code + re-init the container with fresh images from
`waydroid init` — the image itself is unchanged by this fork.
