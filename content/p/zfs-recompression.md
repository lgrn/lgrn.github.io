---
title: 'Re-compressing ZFS datasets used by incus'
date: 2026-02-11T21:00:00+02:00
draft: false
tags:
  - zfs
  - incus
  - linux
  - sysadmin
---

If you have an existing ZFS dataset with no compression, enabling it will not
compress existing data. That makes sense if you think about it, but how can we
make it happen if we want to?

I started experimenting with this recently, so this article will focus on the
use case of a ZFS dataset used by an LXC container under incus, but it should be
generally useful for ZFS re-compression as well if you ignore the incus parts.
It may not be the best way to do it, and if it isn't, [please let me
know!](https://telegrafverket.cc/@linus)

If you're only interested in the ZFS parts, here's essentially what we'll be
doing:

```sh
# source dataset 'foo', create snapshot
zfs snapshot pool/foo@temp
# send snapshot without `-c`ompression to new 'temp'
zfs send -v pool/foo@temp |\
zfs receive -o compression=zstd-1 pool/temp
```

At this point, `pool/temp` is compressed and can either be used as-is, or if it
really needs to take the place of the old dataset, as is the case with incus, we
can delete (or rename) the old dataset and simply rename the new one to take its
place. 

## The incus parts

If we assume we have an LXC container in incus using `nvmepool/containers/foo`,
we can enable compression by simply doing something like:

```sh
zfs set compression=zstd-1 nvmepool/containers/foo
```

In some cases this is sufficient, but in order to compress existing data from
before this setting was changed, we need to re-write the data somehow. There are a
few ways we could go about this in incus-specific terms:

1. We could stop the instance, create a temporary storage in incus of type `dir`
   and then move the instance there. If we then change the default compression
   of the parent dataset `nvmepool/containers`, moving it back there again would
   then compress the data. This is **really** slow (I tried it), and it also
   requires the container to be stopped during the entire process.

1. We could copy the instance, which creates what's called a ZFS clone. It's
   very quick, because no new data is actually written. I considered trying to
   "force-write" the data from the clone back to the original dataset after
   changing the compression value, but this won't work because the "copy" is a
   dependent clone of the original dataset, so force-writing into the dataset
   makes no sense as it would destroy the data the clone itself is depending on. 

1. We handle it outside of incus with `zfs` commands and pray incus will accept
   the "rug-pull" performed under it. This is potentially dangerous, because
   incus keeps lots of metadata and state in its database, but as long as the
   dataset name remains what incus expects we should be fine (?)

In the end, what I settled on trying was the following:

```sh
zfs snapshot nvmepool/containers/foo@temp
```

This starts by creating a snapshot that incus doesn't know about on the zfs
level. This snapshotting as well as the sending below can be done safely while
the container is running. Let's send the data, importantly not with `-c` which
would make the data stream keep existing compression (if present), we don't want
that.

```sh
zfs send -v nvmepool/containers/foo@temp |\
zfs receive -o compression=zstd-1 nvmepool/containers/temp
```

When this is done, the new dataset `nvmepool/containers/temp` is compressed, but
it's completely free-floating and has nothing to do with incus or any running
container.

Using `incus copy`, we can create a new sacrificial container that we will
replace the storage for. Doing `copy` like this creates a zfs clone, which is
very fast. We also get to keep all the instance configuration. We only really
care about the incus metadata parts here, all backing storage will be replaced.

```sh
incus copy foo foo-new --instance-only
```

This means `nvmepool/containers/foo-new` now exists, but we want to replace the
backing storage with our new compressed `temp` dataset instead of it being a
clone of `foo`. Let's simply delete it and create a new dataset, sending over
the compressed (`-c`) data from `temp`:

```sh
# foo-new isn't started yet, delete its storage
zfs destroy -r nvmepool/containers/foo-new
# re-recreate the 'foo-new' storage
zfs send -v -c nvmepool/containers/temp@temp |\
zfs receive -o compression=zstd-1 nvmepool/containers/foo-new
```

Now let's shut down `foo` and start the new container and pray that incus does
not complain:

```sh
incus stop foo
incus start foo-new
```

Because we did `incus copy`, the new container `foo-new` should have kept things
like network configuration, so best-case it's all ready to go. If incus is the
DHCP server here, you may see the new container getting a new IP. To avoid this,
travel back in time and ensure your containers have a static IP set that is
outside of the `ipv4.dhcp.ranges` of the network, that way the IP configuration
should follow when you do `incus copy`. For example:

```sh
incus network set incusbr0 ipv4.dhcp.ranges 10.191.32.100-10.191.32.199
incus config device override foo-new eth0 ipv4.address=10.191.32.10
```

This way, `.100-.199` will be used for DHCP, and `foo-new` is assigned `.10`.
Since this address is not in the DHCP range, you avoid possible collisions.

We can now clean up if everything works as expected:

```sh
# delete the temporary dataset we compressed into
zfs destroy -r nvmepool/containers/temp
# if you wish, delete the old container
incus rm foo
```
