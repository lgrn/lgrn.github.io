---
title: 'Installing the ruTorrent web UI on Debian'
date: 2025-07-27T12:00:00+02:00
draft: false
tags:
  - sysadmin
  - debian
  - torrent
  - incus
---

ruTorrent is a popular web interface for the rtorrent client, here's how
to set it up with lighttpd on Debian.

## Incus

In this example, we will set up ruTorrent and rtorrent in an incus
container. If you just want to set it up on a regular Debian server,
just skip the Incus specific parts, and make sure you don't run any
application as root.

Start by launching a container:

```sh
incus launch images:debian/bookworm torrent
```

If you want a shared mount for this container, add it with `incus config
edit`:

```yaml
share:
  path: /share
  readonly: 'false'
  source: /mnt/share/
  type: disk
```

For "consumer" containers, you may want `readonly: "true"`.

"Container root" is uid `1000000`, so any disk shared like this needs to
have its permissions changed to allow write access. In this case, we'll
go with an ownership change from `root:root` to `1000000:root`
recursively, but you should pick something suitable for your setup:

```sh
chown -Rv 1000000:root /mnt/share
```

Now, let's move into the container with `exec bash`.

## Installation steps

```sh
apt install rtorrent lighttpd php-fpm php-cli php-curl php-xmlrpc git curl
```

In `/var/www` we're going to clone the ruTorrent web UI repo, choose a
tagged release of your preference:

```sh
git clone --branch v5.2.10 --depth 1 https://github.com/Novik/ruTorrent.git
```

We need to fix permissions so that lighttpd can access these files:

```sh
chown -Rv root:www-data /var/www/ruTorrent/
chmod -Rv 770 /var/www/ruTorrent/
```

Let's create our first systemd service:

### rtorrent

Create `/etc/systemd/system/rtorrent.service`:

```ini
[Unit]
Description=rTorrent BitTorrent Client
After=network.target

[Service]
ExecStart=/usr/bin/rtorrent -n -o import=/root/.rtorrent.rc
Type=simple
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

All configuration is done in `/root/.rtorrent.rc`:

```ini
# see https://github.com/rakshasa/rtorrent/wiki/Performance-Tuning

# 90-ish percent of total bandwidth to avoid latency spikes
throttle.global_down.max_rate.set_kb = 52000
throttle.global_up.max_rate.set_kb   = 10000

pieces.memory.max.set = 2048M
network.max_open_sockets.set = 1024
network.max_open_files.set = 1024

directory.default.set = /root/rtorrent/data
session.path.set = /root/rtorrent/session
network.scgi.open_local = /run/rtorrent.sock
execute.nothrow = chown,root:www-data,/run/rtorrent.sock
execute.nothrow = chmod,770,/run/rtorrent.sock

# make sure port 50000 below can be reached
network.port_range.set = 50000-50000
network.port_random.set = no

dht.mode.set = auto
protocol.pex.set = yes
system.umask.set = 0007
system.daemon.set = true
```

Create the folders we just referred to:

```sh
mkdir -p /root/rtorrent/session
mkdir /root/rtorrent/data
```

Enable and start rtorrent:

```sh
systemctl enable rtorrent --now
```

### ruTorrent

ruTorrent comes with a bunch of plugins, some of which require external
dependencies that may not be available. If you don't want these plugins,
simply remove them:

```sh
cd /var/www/ruTorrent/plugins

rm -rfv _cloudflare rss rssurlrewrite rutracker_check spectrogram mediainfo screenshots dump unpack
```

The only config change that needs to be done in regards to ruTorrent is
to point it to the correct socket, i.e. the one we specified in the
rtorrent configuration. In `conf/config.php` set:

```php
$scgi_port = 0;
$scgi_host = "unix:///run/rtorrent.sock";
```

Optionally, you may also want to change
`/var/www/ruTorrent/plugins/theme/conf.php` and set:

```php
$defaultTheme = "MaterialDesign";
```

### lighttpd

There's a few things we need to do to make lighttpd serve this PHP code
correctly -- it has the concept of "modules" which are what you may
recognize from something like nginx etc as the `available` and `enabled`
directories. Let's start by disabling the "unconfigured" module that is
enabled by default:

```sh
lighty-disable-mod unconfigured
```

Now, create `/etc/lighttpd/conf-available/90-rutorrent.conf`:

```plain
server.modules += ( "mod_scgi" )
server.document-root = "/var/www/ruTorrent"
scgi.server = (
  "/RPC2" => (
    "/" => (
      "socket" => "/run/rtorrent.sock",
      "check-local" => "disable"
    )
  )
)
```

We can now enable this as well as the required php module at the same
time:

```sh
lighty-enable-mod rutorrent fastcgi-php-fpm
```

To avoid a crash, we must also in `/etc/lighttpd/lighttpd.conf` comment
out the `server.document-root` value, since we changed it above.

You can now:

```sh
systemctl restart lighttpd
```

### Reverse proxy

lighttpd is configured to serve normal http on port 80, because the
expectation here is that a reverse proxy is used for TLS termination.
Configure one of your choice to forward traffic to the container.

### Networking

We previously configured rtorrent to use port 50000, if that's open then
everything is fine. If not, and this is an incus container, we need to
add a port forward. First:

- create a forward list on the bridge for the host ip, if not done already

```sh
incus network forward list incusbr0
incus network forward create incusbr0 192.168.1.10
```

Where `192.168.1.10` is the ip of your host system on its network.

- edit the forward list and add a descriptive entry in "ports" to the container ip

incus network forward edit incusbr0 192.168.1.10

```yaml
- description: rtorrent_tcp
  protocol: tcp
  listen_port: '50000'
  target_port: '50000'
  target_address: 10.191.32.229
- description: rtorrent_udp
  protocol: udp
  listen_port: '50000'
  target_port: '50000'
  target_address: 10.191.32.229
```

Where `10.191.32.229` is the ip of your container. Now, as long as
traffic hits `192.168.1.10:5000`, it should be forwarded correctly.

Thoughts and feedback are welcome via
[@linus@telegrafverket.cc](https://telegrafverket.cc/@linus) -- email
works too.
