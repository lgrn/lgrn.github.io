---
title: 'Deploying FreeBSD on VMware'
date: 2024-09-21T11:45:00+02:00
draft: false
tags:
  - freebsd
  - vmware
  - sysadmin
---

This post is about deploying FreeBSD to a VMware environment, but since
there are many moving parts this may also be interesting in general to
anyone doing "infrastructure as code", cloud deployments etc.

The components involved are separated into chapters by chronological
order:

- Netbox (1)
- OpenTofu (2)
- cloud-init (3)
- VMware (4)

Since the entire process is pretty involved, this post only aims to give
a basic outline of how this can be done. If anything is unclear, or if
you figure out a better way to do something, feel free to contact me on
mastodon: [@linus](https://telegrafverket.cc/@linus)

If you only care about specific parts, feel free to read the sections
out of order, but there may be references to things in earlier sections
that are left unexplained.

### Netbox (1)

Netbox is a tool used for data center infrastructure management (DCIM),
which can mean a lot, but in this case it means acting as a source of
truth for information regarding virtual machines; such as their
hostname, interfaces with reserved IPs, OS versions etc.

As you will soon notice if you don't already know it, Netbox is very
opinionated, so fitting the data **you** want into Netbox will require
some "creativity", but in the end this cannot be helped for any DCIM
solution unless you want to write your own (please don't).

In my experience with Netbox so far, there are two important types of
Data in Netbox that are necessary to amend virtual machine objects with
extra information for deploys:

- [Custom
  Fields](https://netboxlabs.com/docs/netbox/en/stable/customization/custom-fields/)
- [Config
  Context](https://netboxlabs.com/docs/netbox/en/stable/models/extras/configcontext/)

"Custom Fields" will be accessible through API calls and can be used to
set extra attributes on VM objects that are not available in Netbox by
default, such as `operating_system`, `team_responsible` and so on. Tangentially, since about 2022, you can also set up "**custom
object** fields" to create relationships between objects, there's a
[YouTube video on that here](https://youtu.be/Vo0c9qw2L7Y).

"Config Context" is essentially a JSON blob that you
can fill with whatever you want, also accessible through the API, which
can be really useful when the data you need to store is a bit more
complicated than just one field of data related to a specific VM object.
You'll see an example of this later.

In simple terms, the main use of Netbox (or any DCIM) is that you can
create consensus on what is "true" and then trust this when you deploy,
avoiding the despair that comes with things like IP conflicts, "ghost
ship" VMs that noone is responsible for, and so on.

For simpler setups, just storing JSON data in git might be a better
solution, but the main benefit of web based applications like Netbox is
that the threshold for participation is a lot lower, which is pretty
important when you want a system that many people should respect as your
source of truth.

So, let's talk a little about the Netbox API. If your API query to
Netbox results in multiple hits, you will get a response that looks
something like:

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "vm1",
(...)
    },
    {
      "id": 2,
      "name": "vm2",
(...)
    }
  ]
}
```

Meaning you will have to iterate over `results`, while using an endpoint
like `/api/virtualization/interfaces/?virtual_machine_id=N` will give
you just one result. Let's have look at this one without the redactions:

```json
{
  "id": 1,
  "name": "vm1",
  "status": {
    "label": "Active",
    "value": "active"
  },
  "cluster": {
    "id": 3,
    "name": "Cluster 1"
  },
  "interfaces": [
    {
      "id": 10,
      "name": "eth0",
      "mac_address": "00:50:56:8a:00:01",
      "mtu": 1500,
      "description": "",
      "mode": null
    },
    {
      "id": 11,
      "name": "eth1",
      "mac_address": "00:50:56:8a:00:02",
      "mtu": 1500,
      "description": "",
      "mode": null
    }
  ]
}
```

This leads to the first pain point if you are deploying VMs from Netbox:
while querying a VM will return its interfaces, it will not return any
IPs on those interfaces. To get them, you must perform additional API
lookups targeting the IDs of any interfaces returned:

```json
{
  "id": 10,
  "name": "eth0",
  "virtual_machine": {
    "id": 1,
    "name": "vm1"
  },
  "mac_address": "00:50:56:8a:00:01",
  "mtu": 1500,
  "description": "",
  "mode": null,
  "assigned_ips": [
    {
      "id": 101,
      "address": "192.168.1.100/24",
      "family": 4
    }
  ]
}
```

I won't go into this much more apart from saying that in my experience,
to be able to deploy effectively from Netbox, you need to write
your own code that either performs multiple API calls when deplying, or
creates your own data structure that you can pass to whatever will
handle the deployment.

At this point, it might strike the reader that spending time writing
this probably does not make sense for smaller or individual use cases,
and you would be completely correct. For this reason, we will end the
Netbox section on a sort of "[how to draw an
owl](https://knowyourmeme.com/memes/how-to-draw-an-owl)" note:

Below is the custom built data structure that will be used for the rest
of this post; whether it's generated by some really cool code that
performs multiple API calls and smashes it together, or just
put together manually by you, doesn't really matter:

```json
{
  "1234": {
    "name": "hostname.fqdn",
    "cluster_name": "test-cluster",
    "status": "staged",
    "id": 1234,
    "cluster_id": 29,
    "tenant_id": 277,
    "platform_id": 21,
    "disk": 10,
    "memory": 1024,
    "vcpus": 1,
    "tags": ["test-tag"],
    "custom_fields": {
      "server_os": "freebsd14"
    },
    "config_context": {
      "my-context": {
        "interfaces": {
          "vmx0": {
            "gateway": "192.168.1.1",
            "vmware_network": "my-vmware-network",
            "vmware_switch": "my-vmware-switch"
          }
        },
        "vmware_datastore": "my-datastore"
      }
    },
    "interfaces": {
      "1337": {
        "ip": "192.168.1.100/24",
        "ip_id": 28984,
        "type": "virtualization.vminterface",
        "name": "vmx0",
        "vmware_network_name": "my-vmware-network",
        "vmware_switch_name": "my-vmware-switch",
        "gateway": "192.168.1.1"
      }
    }
  }
}
```

That's quite the JSON, so this requires some explanation:

- `1234` is the VM object ID from netbox, used as a key.
- Most of the following fields like `name`, `memory` and so on are
  vanilla Netbox fields that are available on a VM.
- The `custom_fields` part will be provided to you by Netbox, and this
  is where you can specify your own data for VMs, but only in a sort of
  key/value fashion.
- The `config_context` is a JSON object that you yourself define in
  Netbox however you want. In this case it is being used to amend VMware
  specific information for every interface on the VM itself. There are
  probably other ways to do this, like custom fields on an interface.
- The `interfaces` part is completely synthetic, and simply generated
  from the information provided by the `config_context` matched with the
  interface information from the Netbox API.

Leaving aside the elephant in the room for now how this JSON is actually
put together in an automated way (maybe a subject for a future blog
post), regardless of how it was put together we now have more or less everything we need in terms of VM
information to move on.

### OpenTofu (2)
