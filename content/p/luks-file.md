---
title: 'Encrypted LUKS file container'
date: 2022-10-28T15:59:51+02:00
draft: false
tags:
  - linux
---

While [Linux Unified Key Setup](https://en.wikipedia.org/wiki/Linux_Unified_Key_Setup) &mdash; `LUKS` &mdash; is mostly used to encrypt entire disks under Linux, it can also be used to easily create an encrypted file container. This can be used as an alternative to encrypting something like a `.tar.gz` file directly, and will be easier to mount and read, without having to write decrypted data to disk.

### Creating a container

The first step is to quite simply reserve disk space for the container by creating an empty file:

```
dd if=/dev/zero of=container.luks bs=1 count=0 seek=2G
```

This tells input file `/dev/zero` to write `2G` of its output (zeroes) to `container.luks`.

While it's possible to use a [keyfile](https://en.wikipedia.org/wiki/Keyfile) for the encryption, in this example we will use a passphrase.

Formatting this file as a `LUKS` container is easy:

```
$ cryptsetup -y -v luksFormat container.luks

WARNING!
========
This will overwrite data on container.luks irrevocably.

Are you sure? (Type 'yes' in capital letters): YES
Enter passphrase for container.luks:
Verify passphrase:
Key slot 0 created.
Command successful.
```

The next step is to mount this file as a device, which requires us to be root.

```
sudo cryptsetup luksOpen container.luks container
```

This container is now available as a device (symlink) under `/dev/mapper`, but since it's completely empty we need to format it with a filesystem. You can probably use any filesystem you prefer, but in this case we'll go for `ext4`:

```
$ sudo mkfs.ext4 /dev/mapper/container
mke2fs 1.46.5 (30-Dec-2021)
Creating filesystem with 520192 4k blocks and 130048 inodes
(...)
Writing superblocks and filesystem accounting information: done
```

The device is now formatted and ready to use.

### Mounting

You can either rely on the auto-mount, typically this will make the encrypted container available after running `luksOpen` at a path like:

```
/run/media/your_name/g-u-i-d
```

The easiest way to get to this is to open your file explorer, as it will usually show in the left hand column.

If you want to mount it somewhere else however, you first need to make sure that path exists.

```
mkdir /mnt/container
```

If `luksOpen` has completed, the device is available to mount as `root`.

```
sudo mount /dev/mapper/container /mnt/container
```

Since manual mounting happens as `root`, we need to fix our permissions. This sets `$ME` to the current user, and sets ownerships with that variable:

```
ME="$(whoami)" && sudo chown -Rv $ME:$ME /mnt/container
```

When you're done with the container, simply unmount it and use `luksClose`:

```
sudo umount /dev/mapper/container && sudo cryptsetup luksClose container
```
