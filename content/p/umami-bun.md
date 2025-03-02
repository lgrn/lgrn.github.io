---
title: 'Umami analytics with bun instead of npm'
date: 2025-03-02T11:00:00+02:00
draft: false
tags:
  - linux
  - sysadmin
  - lxc
  - javascript
---

Node.js and `npm` has been the standard for a long time when it comes to
running web applications written in server-side javascript. Here's how
to set up the Umami analytics application with Bun instead.

[Bun](https://github.com/oven-sh/bun) is the hyped JS runtime written in Zig
that is faster, includes a bundler, has native typescript support and
runs as a single binary. While I'm no fan of
javascript myself (neither hosting it nor the language itself), Bun
seems really interesting, and reminds me of [FrankenPHP](https://frankenphp.dev/) for PHP applications.

So when I came across [Umami](https://github.com/umami-software/umami)
when looking into self-hosted analytics platforms (used on this website
as we speak, your data is being rescued, please do not resist) I thought
it would be a great opportunity to try replacing `npm` and `yarn` suggested by the
installation instructions with Bun.

First, a reservation: I know almost nothing about node.js or javascript
development, apart from the fact that it's an absolute mess setting up
web applications if you don't want to use ready made docker images
(which I don't). Being forced to used the Node Version Switcher and
having your reserved disk space run out after multiple gigabytes of
dependencies are pulled is enough to make a grown man cry -- all this to
say that if you see something that looks strange and completely violates
any expectations of how these webapps should be set up, feel free to
[contact me](https://telegrafverket.cc/@linus).

## Step 1: Setting up the container

I'll be running this on Alpine, so I just do:

```sh
incus launch images:alpine/edge umami
```

I also use a `low-prio` Incus profile for this which sets:

```yaml
config:
  limits.cpu.priority: "5"
  limits.disk.priority: "0"
  limits.memory: 3GiB
  limits.memory.enforce: soft
```

## Step 2: Installing bun and umami

After some trial and error, these seem to be the packages required:

```sh
apk add bash unzip curl micro libstdc++ gcc git nodejs npm
```

In most cases I would hope `nodejs` and `npm` wouldn't be required, but
in this case it is as the umami database initialization does not work
without them. The only optional package here is `micro` which is just a
personal preference of editor.

Installing bun is done with:

```sh
curl -fsSL https://bun.sh/install | bash
```

Set up your `.bashrc` and switch to `bash`:

```sh
bash
cat ~/.bashrc
```

```sh
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
```

`source ~/.bashrc`and then clone the repo and run the installation:

```sh
git clone https://github.com/umami-software/umami.git
cd umami
bun install
```

In my case, I'm using a shared Postgres instance, so I'll set up a user
and database for umami to use:

```sql
CREATE DATABASE umami;
CREATE USER umami WITH PASSWORD 'something';
GRANT ALL PRIVILEGES ON DATABASE umami TO umami;
```

Access is restricted by the Postgres `listen_addresses` as well as
`pg_hba` specifying that these password connections can only come from
the local network:

```plain
host all all 10.186.228.1/24 scram-sha-256
```

Create `.env` and add something like:

```sh
DATABASE_URL=postgresql://umami:something@10.186.221.20:5432/umami
```

By trial and error, I figured out that `npm-run-all` is used and needs
to be added:

```sh
bun add npm-run-all
```

After this is all done, we can run the entire "build" as defined in
`package.json`:

```sh
bun run build
```

When this is done, we need to create the service. Here's an example of
how it might look on Alpine:

{{< code language="bash" title="/etc/init.d/umami" id="1" expand="Show"
collapse="Hide" isCollapsed="false" >}}#!/sbin/openrc-run

name="umami"
BUN_PATH="/root/.bun/bin/bun"
WORKING_DIR="/root/umami"
PIDFILE="/run/${name}.pid"

command="${BUN_PATH} start"
command_background=true
pidfile="${PIDFILE}"
directory="${WORKING_DIR}"

depend() {
    need net
}

start_pre() {
    checkpath --directory --mode 0755 /run
}

start() {
    ebegin "Starting ${name}"
    start-stop-daemon --start --background --make-pidfile --pidfile "${PIDFILE}" --chdir "${directory}" --exec ${BUN_PATH} -- start
    eend $?
}

stop() {
    ebegin "Stopping ${name}"
    if [ -f "${PIDFILE}" ]; then
        start-stop-daemon --stop --pidfile "${PIDFILE}" --retry 5
    else
        eerror "PID file not found: ${PIDFILE}"
    fi
    eend $?
}
{{< /code >}}

Make the service file executable with `chmod +x /etc/init.d/umami` and
then `rc-update add umami default` to have it start on boot.

Finally, do `rc-service umami start` and try curling localhost:3000 to
see if you get the expected output.

If you do, set up your reverse proxy of choice and log in with
admin/umami and configure your first site.
