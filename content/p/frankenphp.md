---
title: 'Roundcube with FrankenPHP on Debian'
date: 2024-11-09T16:00:00+01:00
draft: false
tags:
  - sysadmin
  - linux
  - php
  - mail
---

FrankenPHP is a "modern application server for PHP built on top of the
Caddy web server", which in its simplest form lets you serve PHP apps
without the nginx/apache config salad you may be used to. Here's how to
set it up as a service on Debian.

In this example we'll set up [Roundcube](https://roundcube.net/), a
popular front-end for interacting with mail servers, written in PHP.

Assumptions:

- Roundcube will be running alone in a dedicated LXC container, so
  everything will run as root. If you are running it on a server with
  multiple applications, you probably want to adjust permissions and the
  user that the service runs as.

- A reverse proxy handles certificates before hitting FrankenPHP, so we
  only listen on port 80. If this is Internet-facing, reconfigure it to
  also handle certificates, with a Caddyfile for example.

First, let's download and unpack the latest "Complete" version of
Roundcube from [the download page](https://roundcube.net/download/):

```bash
# check the version
curl -OL https://github.com/roundcube/roundcubemail/releases/download/1.6.9/roundcubemail-1.6.9-complete.tar.gz

# unpack it
tar xvf *.tar.gz
```

In the `config/` directory inside the roundcube directory, copy
`config.inc.php.sample` to `config.inc.php` and set it up as instructed
by the comments.

Most likely, you only have to modify:

```php
$config['db_dsnw'] = 'sqlite:////root/sqlite.db?mode=0646';
$config['imap_host'] = 'your.server:143';
$config['smtp_host'] = 'your.server:587';
$config['product_name'] = 'My Webmail';
$config['des_key'] = 'something_else';
```

If the mail server is reachable on an internal IP on the same server,
you may want to add this to `/etc/hosts` to override the A-record.

Install FrankenPHP:

```bash
curl https://frankenphp.dev/install.sh | sh

mv frankenphp /usr/local/bin/
```

Create `/etc/systemd/system/frankenphp.service`:

```ini
[Unit]
Description=FrankenPHP Web Server
After=network.target

[Service]
ExecStart=/usr/local/bin/frankenphp php-server
WorkingDirectory=/root/roundcubemail-1.6.9
Restart=always
Environment=XDG_CONFIG_HOME=/root/.config
Environment=HOME=/root

[Install]
WantedBy=multi-user.target
```

When it's saved, do `systemctl daemon-reload` and `systemctl enable
frankenphp --now`.

Inside the working directory of `/root/roundcubemail-1.6.9`,
`/usr/local/bin/frankenphp` will now serve the PHP app on port 80.

To set up Roundcube, add the following to your config file and save:

```php
$config['enable_installer'] = true;
```

This will enable the installer on the `/installer` URI where you can
check functionality. If it works, comment out the above config value
again to disable the installer and remove the `installer/` directory in
the roundcube directory.

At this point, you should be ready to log in with whatever credentials
are valid for the mail server itself.
