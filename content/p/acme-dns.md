---
title: 'Automated DNS-01 certificates with acme-dns and letsencrypt'
date: 2025-06-07T22:00:00+02:00
draft: false
tags:
  - sysadmin
  - tls
---

The most common way to verify ownership of a hostname to receive a TLS
certificate is the HTTP-01 challenge on port 80, but DNS challenges not
only allows you to get wildcard certificates, they can also be used on
systems with no incoming internet access, with no manual intervention
required on renewals.

## Introduction: DNS-01 vs HTTP-01

### HTTP-01

When you pass a HTTP-01 challenge, it's because you were given a token,
and the hostname you wanted a certificate for was called up on port 80
and responded with that same token. For this reason letsencrypt,
or whatever ACME vendor you might be using, can be sure that you are in
control of this host.

There are two major drawbacks with the HTTP-01 validation, which may or
not matter depending on your use case:

1. The server in question must be able to answer port 80 requests from
   the Internet.
2. The certificate you request must be for a single FQDN with an
   A-record to that server.

If you need a wildcard certificate, or if you can not or will not open
the server to the Internet, you instead need:

### DNS-01

When you pass a DNS-01 challenge, it's because you were given a token,
and that token was then confirmed to exist in the DNS record for the
domain in question.

So if you are given `magic_token` after requesting a wildcard
certificate for `example.org`, the following public DNS record must exist to pass
validation:

```dns
_acme-challenge.example.org. TXT magic_token
```

Since you have proven your ability to enter records into the public DNS
for this domain, you have passed validation.

## The spooky parts of DNS-01

DNS records are, to put it mildly, pretty important. They are also often
non-trivial to update -- maybe you're lucky enough to have a DNS
provider that allows you to do this over an API, but this is not always
the case. And even if you do, does that API have decent access
restrictions, or have you just leaked an API key onto a bunch of
machines that can now update _any_ record in your DNS?

Wouldn't it be nice if there was some way to simply delegate the ACME
validation away to another DNS server, without having to touch your
scary production records more than necessary? Well, you're in luck
because you can, and someone already wrote a dedicated DNS server that
does nothing but ACME validation, and has an API for automatic renewals,
and it's called `acme-dns`.

Before we jump into that, let's talk briefly about what "delegating"
this responsibility actually means.

## Delegating ACME validation with CNAME

As you now know `_acme-challenge` is a type of magic subdomain where
ACME validation expects to find the token you were given, and in many
cases this will be a `TXT` record that is then removed.

Consider instead if this was not a record of type `TXT` but instead of
type `CNAME` (i.e. an alias, or redirect):

```dns
_acme-challenge.example.org. CNAME any.dns.server.com.
```

If this record is left permanently in DNS, it would mean that every
incoming DNS-01 challenge, now and in the future, would instead be
redirected and possibly completed by a `TXT` record from
`any.dns.server.com`, which is also under a completely different domain.

This is still far from automatic though, the problem has really only
moved from how annoying it is to update the DNS for `example.org` to how
annoying it is to do the same for `any.dns.server.com`, and this is the
problem that `acme-dns` solves.

## acme-dns

