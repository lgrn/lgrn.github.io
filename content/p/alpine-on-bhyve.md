---
title: 'Alpine Linux VM cloud images on FreeBSD'
date: 2025-07-31T12:00:00+02:00
draft: false
tags:
  - sysadmin
  - freebsd
  - linux
  - cloud-init
---

You can get almost anything running on most hypervisors if you're OK
with mounting an ISO and running through an installation, but VM cloud
images are essential for repeat deployments, so I wanted to explore
what the support is like on FreeBSD. Turns out, it's not terrible.

I got interested in this after reading _[Creating an Alpine Linux VM on
bhyve](https://it-notes.dragas.net/2022/11/01/creating-an-alpine-vm-on-bhyve-with-root-on-zfs-optionally-encrypted/)_
(shout-out to Stefano Marinelli). Installing an operating system from an
ISO and then making it into a template of your own is completely valid,
especially if you're doing something exotic, but there are also many
use-cases for when you _really_ want vanilla cloud images that you can
easily update for new deployments, while still being able to
continuously apply some kind of semi-agnostic boostrapping on top of
them. So, this post will investigate how far you can get with Alpine
Linux cloud images that come prepared with `cloud-init` on a FreeBSD
host.

## The basics

This is being done on FreeBSD 14.3 with the `vm-bhyve` tool. Installing
it is not difficult, they have a short [quick-start
list](https://github.com/freebsd/vm-bhyve?tab=readme-ov-file#quick-start)
in their repo. I'm using ZFS with a pretty standard `zroot/vm` dataset
where everything (config and data) is stored.

In addition to `vm-bhyve` you also need:

- `grub2-bhyve` (for non-BSD virtual machines)
- `bhyve-firmware` (for UEFI boot)
- `qemu-tools` (to work with qemu files, unsurprisingly)

## Template

The `vm-bhyve` tool comes with templates, and there is one for Alpine
that I have never really had much luck with. In fact, most posts I've
seen have been about how it needs to be changed, and this one will be no
different. Turns out that no extra hacking is needed here, we can just
uefi boot the raw image. I'll create a new one called `alp.conf`:

```ini
loader="uefi"
cpu="2"
memory="2G"
network0_type="virtio-net"
network0_switch="public"
disk0_type="nvme"
disk0_name="disk0.img"
```

As someone who has spent an inordinate amount of time searching for
different configurations for Linux VMs on FreeBSD, this configuration is
almost suspicious in how simple it is, but it actually works.

## Image

Alpine cloud images can be fetched from <https://alpinelinux.org/cloud/>
-- the one we want is the `uefi • cloudinit • vm` of type `nocloud`.

Grab it in whatever way you prefer:

```sh
axel https://dl-cdn.alpinelinux.org/alpine/v3.22/releases/cloud/nocloud_alpine-3.22.1-x86_64-uefi-cloudinit-r0.qcow2
```

We won't be able to do much with a `qcow2` file here, so we need to
convert it to a raw disk file:

```sh
qemu-img convert -f qcow2 -O raw nocloud_alpine-3.22.1-x86_64-uefi-cloudinit-r0.qcow2 alpine.raw
```

Simply move `alpine.raw` into `.img` and `vm img` will show it.

## Deploy

To deploy using our template and image file, run:

```sh
vm create -t alp -i alpine.raw -C -k ~/.ssh/authorized_keys berg
```

This will deploy the VM "berg" with `t`emplate "alp", `i`mage
"alpine.raw", enabling `C`loud-init and passing SSH `k`eys from the
hosts "authorized_keys" file.

You can also pass `-n`, an example is given in the documentation, but we
won't be doing that:

```sh
-n "interface=;ip=;gateway=;nameservers=;searchdomains=;hostname="
```

When creating a VM, it will not be started automatically, and from the
perspective of cloud-init this is a very good thing. Before starting the
VM, let's inspect the VM dataset that was created:

```sh
# ls -alh /zroot/vm/berg
total 114748
(...)  .
(...)  ..
(...)  .cloud-init
(...)  berg.conf
(...)  disk0.img
(...)  seed.iso
(...)  vm-bhyve.log
```

To better understand what is happening here, let's go through what we
are looking at:

- `.cloud-init` is a folder containing YAML files like `user-data`,
  which you will recognize if you've worked with cloud-init in the past.
  These files are not, in strict terms, what is consumed by the VM,
  as this folder is concatenated first into:
- `seed.iso` by vm-bhyve, and if we look at:
- `berg.conf` we can see that our template configuration has been
  amended due to us adding `-C` with:

```ini
disk1_type="ahci-cd"
disk1_name="seed.iso"
disk1_dev="file"
```

In other words, the `seed.iso` file gets passed to the VM, where
cloud-init sneakily lies in wait to parse it on first boot.

What's interesting about this is that even though the vm-bhyve support
for cloud-init is rudimentary, there is nothing stopping us from just
creating our own ISO file before the VM starts for the first time.

Let's create a `vendor-data` file in the `.cloud-init` folder, being a
shell script instead of yaml:

```sh
#!/bin/sh
touch /home/alpine/VENDOR_SAYS_HELLO
```

...then in the "berg" directory just do manually [what vm-bhyve
does](https://github.com/churchers/vm-bhyve/blob/6e91ff54e7a00f2b57c77c930e7ccc5090f68ba6/lib/vm-core#L320) when it creates the iso:

```sh
makefs -t cd9660 -o R,L=cidata "seed.iso" ".cloud-init"
```

Now let's start up the VM for the first time with our modified ISO file:

```sh
vm start berg
```

From the console we can see the IP received over DHCP, and since we
passed the key we can SSH to it:

```sh
ssh alpine@192.168.1.120

$ ls -alh
total 4K
(...)  .
(...)  ..
(...)  .ash_history
(...)  .ssh
(...)  VENDOR_SAYS_HELLO
```

Nice!

## Potential use cases

Using what we have learned above, there are many exciting things you
could do in theory, since this opens up every possibility that
cloud-init offers.

If you have read previous posts of mine, you will know that my opinion
is that the so-called "vendor agnosticism" of cloud-init that in theory
should allow you to specify things like what gateway to use rarely are
very agnostic -- in the very basic sense they don't actually work and
will make you angry, sad, confused, and much more depending on how long
you take to give up and simply pass a shell script.

But since we can now pass a shell script, we could:

- Mass deploy virtual machines pre-configured with certain SSH keys or
  network configurations.
- In addition to bhyve-vm templates, also create "shell script
  templates" that actually install and configure software for us in a
  dynamic way.

If one could dream, it would be nice if vm-bhyve itself simply offered
the option to pass in complete cloud-init configuration and/or shell
scripts, but even if that never happens, the workaround above is good
enough for anyone with some scripting knowledge to build something cool.

Thoughts and feedback are welcome via
[@linus@telegrafverket.cc](https://telegrafverket.cc/@linus) -- email
works too.
