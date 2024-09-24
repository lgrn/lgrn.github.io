---
title: 'Manual disk encryption on Ubuntu'
date: 2022-12-03T15:00:00+02:00
draft: false
tags:
  - sysadmin
  - linux
---

Ubuntu makes it very easy to set up full disk encryption, but it
requires you to wipe the entire disk if you want the wizard to do it for
you, so this is how you can set it up manually.

One common reason you may want to do this is in a dual boot scenario,
where one or several leading partitions are already taken -- or maybe
you simply want to keep whatever is there.

The option in the Ubuntu installer to _"Encrypt the new Ubuntu
installation for security"_ is only available when choosing _"Erase disk
and install Ubuntu"_. So, if you don't want to wipe the entire disk, but
you still want to boot an encrypted root partition, it needs some
preparation.

This also gives some useful insight into how the disk encryption is
actually set up behind the scenes.

In this guide we will:

- Set up the partitions we want manually using `sgdisk` -- but you can
  use `gparted` or similar if you prefer.
- Use `cryptsetup` to encrypt a partition
- Decrypt (open) and mount this encrypted device, and set up LVM within
  it
- Have Ubuntu run its installation against the unlocked partition, like
  any normal installation.
- Manually configure the new installation to prompt the user for a
  passphrase to unlock the device on boot

This may sound like a lot, but it's pretty straight forward.

This guide assumes that you already have, or that you will create, an
EFI system partition. This is outside the scope of the guide.

_Note: This post is heavily inspired by [this
post](https://www.mikekasberg.com/blog/2020/04/08/dual-boot-ubuntu-and-windows-with-encryption.html)
by Mike Kasberg._

### Graphical representation

```plain
| ### sda1 ### | ## sda2 ## | ######### sda3 ######### | -,
  ^-untouched    ^-/boot       ^- LUKS LVM (encrypted)    |
                                                          |
| ####################### sda3 ####################### | <´
| ## swap (lv) ## | ###########  root (lv) ########### |
```

### Introduction

In this example, `/dev/sda1` is taken and we do not want to remove it.
After `sda1`, there is free space available. You may very well have
multiple partitions "taken". If so, the partitions you create might be
`sda5`, or `sda6` etc.

### Partitions

First, create a `2G` partition for /boot (we're not encrypting this) on
`/dev/sda` as partition `2`, which is the next free partition number
available in this example where only `sda1` exists.

```bash
sgdisk --new=2:0:+2G /dev/sda
```

Let the next partition `3` fill the remaining space:

```bash
sgdisk --new=3:0:0 /dev/sda
```

Now set the name of `2` to /boot and `3` to rootfs

```bash
sgdisk --change-name=2:/boot --change-name=3:rootfs /dev/sda
```

Then set the typecode to 8300 on both (Linux filesystem)

```bash
sgdisk --typecode=2:8300 --typecode=3:8300 /dev/sda
```

At this point, we're going to use LUKS to encrypt what will later become
our root disk (`sda3`):

```bash
cryptsetup luksFormat --type=luks1 /dev/sda3
```

Then open it with the passphrase you chose and call it "root", or
whatever really:

```bash
cryptsetup open /dev/sda3 root
```

The naming `root` makes the unlocked device available at
`/dev/mapper/root`

### LVM

We can now treat this meta-device as a regular HDD and create a physical
volume for LVM as you would normally:

```bash
pvcreate /dev/mapper/root
```

Create a volume group, then one logical volume for swap, and use the
rest for our root partition.

```bash
vgcreate ubuntu-vg /dev/mapper/root
lvcreate -L 4G -n swap ubuntu-vg
lvcreate -l 100%FREE -n root ubuntu-vg
```

### Install Ubuntu

Since this encrypted device is already unlocked and LVM has been
prepared, we can use the normal GUI installation in Ubuntu to install
into it.

If you want to double check at this point, you can run `gparted` as root
which should show the partitions you just created.

Start the regular Ubuntu installation, select language, keyboard layout
etc. and then select "Something else" when asked about how you want to
install.

Here's what we'll do in the installation GUI:

- Edit `/dev/mapper/ubuntu--vg-root`, set to ext4 mounted at `/`, and format
  it.
- Edit `/dev/mapper/ubuntu--vg-swap`, set to swap area.
- Edit `/dev/sda2`, set to ext4 mounted at `/boot`, and format it.

Let the installation complete, but -- **do not** -- reboot or shut down
the installation (select "Continue Testing").

The reason we must keep the installation going is that the installation
wizard does not understand that it has actually installed Ubuntu into an
encrypted device, so we need to add some configuration to the
installation we just did while it's still open so that it will prompt
the user for the passphrase to decrypt it.

### chroot into the installation

We'll use `/target` for mounting our installed system:

```bash
mount /dev/mapper/ubuntu--vg-root /target
mount /dev/sda2 /target/boot
for n in proc sys dev etc/resolv.conf; do mount --rbind /$n /target/$n; done
```

Before jumping into it, we need to figure out the UUID (not PARTUUID) of
the encrypted partition (/dev/sda3). This can be found by running:

```bash
blkid /dev/sda3
```

Save this for later.

Since `/target` is now a usable environment, we can chroot to it:

```bash
chroot /target
mount -a
```

Now create and edit `/etc/crypttab` which likely does not exist and add
the name for the device, the device itself (by UUID, no quotes) and some
options:

```plain
root UUID=your_uuid_here none luks,discard
```

Save the file, then apply your changes by running:

```bash
update-initramfs -k all -c
```

This will re-generate your initrd images, and when done you're ready to
reboot. After the reboot, you should be greeted with a prompt asking you
for the passphrase to decrypt "root", and that's it!
