---
title: 'Flatcar Linux VM under Incus on Debian'
date: 2024-12-09T15:01:00+02:00
draft: false
tags:
  - sysadmin
  - linux
  - incus
  - docker
  - flatcar
---

Flatcar Linux is a fork of the now defunct CoreOS, specifically designed
to run container workloads. It has an immutable root file system and
automatic updates, and here's how you can run it as a VM under Incus.

Much like FreeBSD, no images are available for Flatcar:

```bash
incus image list images: flatcar
```

We'll install Flatcar in a similar hacky fashion to [this article]({{<
ref "freebsd-vm-incus" >}}), i.e. create an empty VM and `dd` directly
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
version: 1.1.0
kernel_arguments:
  should_exist:
    - flatcar.autologin
  should_not_exist:
    - quiet
passwd:
  users:
    - name: foo
      password_hash: '$6$7y.DFqCb(...)'
      ssh_authorized_keys:
        - ssh-ed25519 AAAAC3Nz(...)
      groups: ['sudo']
storage:
  files:
    - path: '/etc/systemd/network/00-eth0.network'
      overwrite: true
      contents:
        inline: |
          [Match]
          Name=eth0

          [Network]
          Address=10.200.147.72/26
          Gateway=10.200.147.65
          DNS=1.1.1.1
    - path: '/etc/sudoers.d/foo'
      overwrite: true
      mode: 0440
      contents:
        inline: |
          foo ALL=(ALL) NOPASSWD: ALL
systemd:
  units:
    - name: my.service
      enabled: true
      contents: |
        [Unit]
        Description=my service
        After=network.target

        [Service]
        ExecStart=/usr/local/bin/binary
        Restart=always

        [Install]
        WantedBy=multi-user.target
```

Check the config and fix any errors:

```bash
butane -c -s config.yaml
```

Pipe it through butane and put it somewhere Incus can read it:

```bash
cat config.yaml | butane -s -o /var/lib/incus/devices/flatcar/ignition.json
```

Now set the metadata key specific for flatcar directly with qemu so it
knows where to look for the file:

```bash
incus config set flatcar raw.qemu " -fw_cfg name=opt/com.coreos/config,file=/var/lib/incus/devices/flatcar/ignition.json"
```

Set whatever other values you may want with `incus config edit`:

```yaml
config:
  limits.cpu: "2"
  limits.memory: 2GiB
  security.secureboot: "false"
  (...)
```

Grab a file that tickles your fancy from
[/stable/amd64-usr/current/](https://stable.release.flatcar-linux.net/amd64-usr/current/?sort=size&order=desc):

```bash
curl -OL https://stable.release.flatcar-linux.net/amd64-usr/current/flatcar_production_image.bin.bz2
```

Find the block device for your running VM:

```bash
ls -alh /dev/zvol/default/virtual-machines/
```

Then write the image directly to it:

```bash
bzip2 -dc [image] | dd of=/dev/zvol/default/virtual-machines/foo.block bs=4M conv=fsync status=progress
```

When it's done, force stop and start the VM:

```bash
incus stop flatcar --force && incus start flatcar
```

You should now be able to SSH into the VM with the passwordless sudo-user and key
specified in the butane config.

For more information, see:

- [Getting Started with Flatcar Container Linux](https://www.flatcar.org/docs/latest/installing/)
