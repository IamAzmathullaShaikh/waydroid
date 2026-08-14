# Host prerequisites — notes for distro packagers

Users repeatedly hit the same two host-side prerequisites ("IP address:
UNKNOWN" and missing binder nodes). Packages can't configure the host, but
packagers can surface the requirements in post-install notes and make sure
the runtime dependencies are right.

## Binder nodes

Waydroid needs `/dev/binder`, `/dev/hwbinder` and `/dev/vndbinder`.
Kernels with binder built in (`CONFIG_ANDROID_BINDER_IPC=y`,
`CONFIG_ANDROID_BINDERFS=y`) don't create the nodes until binderfs is
mounted. Recommended packaging support:

- Ship a systemd-tmpfiles entry (e.g. `/usr/lib/tmpfiles.d/waydroid.conf`):

  ```
  d /dev/binderfs 0755 root root -
  L /dev/binder - - - - /dev/binderfs/binder
  L /dev/hwbinder - - - - /dev/binderfs/hwbinder
  L /dev/vndbinder - - - - /dev/binderfs/vndbinder
  ```

- Document the fstab line for the binderfs mount
  (`binder /dev/binderfs binder defaults 0 0`).

The `waydroid init` path already tries `modprobe binder_linux` and mounts
binderfs itself when needed (`tools/helpers/drivers.py`), so the tmpfiles
entry is a convenience, not a hard requirement.

## Firewall / default-deny hosts

The container's DHCP DISCOVER and the FORWARD path are dropped before
Waydroid's own rules run on hosts with a default-deny firewall (ufw,
firewalld with a strict policy). `waydroid status` then reports
`IP address: UNKNOWN`. There is nothing Waydroid can do from inside the
session; the host admin must allow traffic on the `waydroid0` bridge, e.g.
with ufw:

```
ufw allow in on waydroid0 to any port 53,67 proto udp
ufw allow in on waydroid0 to any port 53,67 proto tcp
ufw route allow in on waydroid0
ufw route allow out on waydroid0
```

## Network backend

`data/scripts/waydroid-net.sh` now defaults to **auto-detection**:
nftables when `nft` is present and no iptables tooling is installed,
otherwise iptables (preferring `iptables-legacy`). The Makefile's
`USE_NFTABLES=1` still forces nftables at install time.

- Packages that already depend on iptables (Debian does, via
  `debian/control`) get the iptables path — no change needed.
- nftables-only distros get the nftables path automatically — do **not**
  add an `iptables` dependency that the script no longer strictly needs.
- IPv6 NAT stays off by default; users enable it via the `LXC_IPV6_*`
  environment variables (see `docs/host-integration.md`).

## schedtune (Halium / Ubuntu Touch hosts)

On Halium hosts, Waydroid probes whether the host `schedtune` cgroup
supports nesting and unmounts it otherwise. This is runtime behavior with
no packaging impact, but bug reports about the warning ("Failed to unmount
/sys/fs/cgroup/schedtune") are expected on kernels without the nesting
patch — see the README's schedtune section for the troubleshooting flow.
