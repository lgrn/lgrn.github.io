---
title: "LetsEncrypt DNS wildcard certificates with HAProxy"
date: 2024-03-12T12:00:00+02:00
draft: false
tags:
    - sysadmin
---

Wildcard certificates are really useful, especially in cases where you
are using a load balancer like HAProxy that targets multiple backends
serving separate subdomains.

This article will describe:

- How to install certbot (correctly) and run it in manual `certonly`
  mode to only get a certificate without any additional config magic.
- Receive a wildcard DNS certificate with Subject Alt Names, allowing
  multiple domains in the same certificate.
- Smash it together in a way so that HAProxy can use it.

Reservations:

- Installing certbot correctly requires snap, which is gross. In the
  future I'll explore using
  [acme.sh](https://github.com/acmesh-official/acme.sh) instead.
- There might be better ways to prep the certificate for HAProxy than
  smashing it together manually or via a script, I don't know.
- In order to receive wildcard certificates, authentication *must* be
  done over DNS records (not HTTP).

## Step 1: Install certbot

In order to get the latest version of certbot and any plugins required,
you *must* install via snap. Regardless of what you think about snap,
this is important because the version differences to, for example, the
Ubuntu 22 repos, is immense.

First, if you already have apt packages or similar system packages
installed providing certbot or any certbot plugins, remove them. Ensure
you have snap installed and running, then do:

```bash
snap install certbot
```

In this case, we will be DNS authenticating against Cloudflare, so we
also need the plugin for that:

```bash
snap set certbot trust-plugin-with-root=ok # required
snap install certbot-dns-cloudflare
```

Create a symlink to /usr/bin:

```bash
ln -s /snap/bin/certbot /usr/bin/certbot
```

Verify with `certbot --version`

## Step 2: Set up configuration

Ensure you have a file like `/root/.secrets/cloudflare.ini` that is
only readable by root and contains something like:

```ini
dns_cloudflare_email = "your@email.tld"
dns_cloudflare_api_key = "786sdf6f87fs87ssdffd"
```

You can set up an API key via the Cloudflare web GUI (google it).

## Step 3: Request certificate

Now that certbot has access to modifying your DNS records, you can run
something like:

```bash
certbot certonly --dry-run --dns-cloudflare \
--dns-cloudflare-credentials /root/.secrets/cloudflare.ini \
-d "my.domain,*.my.domain" \
--agree-tos --email foo@my.domain --preferred-challenges dns-01 -v
```

This will use your Cloudflare credentials and the `--dns-cloudflare`
plugin to make DNS changes on your behalf, validating your ownership of
the domain. The certificate will be issued to both `my.domain` and
`*.my.domain`, meaning that it will also work for any subdomains.

In order to actually receive a certificate, you must remove
`--dry-run`.

## Step 4: Smash certificate

Once you have successfully gotten a certificate, you'll see something
like:

```plain
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/my.domain/fullchain.pem
Key is saved at:         /etc/letsencrypt/live/my.domain/privkey.pem
This certificate expires on 2024-06-01.
```

In order for HAProxy to use this certificate, both the full chain and
the private key must be contained in one single PEM file. This is
easily achieved by doing:

```bash
cat /etc/letsencrypt/live/my.domain/fullchain.pem \
/etc/letsencrypt/live/my.domain/privkey.pem > \
/etc/ssl/haproxy/my_cert.pem
```

## Step 5: Configure HAProxy

You'll only need to do this once, if you keep using the same path for
the certificate:

```plain
bind *:443 ssl crt /etc/ssl/haproxy/
```

HAProxy is smart enough to figure out which certificate to use, so that
should be enough. For general TLS configuration, see the
[HAProxy SSL/TLS configuration tutorial](https://www.haproxy.com/documentation/haproxy-configuration-tutorials/ssl-tls/)

Whenever the certificate has changed on disk, you'll want to do:

```
systemctl reload haproxy
```
