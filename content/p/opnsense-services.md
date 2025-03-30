---
title: 'Manually set up services on OPNsense'
date: 2025-03-30T11:00:00+02:00
draft: false
tags:
  - sysadmin
  - freebsd
  - opnsense
---

One of the main benefits of OPNsense is obviously the web interface, but
if you just want to set up a service manually like on FreeBSD, here's how you can
do it. In this case, we're setting up dnscrypt-proxy.

It's a DNS proxy that allows you to send *encrypted* DNS queries from your
router, while still responding to "normal" DNS queries from your
internal network. Since it also supports blacklisting and cloaking, it
can be very useful in situations where you don't want to run a full DNS
server but still want to serve and secure your DNS queries locally.

First of all, ensure you grab the correct package and that the other
packages are not installed:

```sh
# pkg search dnscrypt
dnscrypt-proxy2-2.1.5_10       Flexible DNS proxy with support for encrypted protocols
os-dnscrypt-proxy-1.15_2       Flexible DNS proxy supporting DNSCrypt and DoH
os-dnscrypt-proxy-devel-1.15_2 Flexible DNS proxy supporting DNSCrypt and DoH
```

The `os-*` packages are OPNsense packages which will install it as a
"plugin" in your web-gui. In this case we don't want that, we're setting
it up as a normal service, so `pkg install dnscrypt-proxy2` while
ensuring the other two are not present.

When installed, we need to configure it, then enable the service.
Configuration is located in `/usr/local/etc/dnscrypt-proxy`, and my
config file looks like this:

{{< code language="toml" title="dnscrypt-proxy.toml" id="1" expand="Show"
collapse="Hide" isCollapsed="false" >}}server_names = ['mullvad']
listen_addresses = ['127.0.0.1:53','192.168.1.1:53']
max_clients = 250
ipv4_servers = true
ipv6_servers = false
dnscrypt_servers = true
doh_servers = true
require_dnssec = true
require_nolog = true
require_nofilter = true
force_tcp = false
timeout = 2500
keepalive = 30
log_level = 2
log_file = '/var/log/dnscrypt-proxy/dnscrypt-proxy.log'
use_syslog = false
cert_refresh_delay = 240
dnscrypt_ephemeral_keys = false
tls_disable_session_tickets = false
bootstrap_resolvers = ['9.9.9.9:53']
ignore_system_dns = false
netprobe_timeout = 30
log_files_max_size = 10
log_files_max_age = 7
log_files_max_backups = 1
block_ipv6 = false

forwarding_rules = 'forwarding-rules.txt'
cloaking_rules = 'cloaking-rules.txt'

cache = true
cache_size = 4096
cache_min_ttl = 2400
cache_max_ttl = 86400
cache_neg_min_ttl = 60
cache_neg_max_ttl = 600

[allowed_names]
  allowed_names_file = 'whitelist.txt'
  log_file = '/var/log/dnscrypt-proxy/whitelisted.log'
  log_format = 'tsv'

[blocked_names]
  blocked_names_file = 'blocked-names.txt'

[static]
  [static.'mullvad']
  stamp = 'sdns://AgcAAAAAAAAACzE5NC4yNDIuMi4yAA9kbnMubXVsbHZhZC5uZXQKL2Rucy1xdWVyeQ'
{{< /code >}}

In this config, `server_names` refer to the external
`[static.'mullvad']` DNS configured at
the bottom, and `listen_addresses` matches the IP this router has on my
local network.

In this case, `bootstrap_resolvers` is configured, because the DNS
configured uses DNS-over-HTTPS, which requires resolving a hostname.
This "bootstrap resolver" is not used for any other queries than making
the actual DNS server work.

If you wish, you may use `forwarding_rules` (I don't, but the file must
exist) or `cloaking_rules`. In my case, I use cloaking to ensure that
servers that are actually within the same internal network are resolved
with local IP addresses instead. For example, if you have
`blog.my.domain` hosted on a server at home, other people should get
your external IP in their response, but if it can be reached at
`192.168.1.101` in your network, you probably want to cloak it:

```plain
blog.my.domain 192.168.1.101
```

This way, when you try reading your blog on your internal network you'll
hit that server directly instead, because dnscrypt-proxy will change
the response.

I don't use `allowed_names`, but `blocked_names` is very useful. I point
it to `blocked-names.txt` and then fetch this file nightly followed by a
restart of the service.

I do this via `/etc/periodic/daily/900.dnscrypt-blocklist` (executable)
which looks something like this:

```sh
#!/bin/sh
/usr/local/bin/curl \
https://cdn.jsdelivr.net/gh/hagezi/dns-blocklists@latest/wildcard/pro-onlydomains.txt \
-o /usr/local/etc/dnscrypt-proxy/blocked-names.txt \
&& /usr/sbin/service dnscrypt-proxy restart
```

This simply grabs the latest version of
[hagezi/dns-blocklists](https://github.com/hagezi/dns-blocklists) and
overwrites `blocked-names.txt` with it, followed by a service restart.

By doing this, you have a daily updated blocklist that will refuse to
resolve any domain listed. There are many blocklists to choose from, so
pick one that fits you.

When you're happy with your configuration, it's time to enable the
service. On OPNsense (FreeBSD), this is done via `rc.conf`, specifically
`/etc/rc.conf.d/dnscrypt_proxy`:

```ini
# Ensure this line DOES NOT exist, this is used by the web gui plugin
# dnscrypt_proxy_setup="/usr/local/opnsense/scripts/OPNsense/Dnscryptproxy/setup.sh"
dnscrypt_proxy_enable="YES"
dnscrypt_proxy_suexec="YES"
```

You should now, hopefully, be able to simply do:

```sh
service dnscrypt-proxy start
```

Check the log and try making some queries:

```sh
tail -f /var/log/dnscrypt-proxy/dnscrypt-proxy.log
```

On another system, checking a blocked and non-blocked domain:

```sh
dig +short health-tips-shortcuts.00go.com @192.168.1.1
"This query has been locally blocked" "by dnscrypt-proxy"

dig +short agren.cc @192.168.1.1
172.67.181.149
104.21.18.104
```

You're done!

## Bonus material: DNS stamps

This extra section is for anyone who thinks this DNS server looks a bit odd:

```plain
sdns://AgcAAAAAAAAACzE5NC4yNDIuMi4yAA9kbnMubXVsbHZhZC5uZXQKL2Rucy1xdWVyeQ
```

This is what's called a "DNS stamp", an encoding format that
includes everything you need to securely connect to a DNS server in one
string.

You can paste it into <https://dnscrypt.info/stamps/> to see what it
contains: it basically just says that it's DNS-over-HTTPS (DoH), and
that `dns.mullvad.net/dns-query` should be queried.
Since this is DoH, it does not include a public key in the stamp itself --
instead we rely on our `bootstrap_resolvers` to help us reach
`dns.mullvad.net`, which then needs to present us with a valid
certificate, just like any normal HTTPS response.

Mullvad only provides DoH, but if you look at the [public server
list](https://dnscrypt.info/public-servers/) and compare it to for example
`dnscry.pt-stockholm-ipv4`:

```
sdns://AQcAAAAAAAAADjE4NS4xOTUuMjM2LjYyIBs-wdms4LUcYsk1gE7X2G0U7jqOAxC0ihiHfIwVJAYTGTIuZG5zY3J5cHQtY2VydC5kbnNjcnkucHQ
```

This longer string specifies DNSCrypt (not DoH) and includes the public
key of the provider in addition to the IP; this way an initial DNS
lookup is not necessary.

What protocol to use for secure DNS resolution is completely subjective.
