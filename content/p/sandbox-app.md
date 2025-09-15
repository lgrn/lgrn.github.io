---
title: 'Sandboxing Linux applications with firejail'
date: 2025-09-14T22:00:00+02:00
draft: false
tags:
  - sysadmin
  - linux
  - gnome
---

If you have an application that you know should never need to access
anything outside its own folder, sandboxing with firejail is both easy
and a useful way to increase your security posture.

> Firejail is a SUID security sandbox program that reduces the risk of
> security breaches by restricting the running environment of untrusted
> applications using Linux namespaces and seccomp-bpf. It allows a
> process and all its descendants to have their own private view of the
> globally shared kernel resources, such as the network stack, process
> table, mount table.

On Debian, you first need to install firejail:

```sh
apt install firejail
```

You can then simply preface your commands with `firejail` and some flags
of your choice. The [man
page](https://www.man7.org/linux/man-pages/man1/Firejail.1.html) gives
some useful examples, here are some that I use with descriptions:

{{< code language="plain" title="some useful flags" id="1" expand="Show"
collapse="Hide" isCollapsed="true" >}}
--caps.drop=all

Drop all capabilities for the processes running in the
sandbox. This option is recommended for running GUI
programs or any other program that doesn't require root
privileges. It is a must-have option for sandboxing
untrusted programs installed from unofficial sources - such
as games, Java programs, etc.

--net=none

Enable a new, unconnected network namespace. The only
interface available in the new namespace is a new loopback
interface (lo). Use this option to deny network access to
programs that don't really need network access.

--seccomp
Enable seccomp filter and blacklist the syscalls in the
default list, which is @default-nodebuggers unless --allow-
debuggers is specified, then it is @default.

--private
Mount new /root and /home/user directories in temporary
filesystems. All modifications are discarded when the
sandbox is closed.

--whitelist=dirname_or_filename
Whitelist directory or file. A temporary file system is
mounted on the top directory, and the whitelisted files are
mount-binded inside. Modifications to whitelisted files are
persistent, everything else is discarded when the sandbox
is closed.

--cpu=cpu-number,cpu-number,cpu-number
Set CPU affinity.
{{< /code >}}

An invocation might therefore look like:

```bash
firejail --caps.drop=all --net=none --seccomp --private \
--cpu=0,1,2 --whitelist=/mnt/disk/app/ \
/mnt/disk/app/run.sh
```

If you use GNOME and you want to modify graphical launchers, you may find these in `/home/USER/.local/share/applications/`, find the
relevant `.desktop` file and then replace `Exec=`, `Name=` or whatever
else you wish followed by:

```sh
update-desktop-database ~/.local/share/applications/
```

If your launchers are not present in your user directory, they're
probably system-wide and should therefore be overridden by being copied
to your user folder first before editing and updating the database, for
example:

```sh
cp -v /usr/share/applications/librewolf.desktop \
/home/USER/.local/share/applications/
```

Thoughts and feedback are welcome via
[@linus@telegrafverket.cc](https://telegrafverket.cc/@linus) -- email
works too.
