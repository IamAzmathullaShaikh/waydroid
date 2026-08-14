# Host integration mechanisms

When a session starts, the root container service
(`tools/actions/container_manager.py`) runs a series of host-side steps around
booting the container. This page covers the ones that reach into host
services and hardware — networking, sensors, and NFC. (The schedtune cgroup
handling is documented in the [README](README.md#schedtune-cgroup-handling).)

The container startup sequence, in order:

1. load the binder/ashmem drivers and set device permissions
2. run `data/scripts/waydroid-net.sh start` (networking, below)
3. launch `waydroid-sensord` if installed (sensors, below)
4. start Android init's `cgroup-lite` service if present (Halium hosts)
5. probe/keep the schedtune cgroup (see README)
6. generate the session LXC config, mount the rootfs, boot the container

## Networking — `waydroid-net.sh`

`data/scripts/waydroid-net.sh` gives the container its own private network:
`waydroid-net.sh start` at container start, `waydroid-net.sh stop` at stop.

It creates the `waydroid0` bridge (the name is read from the LXC config's
`lxc.net.0.link`, defaulting to `waydroid0`), assigns it `192.168.240.1/24`
with the LXC MAC `00:16:3e:00:00:01`, enables IPv4 forwarding, and starts a
hermetic `dnsmasq` serving DHCP (`192.168.240.2`–`.254`) and DNS on the
bridge. The dnsmasq is deliberately isolated from the host's
`/etc/dnsmasq.conf` (`--conf-file=/dev/null`) and runs as the first of
`lxc-dnsmasq`, `dnsmasq`, or `nobody` that exists.

Outbound access is provided through NAT:

- **iptables** by default — it prefers `iptables-legacy` when installed.
  Rules accept DHCP/DNS traffic on the bridge, ACCEPT forwarding, add a
  POSTROUTING MASQUERADE for `192.168.240.0/24`, and fix the DHCP reply
  checksum (mangle rule on port 68).
- **nftables** when `LXC_USE_NFT=true` — the Makefile's `USE_NFTABLES=1`
  flips this at install time. Equivalent ruleset in the `lxc` tables. When
  the variable is unset it defaults to `auto`: nftables is used only when
  `nft` is present and no iptables tooling is installed, so nftables-only
  hosts (minimal distros) work out of the box while hosts with iptables
  keep the legacy path.

The script is idempotent: `start` refuses to run if
`/run/waydroid-lxc/network_up` already exists (and force-stops a stale
bridge first), and `stop` tears down the rules, kills dnsmasq, and removes
the bridge unless interfaces are still attached.

### IPv6 NAT

IPv6 NAT is supported (`LXC_IPV6_*` variables) but disabled by default.
The script reads them from the environment, so it can be enabled per
session without editing the script:

```
LXC_IPV6_ADDR=fd00::1 LXC_IPV6_MASK=64 \
LXC_IPV6_NETWORK=fd00::/64 LXC_IPV6_NAT=true \
waydroid-net.sh start
```

When enabled, dnsmasq serves router-advertisements on the bridge
(`--dhcp-range=<addr>,ra-only`) and the NAT rules (iptables or nftables)
masquerade the container subnet. It stays off by default because adding
IPv6 to the bridge can surprise hosts with existing IPv6 setup (e.g.
`accept_dad` is disabled on the bridge by the script).

## Sensors — `waydroid-sensord`

If `waydroid-sensord` is installed, it is launched in the background at
container start with the hwbinder device node:

```
waydroid-sensord /dev/hwbinder
```

(`hwbinder` is the configured binder node, the same one the container's
Android services use.) Sensord is the host-side daemon that forwards the
device's sensors to Android inside the container over the shared hwbinder,
so apps get accelerometer/gyro/etc. data. At container stop, sensord is
looked up with `pidof` and killed. On regular desktops there is no sensord
binary and this step is a no-op.

## NFC — the removed nfcd hacks

Historically, `container_manager` stopped the host's `nfcd` daemon at
container start and restarted it at stop (via Android init's `stop`/`start`
commands, falling back to `systemctl`). The reason: on hosts that run
Android's nfcd (Ubuntu Touch / Halium), the host and container NFC daemons
would contend over the single NFC adapter, so the hack gave the container's
nfcd exclusive access for the session.

Those blocks were marked `#TODO: remove NFC hacks` and are now removed, so
the host nfcd is left untouched and Android's nfcd inside the container
manages the adapter on its own. Two consequences worth knowing:

- The `enableNFC`/`enableBluetooth` binder callbacks in
  `tools/services/hardware_manager.py` remain intentionally unimplemented
  (see their docstrings): this codebase has no data plane between the
  container's Android NFC stack and the host's NFC hardware, so toggling
  the host nfcd from the callback could not make NFC work in Android and
  would risk recreating the very contention the hacks prevented.
- On hosts that do run nfcd, NFC hardware access is no longer arbitrated
  between host and container — if both daemons are active, they may
  contend. If you observe that, the fix belongs in a session-scoped or
  hardware-adaptation layer, not in the removed stop/start hack.
