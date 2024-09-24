---
title: 'MAC spoofing on Wi-Fi with captive portals'
date: 2022-12-25T14:00:00+02:00
draft: false
tags:
  - linux
  - wifi
---

Not all devices are capable of handling [captive
portals](https://en.wikipedia.org/wiki/Captive_portal). Problematic
devices usually include older hardware with outdated browsers, such as
"smart" TVs, gaming consoles and the like.

Regardless of the portal's purpose, whether it's to limit connection for
a specific time, or force end-users to accept some kind of agreement,
they usually work the same way: they force you through some kind of web
UI, and in the end it will validate your device by storing the MAC
address server-side.

A MAC address can be changed, which means that if you have a device that
cannot access the portal, you can still get that device onto the network
if you have a Linux machine that can:

- Find out the MAC address of the TV or other device
- Change your laptop's MAC to match the device
- Go through the validation process
- Change your laptop's MAC back to something else

So by masquerading your laptop as the other device, you can ensure that
MAC address gets whitelisted, giving your other device access.

## Step 1: Figure out the MAC address

You may be able to figure out the MAC of the device from a physical
sticker, or if it has a settings menu you can probably see it under
network settings. In this case, it's a Samsung TV where the built-in
browser can't handle the web portal. Let's call it `84:C0:EF:00:00:00`.

## Step 2: Change your laptop's MAC

In Linux, this can be done with `macchanger`, likely available from your
package manager. Remember to disable your wifi device first.

```bash
sudo macchanger --mac="84:C0:EF:00:00:00" wlp0s20f3
```

## Step 3: Authenticate

With your new MAC address, authenticate to the wifi just like you
otherwise would, or if you're cool, figure out the curl commands to do
it. "Network" under the developer console (F12) in Firefox is helpful
for this, and can export `POST` requests as curl which is convenient. It
might look something like this:

```bash
curl "$URL" -X POST -H 'Accept: */*' -H 'Accept-Language: en-US,en;q=0.5' \
-H 'Accept-Encoding: gzip, deflate, br' \
-H 'Referer: https://www.example.com/en/online-booking/Customer/EmailLogin?context=default' \
-H 'Content-Type: application/json' -H 'Origin: https://www.example.com' \
--cookie-jar '/tmp/cookiejar' \
--data-raw '{"Email":"foo@foo.foo","Password":"f00b4r","PersistentLogin":true,"IsModal":false}'
```

If there's multiple steps required, like also accepting terms of usage
after a login, the `--cookie-jar` flag is crucial here to allow the use
of `--cookie` in your next command:

```bash
curl "https://www.example.com/wifi/?terms=accepted" --cookie '/tmp/cookiejar'
```

This allows you to accept the terms with whatever cookies that were
given to you when logging in.

If the responses are JSON, you can just pipe them to `jq` to easily see
if all went OK.

## Step 4: Reset your MAC again

If you got access working with the modified address in Step 3, you can
now switch MAC again on your laptop. In this case, we'll just pick a
random one. Shut down your wireless device again, and run:

```bash
sudo macchanger -a wlp0s20f3
```

You can now re-authenticate your laptop, and when testing the other
device, it should be allowed through.

If not, you may need to disable the connection on that device and
re-connect to the network. At this point, there shouldn't be a portal in
the way.
