# Runbook — Longhorn node setup (per node, out-of-band)

> Prepares a Kubernetes node to run Longhorn v1.12.0. Run these steps on **every**
> node that will host Longhorn replicas — the single VPS today, and each new node
> at Phase 4. Like the lxcfs daemon and the SMTP relay unit (`k8s/deploy/node/`),
> node prep is hand-applied, not automated by CI.

Longhorn's V1 data engine needs `open-iscsi`, a clean device layer, and (ideally)
a dedicated disk. Skipping any of these is the top cause of field failures
(volumes stuck attaching, or `multipathd` stealing Longhorn's block devices).

## 1. iSCSI (required)

Longhorn attaches volumes over iSCSI; `iscsid` must be installed and running.

```bash
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y open-iscsi nfs-common
sudo systemctl enable --now iscsid
sudo modprobe iscsi_tcp
systemctl is-active iscsid          # -> active
```

`nfs-common` is only needed if you ever use RWX volumes (not today), but
installing it now avoids a second node visit.

> **k3s note:** modern k3s (≥ v0.10) uses the standard `/var/lib/kubelet`, which
> Longhorn auto-detects — no `csi.kubeletRootDir` override needed. Confirm with
> `ps aux | grep k3s` (look for a non-default `--data-dir`); only override if one
> is set.

## 2. Blacklist Longhorn devices from multipathd (required if multipathd runs)

`multipathd` can claim Longhorn's block devices and cause I/O errors. Blacklist them:

```bash
# /etc/multipath.conf
blacklist {
    devnode "^sd[a-z0-9]+"
}
```
```bash
sudo systemctl restart multipathd || true   # ok if multipathd isn't installed
```

## 3. Dedicated disk at /var/lib/longhorn (recommended)

Give Longhorn its own disk, not the root filesystem, so student data can't fill
the OS disk and vice-versa. On Azure, attach a **Premium SSD** managed disk
(~256 GiB / P15 to start — the disk tier is the main lever for the §6 benchmark;
grow to P20 when usage crosses ~60%). Then:

```bash
# Identify the new disk (e.g. /dev/sdc) — DO NOT format the wrong one.
lsblk
sudo mkfs.ext4 -m 0 /dev/sdc
sudo mkdir -p /var/lib/longhorn
# Mount by UUID for reboot-stability:
UUID=$(sudo blkid -s UUID -o value /dev/sdc)
echo "UUID=$UUID /var/lib/longhorn ext4 defaults,noatime 0 2" | sudo tee -a /etc/fstab
sudo mount -a
findmnt /var/lib/longhorn            # -> ext4 on the new disk
```

Sizing vs the workspace pool: commitments are thin-provisioned 20/50/100 GiB per
plan. Leave headroom for snapshots (weekly prune keeps 5 → budget ~1.5–2× active
bytes) plus the 25% minimal-available reserve Longhorn keeps free.

## 4. Environment check (required gate)

Run Longhorn's official pre-flight against this node. **Download and inspect, do
not `curl | bash`.**

```bash
curl -sSfLO https://raw.githubusercontent.com/longhorn/longhorn/v1.12.0/scripts/environment_check.sh
less environment_check.sh            # inspect
bash environment_check.sh            # expect all checks PASS
```

## 5. Capacity headroom (required gate)

Longhorn reserves ~12% CPU (guaranteed) + ~1 GiB RAM per node for its
instance-manager. Verify the node has room **before** installing:

```bash
kubectl top node                     # steady-state CPU should be < ~60%
```

If the node is already busy, resize the VPS first — Longhorn starving the
api-gateway/orchestrator would be worse than the storage problem it solves.

---

**Gate for Phase 0 complete:** `systemctl is-active iscsid` = active on every
node · `findmnt /var/lib/longhorn` shows the dedicated disk · environment check
all-green · `kubectl top node` has headroom. Then proceed to
`docs/runbooks/longhorn-install.md`.
