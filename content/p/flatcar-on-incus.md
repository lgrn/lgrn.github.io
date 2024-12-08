---
title: 'Flatcar Linux VM under Incus on Debian'
date: 2024-12-08T11:45:00+02:00
draft: false
tags:
  - sysadmin
  - linux
  - incus
  - docker
  - flatcar
---

Flatcar Linux is a fork of CoreOS, specifically designed to run
container workloads. It has an immutable root file system and automatic
updates, here's how you can run it as a VM under Incus.

Much like FreeBSD, no images are available for Flatcar:

```bash
incus image list images: flatcar
```

We'll install Flatcar in a similar hacky fashion to [this article]({{< ref "freebsd-vm-incus" >}}), i.e. create an empty VM and `dd` directly
to the block device.

Let's start by creating an empty VM:

```bash
incus launch flatcar --empty --vm
```

We should grab `butane`, which is what Flatcar
uses to transpile the initialization files passed to the VM. These are
kind of like cloud-init, except they run earlier and allow you to
configure more low-level stuff (like what filesystem to use).

Grab the latest release of Butane [from the release
page](https://github.com/coreos/butane/releases), make it executable and
put it in `/usr/bin` (or wherever in your path you want it).

Now, create a simple `config.yaml` for butane to parse:

```yaml
variant: flatcar
version: 1.0.0
passwd:
  users:
    - name: your_name
      ssh_authorized_keys:
        - ssh-ed25519 AAAA(...)
      groups: ['sudo']
storage:
  filesystems:
    - device: /dev/disk/by-partlabel/ROOT
      format: btrfs
      wipe_filesystem: true
      label: ROOT
  files:
    - path: /etc/sudoers.d/username
      mode: 0440
      contents:
        inline: |
          your_name ALL=(ALL) NOPASSWD: ALL
```

Pipe it through butane and put it somewhere Incus can read it:

```bash
cat config.yaml | butane | tee /var/lib/incus/devices/flatcar/ignition.json
```

Now set the metadata key specific for flatcar directly with qemu so it
knows where to look for the file:

```bash
incus config set flatcar raw.qemu " -fw_cfg name=opt/com.coreos/config,file=/var/lib/incus/devices/flatcar/ignition.json"
```

Grab a file that tickles your fancy from
[/stable/amd64-usr/current/](https://stable.release.flatcar-linux.net/amd64-usr/current/?sort=size&order=desc):

```bash
curl -OL https://stable.release.flatcar-linux.net/amd64-usr/current/flatcar_production_qemu_uefi_image.img.bz2
```

Find the block device for your running VM:

```bash
ls -alh /dev/zvol/default/virtual-machines/
```

Then write the image directly to it:

```bash
bzip2 -dc flatcar_production_qemu_uefi_image.img.bz2 | dd of=/dev/zd16 bs=4M conv=fsync status=progress
```

When it's done, force stop and start the VM:

```bash
incus stop flatcar --force && incus start flatcar
```

You should now be able to SSH into the VM with the passwordless sudo-user and key
specified in the butane config.

For more information, see:

- [Getting Started with Flatcar Container Linux](https://www.flatcar.org/docs/latest/installing/)