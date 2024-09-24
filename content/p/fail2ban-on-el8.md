---
title: 'fail2ban on EL8'
date: 2021-10-08T15:30:51+02:00
draft: false
tags:
  - linux
  - sysadmin
---

fail2ban is commonly used to take a certain action, such as automatically blocking an IP, after repeated authentication failures or other generally bad behavior against applications, as detected by regex matching against log output.

This example will show how to install and configure fail2ban on EL8 (Rocky Linux 8.4), and to configure it to block an IP after multiple failed login attempts.

#### Installing fail2ban via EPEL

```
# yum install https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm
# yum install fail2ban

# fail2ban-client --version
Fail2Ban v0.11.2

# systemctl enable fail2ban --now
# fail2ban-client status
Status
|- Number of jail:      0
`- Jail list:
```

At this point, fail2ban is installed and running, but does not have any active jails. The first step is therefore to enable the jails we want, which is done by copying the default file in `/etc/fail2ban` called `jail.conf` to `jail.local`, which is the fail2ban syntax for a user-defined override file.

```
# cp jail.conf jail.local && vim jail.local
```

Since all the commented help text is still available in `jail.conf`, we can make our override file short and sweet. The options should be pretty self-explanatory:
{{< code language="cfg" title="jail.local" id="1" expand="Show" collapse="Hide" isCollapsed="false" >}}
[DEFAULT]
bantime = 24h
maxretry = 3
findtime = 60m
backend = systemd
banaction = nftables[type=allports]

[sshd]
enabled = true
{{< /code >}}
This will ban an IP for `24h` if `3` failed attempts happen within `60m`. The IP will be banned on all ports and is actioned through `nftables`.

When the file is saved, let's restart fail2ban and verify that the jail is active:

```
# systemctl restart fail2ban
# fail2ban-client status
Status
|- Number of jail:      1
`- Jail list:   sshd
```

#### Trust, but verify

Now let's do something dumb and enable passwords for SSH authentication, then attempt to get ourselves banned when failing to login from `127.0.0.1`. First, ensure password authentication is enabled in `/etc/ssh/sshd_config`:

```
PasswordAuthentication yes
```

Restart the SSH daemon:

```
# systemctl restart sshd
```

Attempt an SSH login with an incorrect password:

```
# ssh localhost -P
root@localhost's password:
Permission denied, please try again.
```

This failed attempt should now be visible in `/var/log/secure`:

```
unix_chkpwd[1373]: password check failed for user (root)
sshd[1371]: pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 .0.1  user=root
sshd[1371]: Failed password for root from 127.0.0.1 port 37780 ssh2
sshd[1371]: Connection closed by authenticating user root 127.0.0.1 port 37780 [preauth]
```

This very serious breach attempt was naively ignored by fail2ban though, as visible in `/var/log/fail2ban.log`:

```
fail2ban.filter [1305]: INFO [sshd] Ignore 127.0.0.1 by ignoreself rule
```

Luckily, this is something we can override in our `jail.local` file by setting `ignoreself = false` under `[DEFAULT]`. After restarting fail2ban, repeated attempts gives us this in `fail2ban.log`:

```
fail2ban.filter  [1451]: INFO    [sshd] Found 127.0.0.1 - 2021-10-08 14:38:01
fail2ban.filter  [1451]: INFO    [sshd] Found 127.0.0.1 - 2021-10-08 14:38:49
fail2ban.filter  [1451]: INFO    [sshd] Found 127.0.0.1 - 2021-10-08 14:38:51
fail2ban.actions [1451]: NOTICE  [sshd] Ban 127.0.0.1
```

Congratulations, you've banned yourself:

```
# fail2ban-client banned
[{'sshd': ['127.0.0.1']}]
```

Clearing all bans:

```
# fail2ban-client unban --all
```

#### Summary

What we've done:

- We created a `jail.local` override file with our own settings.
- We enabled the `sshd` jail, and there are of course others ready to use for other services.
- We verified that repeatedly failing to log in did add the firewall rule correctly, and that fail2ban could clear it.
