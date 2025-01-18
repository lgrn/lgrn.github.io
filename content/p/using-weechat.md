---
title: 'Using and configuring WeeChat, making IRC mostly painless'
date: 2025-01-18T12:00:00+02:00
draft: false
tags:
  - freebsd
  - linux
---

There's a simplicity to IRC compared to most "modern" alternatives that
is easy to love. This article is about how to set up the basics of
the WeeChat IRC client.

First of all, a short tangent regarding the name: _WeeChat_ (the IRC
client) was released in 2003, predating the Chinese instant messaging
app [WeChat](https://en.wikipedia.org/wiki/WeChat) by about eight years.
This, of course, does not matter much since the latter has more than
1.2B users (2022), which means confusion is unavoidable. It might be
unnecessary to state it, but they have no connection to eachother.

## Installing WeeChat

It's pretty likely that your \*NIX package manager already offers
WeeChat, so using `pacman`, `dnf`, `apt` or `pkg` should be sufficient.
We'll also be using `tmux` to keep the session alive, so for Debian:

```bash
apt install weechat tmux
```

## First launch

If you've never used `tmux` before, you only need to know that:

- `tmux` starts a new session
- `CTRL+b` followed by `d` will detach your session, keeping it alive in
  the background.
- `tmux a` will attach your tmux session again, assuming there is only one.

So let's start by creating our first tmux session, then start WeeChat
inside it:

```bash
tmux
```

```bash
weechat
```

When starting WeeChat the first time, you'll be in the `core` buffer,
which just means you haven't configured any IRC servers yet to switch
between. Let's do that now.

## Configuring IRC servers

Let's set up a connection to
[Libera.Chat](https://en.wikipedia.org/wiki/Libera_Chat), a network
founded in 2021 by former staff at Freenode. It's used by a wide variety
of open source projects, and is a good place to start.

This part is also covered pretty well in the [WeeChat
Quickstart](https://weechat.org/files/doc/stable/weechat_quickstart.en.html#add_irc_server).

First, let's add Libera as a server. As with any IRC network, it's best
to check with them directly what servers you can use, which Libera
provides in their [Connecting to
Libera.Chat](https://libera.chat/guides/connect) article:

| Description               | Hostname             |
| ------------------------- | -------------------- |
| Default                   | irc.libera.chat      |
| Europe                    | irc.eu.libera.chat   |
| US & Canada               | irc.us.libera.chat   |
| Australia and New Zealand | irc.au.libera.chat   |
| East Asia                 | irc.ea.libera.chat   |
| IPv4 only                 | irc.ipv4.libera.chat |
| IPv6 only                 | irc.ipv6.libera.chat |

| Description | Ports                |
| ----------- | -------------------- |
| Plain-text  | 6665-6667, 8000-8002 |
| TLS         | 6697, 7000, 7070     |

I'm in the EU, and I like TLS, so I'll do:

```
/server add libera irc.eu.libera.chat/6697

irc: server added: libera
```

Normally, you should be able to add `-tls` to this command, but for some
reason I couldn't get it to work, but that's fine: this is an excellent
reason to go through configuration of existing servers.

### Reconfigure the 'libera' server

Run the following to get a verbose output of all attributes set for all
servers, and use PGUP/PGDOWN to scroll:

```
/server listfull
```

Along lots of other attributes, you'll see:

```
Server: libera [not connected]
  addresses. . . . . . : 'irc.eu.libera.chat/6697'
  (...)
  ssl. . . . . . . . . :   (off)
```

We know this should be a secure connection, so let's change that value.
These attributes are all available via `irc.server.libera`, where
`libera` is the name you chose for the server, so the `ssl` value is set
with:

```
/set irc.server.libera.ssl on

Option changed: irc.server.libera.ssl = on  (default if null: off)
```

This will be useful to know later when we want to set things like
`autoconnect`, `autojoin` and so on.

### Choosing a name

Before connecting, we need to choose a name. Unlike what some may be
used to, the nickname on IRC is set by the user themselves on every
connection, and must be "reserved" by registration and authentication.
WeeChat can handle this for us, but the risk of collision with yourself
or someone that has rudely stolen your name means that setting up
alternate names is common practice. Assuming your preferred name is
`deppenleerzeichen` on this network, you may want to at least set:

```
/set irc.server.libera.nicks "deppenleerzeichen,deppenleerzeichen_"

Option changed: irc.server.libera.nicks = "deppenleerzeichen,deppenleerzeichen_"  (default if null: "root,root1,root2,root3,root4")
```

In this case, I'm running WeeChat in a container as root, which is why the
default name is variants of "root" (the user running weechat).

### Registering your name

We're now ready to connect, with our completely unregistered and made up
name:

```
/connect libera

(...)
libera  -- | User mode [+Ziw] by deppenleerzeiche
```

The [user mode](https://libera.chat/guides/usermodes) `+Z` tells us that
a secure connection was established successfully.

At this point, we could just join channels and start chatting away, but:

- We want our name to be registered, not only so we can know it won't be
  used by other people, but also because some channels require it.
- It hides your "host", meaning that if you run `/whois your_name`, your
  reverse DNS will be replaced by `user/your_name`, which is nice.
- We also want to set up authorization and channel joins automatically,
  so we don't have to manually do this every time WeeChat starts back up
  (because you'll forget how).

[Nickname Registration](https://libera.chat/guides/registration) in
libera's own documentation tells us how to do it:

```
/msg NickServ REGISTER some_decent_password youremail@example.com

An email containing nickname activation instructions has been sent to REDACTED.
Please check the address if you don't receive it. If it is incorrect, DROP then REGISTER again.
If you do not complete registration within one day, your nickname will expire.
deppenleerzeiche is now registered to REDACTED.
```

The e-mail you receive will contain a command you can run that looks
like:

```
/msg NickServ VERIFY REGISTER deppenleerzeiche something
```

Just run that, and you're done. Now that we have registered our name, we
can set up authentication and channel joins to happen automatically.

### SASL authentication

Back in the bad old days, identification was done by doing something
like `/msg nickserv identify`, which just sent a simple message to the
"nickserv" user (a bot) which then proved your identity. These days,
when supported, you should use SASL, so we're doing that.

Simply set `sasl_username` and `sasl_password` to your nickname and
chosen password respectively:

**WARNING**: If you are setting this up in a shared environment, this is
not a secure way to store your password. Refer to [Set custom IRC server
options](https://weechat.org/files/doc/stable/weechat_quickstart.en.html#irc_server_options)
and use `/secure passphrase` and `/secure set` to set up a secure
variable like `${sec.data.libera_password}` instead.

The below is a bit simpler, but should only be used on single user systems.

```
/set irc.server.libera.sasl_username "mynick"
/set irc.server.libera.sasl_password "xxxxxxx"
```

If you `/disconnect libera` then `/connect libera`, somewhere in the
output you should hopefully see:

```
You are now logged in as deppenleerzeiche (deppenleerzeiche!root@user/deppenleerzeiche)
deppenleerzeiche SASL authentication successful
```

### Final touches

Since we now have automatic authentication, the only thing left is to
set up autoconnect rather than having to do `/connect`, and what
channels we want to join. Autoconnect is just one of the attributes we
saw earlier with `/server listfull`:

```
/set irc.server.libera.autoconnect on
```

You can verify that this works by doing `/exit`, which will kill
WeeChat, then running `weechat` again.

The easiest way to set up auto-join of channels in my opinion is to
simply join the channels you want, for example:

```
/join #libera
```

To switch between channels and the "status" window, just do ALT+UP/DOWN,
or ALT+N where N is the number displayed on the left. When you're in the
status window, you can switch between server-specific buffers and the
core buffer by pressing CTRL+x. You'll notice that highlight colors
change (to show what lines are relevant to your current buffer), and
that `irc/libera` or `core` is displayed in the bottom left.

This is relevant because some commands only make sense in the context of
a single server, like the one we're going to run now:

```
/autojoin apply

libera     | Autojoin changed from empty value to "#libera"
```

This simply adds all the channels you are currently in to your autojoin
list. If you run this in the "core" context, you'll instead get:

```
weechat =!= | irc: command "autojoin" must be executed on irc buffer (server, channel or private)
```

You can now again run `/exit`, start WeeChat back up, and notice that
both authentication and channel joins happen automatically.

### Summary

We have:

- Installed WeeChat
- Configured connecting to an IRC server over TLS
- Registered our name, and set up automatic authentication
- Set up auto-join for the channels we want

There's obviously a lot more you can do with WeeChat, if you have any
suggestions or feedback feel free to get back to me via Mastodon
[@linus@telegrafverket.cc](https://telegrafverket.cc/@linus) or e-mail.