acme-dns ([joohoi/acme-dns](https://github.com/joohoi/acme-dns)) is a:

> _limited DNS server with RESTful HTTP API to handle ACME DNS
> challenges easily and securely_

In other words, it's a single-binary DNS server that serves only one
purpose: to respond to ACME DNS challenges, and to provide an API
through which you can request certificates.

By way of example, let's say you own `example.org` and you want to host
acme-dns on `acme.example.org`. Since the following text will talk about
two DNS servers, they will be referred to as the "parent" DNS (for
`example.org`), and the "child" DNS (`acme.example.org`).

Due to the variable times involved in DNS propagation, I would
suggest that before doing anything else, adding the following records to
the parent DNS, using whatever will be the external IP of acme-dns, is a
good idea:

```dns
acme    A   1.2.3.4
acme    NS  acme.example.org.
```

In human language:

- `A`: The IP of `acme.example.org` is `1.2.3.4`
- `NS`: The nameserver responsible for the `acme` subdomain in
  `example.org` is `acme.example.org`

Note that an NS record must not be dependent on a CNAME redirection.

After applying these records, we can let them marinate while actually
setting up acme-dns.

Note that in some cases, NS records may take up to 24 hours to
propagate. Web services like
[whatsmydns](https://www.whatsmydns.net/#NS) can be helpful here.

### Install acme-dns

Follow the instructions in
[README#installation](https://github.com/joohoi/acme-dns?tab=readme-ov-file#installation)
-- like any golang binary, you just need to compile it and place it in
your path. Set up a service with systemd, or whatever init system you
prefer.

Example of `config.cfg` used by acme-dns:

```ini
[general]
# listen on port 53 (DNS) on any IP
listen = "0.0.0.0:53"
# listen on both tcp and udp, but only ipv4
protocol = "both4"
domain = "acme.example.org"
nsname = "acme.example.org"
# 'nsadmin' takes an email, with @ replaced by .
# for this reason, an email with dots cannot be used
nsadmin = "admin.example.org"
# A-record and NS-record, same as in parent dns
records = [
    "acme.example.org. A 1.2.3.4",
    "acme.example.org. NS acme.example.org.",
]
debug = false

[database]
engine = "sqlite3"
connection = "/root/acme-dns.db"

[api]
# listen to incoming http api calls on any ip
ip = "0.0.0.0"
# disable new registrations, can be done after setup
# is complete if no new registrations are expected
disable_registration = false
# http api listens on port 80
port = "80"
# do not use TLS, in this case because TLS termination
# happens before acme-dns is hit
tls = "none"
corsorigins = [
    "*"
]
# use HTTP header to get the client ip, useful when
# a reverse proxy is involved.
use_header = true
header_name = "X-Forwarded-For"

[logconfig]
# logging level: "error", "warning", "info" or "debug"
# this can be turned down from debug after initial setup
loglevel = "debug"
logtype = "stdout"
logformat = "text"
```

Simply set up your service to run `/usr/bin/acme-dns` (or wherever you
put it) pointing to the config file to use with something like `-c
/root/config.cfg`.

On Alpine for example `/etc/init.d/acme-dns` might look like this:

```sh
#!/sbin/openrc-run
command="/usr/bin/acme-dns"
command_args="-c /root/config.cfg"
command_background="yes"
output_log="/root/acmedns.log"
error_log="/root/acmedns.log"
pidfile="/run/acme-dns.pid"
depend() {
    need net
    after firewall
}
```

Followed by:

```sh
rc-update add acme-dns default
rc-service acme-dns start
```

The DNS server is now running, so you should be able to query the
`records = []` seen in the config above:

```sh
dig @1.2.3.4 acme.example.org
dig @1.2.3.4 acme.example.org +tcp
```

acme-dns is now installed, but cannot complete any certificate
challenges yet.

### Register with acme-dns

As long as `disable_registration = false`, anyone can register a new
user with acme-dns -- but apart from causing some kind of denial of
service, this will not give any inherent permissions to do anything but
trigger (failing) certificate requests. Still, after initial setup, it's
a good idea to change this to `true`.

Registration can be handled automatically by many clients, but for the
purpose of understanding what's going on, we will be doing it manually.

Simply send a `POST` request to the `/register` endpoint, optionally
with an IP restriction on future requests for these credentials.

```bash
curl -X POST "https://acme.example.org/register" \
     -H "Content-Type: application/json" \
     -d '{
           "allowfrom": [
             "10.1.1.0/24"
           ]
         }'
```

acme-dns responds with something like:

```json
{
  "username": "<redacted>",
  "password": "<redacted>",
  "fulldomain": "<uuid>.acme.example.org",
  "subdomain": "<uuid>",
  "allowfrom": ["10.1.1.0/24"]
}
```

Save this in a safe place, as it will be needed later. If you wish, you
can now disable registration and restart acme-dns.

This output can be interpreted as "when authenticating with username
`<redacted>` and password `<redacted>` from an IP in the
`10.1.1.0/24` subnet, the challenge token will be added to
`<uuid>.acme.example.org`".

While we have already created an `A`-record and an `NS`-record, no
actual **delegation** of the ACME challenge has been done yet. To do
this, we need to add this third and final record to our parent DNS:

```dns
_acme-challenge.example.org. CNAME <uuid>.acme.example.org.
```

In other words, when an external ACME provider (like letsencrypt) looks
up `_acme-challenge.example.org`, perhaps expecting a TXT record
containing the token, it will instead be redirected to
`<uuid>.acme.example.org`.

Since we added an `NS` record stating that `acme.example.org` is itself
the DNS responsible for anything under that subdomain, the question for
the `<uuid>` record will go to acme-dns, which is exactly what we want.

At this point, we should be ready to use our username and password in
any client supporting acme-dns. In this example, we will use `acme.sh` ([acmesh-official/acme.sh](https://github.com/acmesh-official/acme.sh))

### Request a certificate

Since we are no longer bound by the requirements of HTTP validation, the
server requesting a certificate can be situated in any environment, as
long as it can reach `acme.example.org` from an IP in the `allowfrom`
list.

Assuming you have all necessary packages, the installation of acme.sh is
straight-forward:

```sh
curl https://get.acme.sh | sh -s email=my@example.com
```

The shell script and all stateful data (credentials, certificates etc.)
will be put in `~/.acme.sh/`

Before setting it up, let's do a sanity check of our DNS records from
this "client" machine:

```sh
dig CNAME _acme-challenge.example.org
# should point to <uuid>.acme.example.org

dig NS acme.example.org
# should show that acme-dns is the authoritative
# name server for its own subdomain

dig A acme.example.org
# should give us the external IP of acme-dns
```

Now, as shown in the [acme.sh docs for
acme-dns](https://github.com/acmesh-official/acme.sh/wiki/dnsapi#45-use-acme-dns-api):

```sh
export ACMEDNS_BASE_URL="https://acme.example.org"
export ACMEDNS_USERNAME="<username>"
export ACMEDNS_PASSWORD="<password>"
export ACMEDNS_SUBDOMAIN="<uuid>"
```

When these are all set, just request a certificate by running the script:

```sh
./acme.sh --issue --dns dns_acmedns -d example.org -d *.example.org --server letsencrypt
```

acme.sh will use zerossl by default, this can be overridden with
`--server`, or permanently changed with `--set-default-ca`.

Hopefully, by now you will be met by a successful certificate request,
with some information on where the certificate has been stored.

Further things to look into if you're deploying certificate renewals
with acme.sh:

- `./acme.sh --help`
- Use `./acme.sh --install-cronjob` to install the cronjob for automatic
  certificate renewal.
- Use `./acme.sh --list` to show all domains acme.sh knows about
- Use `--install-cert` to actually place the certificate, and
  `--reloadcmd` to reload the relevant service.

Nginx example from the acme.sh README:

```sh
acme.sh --install-cert -d example.com \
--key-file       /path/to/keyfile/in/nginx/key.pem  \
--fullchain-file /path/to/fullchain/nginx/cert.pem \
--reloadcmd      "service nginx force-reload"
```

There are of course other clients than acme.sh supporting acme-dns. From
their own README, some examples are:

- Certify The Web: <https://github.com/webprofusion/certify>
- cert-manager: <https://github.com/jetstack/cert-manager>
- Lego: <https://github.com/xenolf/lego>
- Posh-ACME: <https://github.com/rmbolger/Posh-ACME>
- Sewer: <https://github.com/komuw/sewer>
- Traefik: <https://github.com/containous/traefik>
- Windows ACME Simple (WACS): <https://www.win-acme.com>

Thoughts and feedback are welcome via
[@linus@telegrafverket.cc](https://telegrafverket.cc/@linus) -- email
works too.
