---
title: "Using signed-by in repository configuration"
date: 2023-09-19T10:22:00+02:00
draft: true
tags:
    - linux
    - debian
    - ubuntu
    - sysadmin
---

On newer versions of Debian and Ubuntu, the way repos are authenticated
through public keys has changed somewhat. Here's what I've found.

You may recognize the command `apt-key`: this is a now deprecated
command that was previously used to add a trusted key to the keyring at
`/etc/apt/trusted.gpg`. This is not great, as the same keys are
considered valid for any repo you add.

This can (and on newer versions, must be) resolved by using `signed-by`
when configuring a repo. That way, only packages from that repository
will be considered valid when signed by the specified key.

### Configuration examples

```
# OLD WAY
deb https://my.repository.com/debian distribution component
```

When adding a new repository, you would typically curl and pipe the a
keyfile to `apt-key add`, which would add it to `trusted.gpg`, making it
a trusted key for every configured repo.

```
# NEW WAY
deb [signed-by=/path/to/key.gpg] https://my.repository.com/debian distribution component
```

In this example, keys in `key.gpg` are only considered valid for that
specific repository.

### When it might cause issues

This will normally not cause problems, as both the keys and the correct
configuration (hopefully) comes as part of your default installation.
However, when migrating between major versions, or when adding new
repositories, you may encounter warnings with the "old" configuration.

A short demonstration: if you run `apt-get update` with no pubkeys
available at all, a situation you could provoke by for example gzipping
`trusted.gpg`, you will get an error similar to the following:

```
The following signatures couldn't be verified because the public key is not available: NO_PUBKEY 9165938D90FDDD2E
```

It's pretty obvious from the error that `9165938D90FDDD2E` is a public
key, but we don't have it so we can't proceed.

First of all, what is this string? The answer is that it's an
abbreviated *fingerprint* of a public key. You can get these from `gpg`.
For now, let's ignore how we know which file it's in:

```
# gpg --show-keys --with-fingerprint --keyid-format long raspbian-archive-keyring.gpg | grep 9165938D90FDDD2E -A1

pub   rsa2048/9165938D90FDDD2E 2012-04-01 [SC]
      Key fingerprint = A0DA 38D0 D76E 8B5D 6388  7281 9165 938D 90FD DD2E
```

On the first line of the output you can see the pubkey fingerprint, with
a `keyid-format` of `long` matching the error message. Notice how this
is actually the four last parts of the entire fingerprint (and `short`
would only give us the last two: `90FDDD2E`).

Tangent: using the `short` format is [violently
insecure](https://security.stackexchange.com/questions/84280/short-openpgp-key-ids-are-insecure-how-to-configure-gnupg-to-use-long-key-ids-i),
as it only "takes 4 seconds to generate a colliding 32bit key id on a
GPU" (2020).

Ok, so now that we know what this string represents, the next question
might be how we know that this is the right key. If the repository is
accessed over HTTPS at least we know it's what the repo gave us, because
a man-in-the-middle attack is pretty unlikely.

How do we know that the repo key hasn't been compromised? We could look
for the key in other places, for example by searching for it online. In
this case, the repo itself has the key listed on a web page with
instructions on how to add the repo, as well as a link to where you can
find the key.

Finding the key isn't usually the issue, it's even registered at this
public key server:

https://keys.openpgp.org/search?q=9165938D90FDDD2E

It's more important to ensure that this key is legit, and for now we'll
assume that a guide that has been around for years served over HTTPS
from the official repository page is proof enough.

On Debian, keys are provided through the `debian-keyring` package,
which will put them in `/usr/share/keyrings`. On Raspberry Pi OS, there
are two packages available: `raspbian-archive-keyring` and
`raspberrypi-archive-keyring`, which will put keys in the same folder.

The first `raspbian` package is what provides the file we inspected previously:

```
# dpkg-query -L raspbian-archive-keyring | grep "\.gpg"
/usr/share/keyrings/raspbian-archive-keyring.gpg
```

So if we already have this file on disk, we can use that for our repo,
since we now feel pretty confident that is the key that we expect
packages from there to be signed with:

```
deb [signed-by=/usr/share/keyrings/raspbian-archive-keyring.gpg] https://archive.raspbian.org/raspbian bookworm main contrib non-free rpi
```

But for the sake of learning, let's pretend we did not have this key
available locally, how do we get it from the Internet and use it?

The instructions from raspbian illustrate perfectly the "old" way of
doing things:

```
# OLD REPO SYNTAX
deb http://archive.raspbian.org/raspbian wheezy main contrib non-free
```
Adding the key
```
# DEPRECATED
wget https://archive.raspbian.org/raspbian.public.key -O - | sudo apt-key add -
```

What we really want is to grab that file, make it into a `.gpg` file and
use it with the new syntax.

First, let's just inspect it and make sure it's the key we're looking
for:

```
$ curl --silent https://archive.raspbian.org/raspbian.public.key | gpg --show-keys --fingerprint --keyid-format long
pub   rsa2048/9165938D90FDDD2E 2012-04-01 [SC]
      Key fingerprint = A0DA 38D0 D76E 8B5D 6388  7281 9165 938D 90FD DD2E
(...)
```

Since this looks fine, we can now grab it and perform "dearmoring", which really
only means to convert it from ASCII to binary (the inverse is called
"enarmoring"). The ASCII form of a key is probably familiar to you:

```
$ curl --silent https://archive.raspbian.org/raspbian.public.key | head -n5
-----BEGIN PGP PUBLIC KEY BLOCK-----
Version: GnuPG v1.4.12 (GNU/Linux)

mQENBE94wmkBCADPW5ga8ZyIsW0pym3c+o7l/N1ipRfs2+9HaEWeyPZS6wdTdSp3
Wo0OOv3rGQDGclbvsrMZoJFzxfsADoMfPkToWg+pY4w3xkjZt4Mh7gO/kDsaOMDz
```

In order to dearmor and place this key somewhere, we can run:

```
# curl --silent https://archive.raspbian.org/raspbian.public.key | gpg --dearmor > /usr/share/keyrings/raspbian.public.gpg
```

This binary representation of the key can now be used when specifying
`signed-by` for a repo.

In summary:

- Packages in repos should be `signed-by` specific keys, not just any
  key that's ever been added.
- If a repo does not have the `signed-by` attribute, you may get
  warnings. It's a good idea to fix your configuration.
- If you lack public keys completely, it breaks `apt-get`
- What public keys are trusted is completely up to you, so exercise
  caution.

Final notes:

- Remember that any repo can still update any package. To avoid this,
  see: 
  "[Prevent/selective installation from a third-party
  repository](https://wiki.debian.org/AptConfiguration#Prevent.2Fselective_installation_from_a_third-party_repository)"
