---
title: "Linux Sysadmin Scratchpad"
date: 2022-09-24T12:51:00+02:00
draft: false
tags:
    - sysadmin
    - linux
---

This page is a collection of useful commands or one-liners collected through the years. They are sorted in general categories, but I've attempted to describe them as well as I can so hopefully CTRL+F will work decently if you know what you're looking for.

This post will be updated in-place, refer to the date above.

## Converting Unix epoch time

If `1660000000` doesn't tell you much, here's a few conversion examples:

```
$ echo 1660000000 | perl -pe 'use POSIX qw/strftime/; \
s/(\d{10})/strftime("%Y-%m-%d %H:%M:%S",localtime($1))/e'
2022-08-09 01:06:40
```
Note that this prints `localtime()` which depends on your system, and looks for exactly 10 numbers.

If you have a log that begins with a very specific epoch timestamp syntax (nagios) this is an alternative way of doing it that also looks for brackets:

```
$ echo "[1660000000] foo" | perl -pe 's/\[(\d{10})]/localtime($1)/e'
Tue Aug  9 01:06:40 2022 foo
```

You can combine it with the above to get ISO-timestamps instead.

## Print a config file, but remove all comments (#) and empty rows

```
grep -vE '^[[:space:]]*#|^$' file
```

## Poor man's jq

If you're on a system without jq but you're just looking to make a json blob readable, you can use python's json.tool instead:

```
$ echo '{"bax":{"foo":"bar","baz":["ba","ba","ba"]}}' | python -m json.tool
{
    "bax": {
        "foo": "bar",
        "baz": [
            "ba",
            "ba",
            "ba"
        ]
    }
}
```

## Replace every instance of x in a file

```
sed -i 's/val=foo/val=bar/g' /etc/file
```

## Show frequently recurring lines in a log file

If you know that the timestamp is 14 characters long, this will cut out the timestamp and show you a count of the worst offenders:

```
cat file.log | cut -c14- | sort | uniq -c | sort | tail
```

## Test outbound connectivity on a specific port

Single port, or range of:
```
nc -zv host 80
nc -zv host 20-30
```

## Time travel

If your testing depends on the system clock being wrong, you can disable NTP and set it to whatever like this:

```
# timedatectl set-ntp 0
# timedatectl set-time '2016-12-13 13:45'
# date
Tue Dec 13 13:45:01 WST 2016
```

To re-enable NTP:

```
timedatectl set-ntp 1 && timedatectl --adjust-system-clock
```

## Push a thousand things to an API/config file

Useful for load testing, or just filling up a bunch of garbage.

* `JSON_DATA_OBJECT`: What you want to send to the API, in this case assumed JSON. If you need certain fields to be random, you could fill them with `$(cat /proc/sys/kernel/random/uuid)` for example.

The response is assumed to be JSON and piped for formatting.

```
#!/bin/bash
for i in $(seq 1 1001); do
   curl -sk -H 'content-type: application/json' \
   -d 'JSON_DATA_OBJECT' 'https://url/api' \
   -u 'user:password' | python -m json.tool
done
```

If you need to do a `POST` or some other type of request with no data to apply the change, just pass `-X POST` instead of `-d`ata.

#### Config file

To create a bunch of blocks with the expected syntax (here it's nagios), you can do:

```
#!/bin/bash
cd /somewhere

for i in $(seq 1 10001); do
    UUID=$(cat /proc/sys/kernel/random/uuid)
    echo "define host {
    use                            default-host-template
    host_name                      $UUID
    address                        127.0.0.1
    register                       1
    }" >> hosts.cfg
done
```

## Sort a file alphabetically by object name, not by line

Assume you have this:
```
gamma {
    banana
}

alpha {
    apple
    pear
}
```

How do you sort this alphabetically by `object{}`, not by line? There's always a million ways, but one way to do it is to replace all linebreaks with some kind of unique placeholder character that appears nowhere in the file, like `§`. This can be done in `vim` with:

```
:%g/.*{$/;/^}$/s/\n/§/
```

This gives us:

```
gamma {§    banana§}§ 
alpha {§    apple§    pear§}§
```

Note that this only works if `}` also has a newline after it. You can now sort it normally:

```
:%sort
```

When it's all sorted, restore the newlines by replacing the `§` characters:

```
:g/.*{/s/§/\r/g
```

## Create TAR on a remote system, but compress it locally

When bandwidth isn't the issue and you don't want to use up any space on the remote system, you may want to do the compression yourself locally and stream the tarball. If `sudo` is required, you can put it in a variable, but note that it will show up in the process list as long as the command is running.

`2>/dev/null` will hide the sudo prompt.

```
$ read -s sudopass
$ ssh you@host "echo $sudopass | \
sudo -S tar cf - /dir" 2>/dev/null | \
XZ_OPT='-9 -T0 -v' xz > dir.txz
```

Verify that the file has contents:

```
$ tar tvf dir.txz | head
```

You can also do the same only for a specific subset of files, for example all log files:

```
$ ssh you@host "echo $sudopass | \
sudo -S find '/dir' -name '*.log' | \
sudo tar -cf- -T-" | \
XZ_OPT='-9 -T0 -v' xz > logs.txz
```

## Encrypt a file with OpenSSL

If you're going to be throwing logs across the internet, it's probably a good idea to encrypt the file. One way to do this is:

```
$ openssl enc -e -aes-256-cbc -md sha512 -pbkdf2 \
-iter 10000 -in [PLAIN_FILE] -out [ENCRYPTED_FILE]
```

It will ask you for a passphrase. To decrypt, use the `-d` flag in an otherwise very similar command:

```
$ openssl enc -d -aes-256-cbc -md sha512 -pbkdf2 \
-iter 10000 -in [ENCRYPTED_FILE] -out [PLAIN_FILE]
```

Enter your passphrase and you'll have the decrypted file ready for decompression.

## Bash

Since `!!` refers to the previous command, you can re-run a failed command as root with:

```
$ sudo !!
```

So-called *brace expansion* is commonly used to move or copy one or many files as backups:

```
$ mv -v file{,.bak}
renamed 'file' -> 'file.bak'
```

For multiple files, `find` with `-exec` is a lot more flexible:
```
$ touch fakelog{1..10}.log          # create 10 fake log files
$ find . -type f -name '*.log'      # find all *.log files recursively
# now execute 'mv -v fakelog{1..10}.log fakelog{1..10}.log.bak' for every file found
$ find . -type f -name '*.log' -exec mv -v {} {}.bak \;
```

**Final advice** for everything bash:

Use [shellcheck](https://github.com/koalaman/shellcheck) when writing scripts, available as an extension in most editors. The [Google Shell Style Guide](https://google.github.io/styleguide/shellguide.html) isn't bad either.

## Product-specific: Salt-stack

If you don't use [salt](https://saltproject.io/whats-saltstack/), you can disregard this section.

#### Filtering by grains, and listing grains

```
# salt -C 'prefix-* and G@osmajorrelease:14' grains.get 'osrelease'
```

#### Apply a state only to nodes that have it

Get all states for a specific group of nodes:

```
# salt 'prefix-*' state.show_lowstate --out=json > out.json
```

Use `jq` to only return nodes that have a specific `state`:

```
cat out.json | \
jq -r 'select(.[][].__sls__ == "state") | keys[]' | \
sort -u
```

Wrangle this string to make it into a salt-compatible list (comma-separated), and then use that, ping to check before trying `state.apply`:

```
sudo salt -L 'host,host,host' test.ping
```