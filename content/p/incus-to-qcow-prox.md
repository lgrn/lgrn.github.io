---
title: 'Migrating VM from Incus to Proxmox (QCOW2)'
date: 2026-11-20T22:01:00+02:00
draft: false
tags:
  - sysadmin
  - proxmox
  - incus 
  - linux
---

Migrating a VM from Incus to Proxmox is relatively easy, this post will detail how a block device is exported to a QCOW2 file and attached to a VM.

## Incus 

Stop the VM and change the `volmode` so that the disk is still accessible when the VM (FOO) is powered off:

```sh
incus stop FOO
zfs list -t volume | grep FOO

# using the name shown
zfs get volmode hdd/incus/virtual-machines/FOO.block

# set it to "dev"
zfs set volmode=dev hdd/incus/virtual-machines/FOO.block
udevadm settle
```

Run `qemu-img` to read the block device directly and write to QCOW2 with compression (empty space is sparse by default):

```sh
qemu-img convert -p -f raw -O qcow2 -c -o compression_type=zstd \
/dev/zvol/hdd/incus/virtual-machines/FOO.block /mnt/disk/foo.qcow2
```

Note that `compression_type` only triggers compression for _this_ data, it will not compress future data going into the disk.

When it's done, you should have a `foo.qcow2` ready to use with proxmox.

## Proxmox 

In this case, an NFS storage is used. You can use `pvesm status` to list your configured storage.

Choose a suitable VMID. Begin by creating an UEFI boot VM with no disk, putting EFI disk on `nfs1`:

```sh
qm create 901 --name foo --memory 8192 --cores 4 --net0 virtio,bridge=vmbr0 \
  --bios ovmf --machine q35 --efidisk0 nfs1:1,efitype=4m,pre-enrolled-keys=0 \
  --scsihw virtio-scsi-single --ostype l26
```

Create an image-directory for your VM on the NFS share you wish to use, e.g:

```sh
mkdir -p /mnt/pve/nfs1/images/901
mv foo.qcow2 /mnt/pve/nfs1/images/901/vm-901-disk-1.qcow2
```

This magic naming means that you can trigger a rescan in Proxmox which will pick up the disk as "unconfigured":

```sh
qm rescan --vmid 901 # will find the disk
qm set 901 --scsi0 nfs1:901/vm-901-disk-1.qcow2 --boot order=scsi0
# if you wish, start it:
qm start 901
```

## Customization

Any customization you wish to make can be done either before exporting from Incus, or after directly against the QCOW file. For example, to reset the root password and install `qemu-guest-agent`, run this while the VM is powered off:

```sh
apt install libguestfs-tools
qm stop 901

virt-customize -a /mnt/pve/nfs1/images/901/vm-901-disk-1.qcow2 \
  --install qemu-guest-agent \
  --run-command 'systemctl enable qemu-guest-agent' \
  --root-password password:YOUR_PASSWORD_HERE

qm set 901 --agent enabled=1
qm start 901
```

Incus VMs usually use `systemd-networkd`, so you may need to fix `/etc/systemd/network/`.

## ZFS -> ZFS

**This entire section is untested.**

Incus obviously supports ZFS as well, so while I haven't tested it, it should be possible to do something like:

```sh   
zfs snapshot disk/incus/virtual-machines/FOO.block@MIGRATION
zfs send -v disk/incus/virtual-machines/immich.block@MIGRATION \|
    ssh pve_server zfs receive rpool/data/vm-901-disk-1
```

Then as before use `qm create` to create a VM with the same ID, followed by `qm rescan`. This carries the obvious benefits of, for example, keeping existing ZFS compression (if any), or the fact that you can lessen downtime by delta-sending the last part at the end.

Apparently, you can also run `virt-customize` directly against a block device, so that should be doable against a ZFS disk as well:

```sh
virt-customize -a /dev/zvol/rpool/data/vm-100-disk-1 (...)
```

Thoughts and feedback are welcome via
[@linus@mastodon.acc.sunet.se](https://mastodon.acc.sunet.se/@linus)
