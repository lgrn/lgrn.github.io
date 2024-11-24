---
title: 'FreeBSD VM under Incus on Debian'
date: 2024-11-24T11:45:00+02:00
draft: false
tags:
  - freebsd
  - sysadmin
  - linux
  - incus
---

Incus helps you manage both containers (LXC) and virtual machines
(QEMU), and while many images come prepared, FreeBSD is not one of them:
here's how to set it up.

This example assumes Incus on Debian with ZFS backed storage.

Normally you might do something like `incus image list images: | grep
bookworm` to find a suitable Debian Bookworm image for new deploys, but
if you look for any type of BSD you'll notice these are absent, in fact
there's not even an incus agent, so [the
recommendation](https://discuss.linuxcontainers.org/t/how-to-install-incus-agent-on-linux-vm/18874/2?u=baleygr)
is to simply use SSH.

We could [boot an
ISO](https://linuxcontainers.org/incus/docs/main/howto/instances_create/#launch-a-vm-that-boots-from-an-iso)
and install FreeBSD "normally", but since there are raw disk images
available, it would be quicker to just use these directly. You'll find
all kinds of images under
[VM-IMAGES/](https://download.freebsd.org/ftp/releases/VM-IMAGES/) -- I
will be grabbing the 14.2-RC1 with the UFS filesystem, since the backing
storage already runs ZFS. You could do this with `curl` or `wget`, but I
prefer `axel` since it provides parallel downloads.

```bash
axel -n 10 https://download.freebsd.org/ftp/releases/VM-IMAGES/14.2-RC1/amd64/Latest/FreeBSD-14.2-RC1-amd64-ufs.raw.xz
```

Then unpack it:

```bash
xz -d FreeBSD-14.2-RC1-amd64-ufs.raw.xz
```

When we create an empty VM, a related `block` device will automatically be
created with it, known to ZFS as `default/virtual-machines/freebsd`.

```bash
incus init freebsd --empty --vm
```

Before starting it up, let's prepare all the config:

```bash
incus config edit freebsd
```

Some suggestions on what to add:

```yaml
# cpu and memory limits
config:
(...)
  security.secureboot: 'false'
  limits.cpu: 2
  limits.memory: 2GB
```

```yaml
devices:
  root:
    path: /
    pool: default
    type: disk
    size: 20GB
  vtnet0:
    name: vtnet0
    network: macvlan
    type: nic
```

At this point, we should also remove the `default` profile from the VM
to stop the `eth0` default DHCP device from being added:

```bash
incus profile remove freebsd default
```

You can now inspect the full config, including additions from profiles:

```bash
incus config show freebsd -e
```

Now, this ZFS block device is, of course, empty -- but if we start the VM, it
will be available as an `zd` device (the device will not show up when
the VM is powered off):

```bash
incus start freebsd
```

```bash
ls -alh /dev/zvol/default/virtual-machines/
(...)
lrwxrwxrwx 1 root root 13 Nov 23 20:18 freebsd.block -> ../../../zd16
```

```bash
lsblk
NAME   MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
(...)
zd16   230:16   0  18.6G  0 disk
```

All we have to do is write the raw data directly to the (quite
importantly, correct) device:

```bash
dd if=FreeBSD-14.2-RC1-amd64-ufs.raw of=/dev/zd16 bs=4M status=progress
```

Let's see if it actually boots You can get a console immediately with:

```bash
incus stop freebsd --force
incus start freebsd --console
```

Or, if the VM is already running, use `incus console freebsd --type=console`

````plain
   ______               ____   _____ _____
  |  ____|             |  _ \ / ____|  __ \
  | |___ _ __ ___  ___ | |_) | (___ | |  | |
  |  ___| '__/ _ \/ _ \|  _ < \___ \| |  | |
  | |   | | |  __/  __/| |_) |____) | |__| |
  | |   | | |    |    ||     |      |      |
  |_|   |_|  \___|\___||____/|_____/|_____/      ```                        `
                                                s` `.....---.......--.```   -/
 ╔══════════ Welcome to FreeBSD ═══════════╗    +o   .--`         /y:`      +.
 ║                                         ║     yo`:.            :o      `+-
 ║  1. Boot Multi user [Enter]             ║      y/               -/`   -o/
 ║  2. Boot Single user                    ║     .-                  ::/sy+:.
 ║  3. Escape to loader prompt             ║     /                     `--  /
 ║  4. Reboot                              ║    `:                          :`
 ║  5. Cons: Dual (Video primary)          ║    `:                          :`
 ║                                         ║     /                          /
 ║  Options:                               ║     .-                        -.
 ║  6. Kernel: default/kernel (1 of 1)     ║      --                      -.
 ║  7. Boot Options                        ║       `:`                  `:`
 ║                                         ║         .--             `--.
 ║                                         ║            .---.....----.
 ╚═════════════════════════════════════════╝
   Autoboot in 2 seconds. [Space] to pause
````

Nice!

The reason we use `macvlan` is that FreeBSD seems to have issues with
the default Incus DHCP configuration through `incusbr0`.

According to [this
thread](https://discuss.linuxcontainers.org/t/no-ipv4-address-for-freebsd-vm/21083),
it seems like the issue goes away if you disable TCP segmentation
offloading (TSO) on the `incusbr0` interface on the host:

```bash
ethtool --offload incusbr0 tx off
```

I haven't tried this though, and in my case I don't mind simply changing
the network type.

At this point, within the VM, you may want to check if your file system
is actually using the entire disk. The easiest way is probably to just
run `gpart show da0` and check for any "free" space at the end.

To provoke the issue, I've increased it to `40GB`:

```sh
# gpart show da0
=>      34  78124957  da0  GPT  (37G)
        34       122    1  freebsd-boot  (61K)
       156     66584    2  efi  (33M)
     66740   2097152    3  freebsd-swap  (1.0G)
   2163892  36898596    4  freebsd-ufs  (18G)
  39062488  39062503       - free -  (19G)
```

Let's grow partition `4`, then the file system:

```sh
gpart resize -i 4 da0
growfs /
```

This is a good time to install whatever base software you want before
creating an image:

```sh
pkg install nano
# :-)
```

Anyway, `poweroff` and then do the following to create an image:

```bash
incus publish freebsd
```

If you look at running processes, you'll
see that what it actually does is something like:

```bash
qemu-img convert -p -f raw -O qcow2 -c -T none -t none /dev/zvol/default/virtual-machines/freebsd.block /var/lib/incus/images/incus_export_2111142778/rootfs.img
```

When it's done, you can run `incus image list` to see it, and it's short
fingerprint. Let's give it a creative name:

```bash
incus image alias create freebsd-image e7b39b8c341b
```

Let's try spinning up a new VM from it:

```bash
incus init freebsd-image cheese-burger --vm
```

Of course, it's a bit annoying that we again have to fix the disk and
NIC configuration manually, but that's easy, just pass in the YML you
want to use when running init, for example:

```bash
incus rm cheese-burger --force
incus init freebsd-image cheese-burger --vm < freebsd.yml
```

Where the file contains:

```yaml
architecture: x86_64
config:
  limits.cpu: '2'
  limits.memory: 2GB
  security.secureboot: 'false'
devices:
  root:
    path: /
    pool: default
    size: 40GB
    type: disk
  vtnet0:
    name: vtnet0
    network: macvlan
    type: nic
profiles: []
```

The first init may be a bit slow, but they'll be much faster once the
initial move into the data pool is completed, which means you can also
find it by its fingerprint:

```bash
zfs list | grep e7b39b8c341b
default/images/e7b39b8c341b8daee19064a6a9aab0ad23ba5247d6f9f4421de36405fafede01                24.5K   500M     24.5K  legacy
default/images/e7b39b8c341b8daee19064a6a9aab0ad23ba5247d6f9f4421de36405fafede01.block          1.96G   241G     1.96G  -
```

You might notice that the `default` profile is still applied. It's a bit
hacky, but one way to get around this is to create an empty profile and
apply that instead:

```bash
incus profile create no-profile
incus rm cheese-burger --force
incus init freebsd-image cheese-burger --vm -p no-profile < freebsd.yml
```

In summary, we have:

- Created an empty VM
- Written raw data to the VM block device
- Reconfigured the VM
- Created an image to be used for future VM deployments
- Prepared an empty `no-profile` and a `.yml` file.

Have fun deploying FreeBSD on Incus!
