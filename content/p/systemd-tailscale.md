---
title: 'Making tailscaled dependable for sshd and other services'
date: 2025-03-01T09:45:00+02:00
draft: false
tags:
  - linux
  - debian
  - ubuntu
  - sysadmin
  - systemd
  - tailscale
---

If you use Tailscale on your server, you may have services that should
only listen on that IP. Unfortunately, the tailscaled service often goes
active before it's actually done, breaking dependencies: here's how to
fix it.

There are multiple Github issues pointing out that the `tailscaled`
systemd service does not behave very well and often says that it's ready
before a bindable IP is actually available:
[#11504](https://github.com/tailscale/tailscale/issues/11504) and
[#3340](https://github.com/tailscale/tailscale/issues/3340) are two
examples.

In March 2024, almost a year ago as of this writing, it was pointed out
that this looks like a regression, but since it still doesn't seem to be
fixed, it requires users to work around it.

One great way mentioned in #11504 is that you can add an `ExecStartPost`
attribute for the tailscaled service that ensures it's _actually_ done
before marking the service as running.

In this example, we'll illustrate how to set up and make a dependency in the ssh
daemon service more reliable, for situations where your tailscale ip is
the only ip that you expect to use for ssh.

## Step 1: Improve `tailscaled.service` reliability with an override

Run the following to open your editor, creating an override for the
service object:

```sh
systemctl edit tailscaled
```

Read the comments on screen, and add the following between the two
comment blocks as instructed:

```toml
[Service]
ExecStartPost=timeout 60s bash -c 'until tailscale status --peers=false; do sleep 1; done'
```

The comments will show you the current configuration of the service
object, where you may note that `ExecStartPost` is not set. The way
overrides work is that anything specified will "merge" into the existing
service configuration without having to change it, which is good since
it's often owned by the package itself. It follows the logic of
`.d`-directories, which is also clear by the path chosen for these
override files.

When you have saved and exited from your editor, you can run the
following to see the full "state" of your current service object
configuration:

```sh
systemctl cat tailscaled
```

Note that your override shows up at the bottom.

## Step 2: Configure sshd and create a dependency

If you want your ssh daemon to only listen on a specific ip, the easiest
way to achieve this is to simply configure it in `sshd_config`. Look for
the `ListenAddress` attribute, and specify it once or several times,
depending on your use case. In this example, we are using both tailscale
and wireguard, so the sshd configuration looks like this:

```plain
ListenAddress 100.74.237.36
ListenAddress 10.10.10.5
```

Confirming that this configuration is active, after a restart if changed
recently, can be done by simply looking for the `Port` configured in
sshd in the output of `ss`:

```bash
ss -tuln | grep ':22'
```

```plain
tcp LISTEN 0 128 100.74.237.36:22 0.0.0.0:*
tcp LISTEN 0 128    10.10.10.5:22 0.0.0.0:*
```

If your sshd configuration is set up correctly, all you have to do is
create the service object dependency, to ensure that the ssh daemon
waits for `tailscaled.service` before starting, which should now be a
bit more reliable with the above workaround.

Again, simply do:

```bash
systemctl edit ssh
```

A short tangent on lists in systemd: some attributes, like `After` in
this case, are __lists__. You can tell that something is a list from the
way that it's clearly a list:

```toml
Attribute=lists have multiple objects
```

Although it's not a valid syntax, the above can be mentally parsed as:

```toml
Attribute=[lists, have, multiple, objects]
```

There are other attributes which are clearly not lists, like
`Description` which takes a string, and only one string.

Because overrides will "merge" values, the default behavior when
overriding a list is to _append to that list_. If you want to actually
__override__ the list, you therefore need to remember to null the list
first before overriding it. For example, if the current value is
`Attribute=foo fax` and you want to completely override it, this
requires you to do:

```toml
[Section]
Attribute=
Attribute=bar baz
```

If you don't do this, the end result of the override would be
`Attribute=foo fax bar bax`.

This is good to know, but not strictly relevant in our case, as we
actually do want to just append new dependencies, so after running
`systemctl edit ssh` we can simply add:

```toml
[Unit]
After=wg-quick@wg0.service tailscaled.service
```

If you are not using wireguard, this would obviously just be
`tailscaled.service`.

After saving and running `systemctl daemon-reload`, we can again verify:

```sh
systemctl cat ssh | grep After
```

```toml
After=network.target auditd.service
After=wg-quick@wg0.service tailscaled.service
```

If you want to be extra sure, you can also check the output of:

```sh
systemctl show ssh | grep After=
```

Now that both `tailscaled.service` and `ssh.service` are fixed up, you
can at your convenience try rebooting the server, first ensuring you have a
way of getting back in if it breaks, of course.

You can then, hopefully, observe the services starting in the correct
order:

```sh
journalctl --boot | grep -E "ssh.service|tailscaled.service"
```

```plain
systemd[1]: Starting tailscaled.service - Tailscale node agent...
systemd[1]: Started tailscaled.service - Tailscale node agent.
systemd[1]: Starting ssh.service - OpenBSD Secure Shell server...
systemd[1]: Started ssh.service - OpenBSD Secure Shell server.
```
