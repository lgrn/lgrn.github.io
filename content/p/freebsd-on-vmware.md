---
title: 'Deploying FreeBSD on VMware'
date: 2024-09-23T11:45:00+02:00
draft: false
tags:
  - freebsd
  - vmware
  - sysadmin
  - linux
  - cloud-init
---

This post is about multiple components involved in deploying FreeBSD to
a VMware environment. Since there are many moving parts this may also be
interesting in general to anyone doing "infrastructure as code" and
cloud deployments, the process is quite similar for Linux.

_Revision: 2024-09-23 (#1)_ --- changelog at the end.

The components involved are separated into chapters by chronological
order:

- [Netbox (1)](#netbox-1)
- [OpenTofu (2)](#opentofu-2)
- [cloud-init (3)](#cloud-init-3)
- [VMware (4)](#vmware-4)

Since the entire process is pretty involved, this post aims to give a
basic outline of how this can be done. If anything is unclear, or if you
figure out a better way to do something, feel free to contact me on
mastodon: [@linus](https://telegrafverket.cc/@linus)

Feel free to read the sections out of order if you prefer, but there may
be references to things in earlier sections that are left unexplained.

### Netbox (1)

Netbox is a tool used for data center infrastructure management (DCIM),
which can mean a lot, but in this case, it means acting as a source of
truth for information regarding virtual machines: hostnames, interfaces
with reserved IPs, OS versions etc.

Netbox is pretty opinionated, so fitting the data **you** want into
Netbox might require some "creativity", but in the end this probably
cannot be helped for any DCIM solution unless you want to write your own
(please don't).

All in all, Netbox is pretty good, but I believe it was originally
created to keep track of network information (as the name might
suggest), and it shows. Wrestling with the API when it comes to virtual
machines is not a very enjoyable experience, but to my knowledge it's
one of the most common solutions out there, and when it comes to
_replacing_ a DCIM solution, just know that whatever pros you may have
found, embarking on that quest means most of your colleagues will
probably hate you. To me, Netbox is "good enough", which is often more
than you can hope for.

In my experience with using Netbox for VM deployments so far, there are
two important types of data that are necessary to amend objects with
extra information for deploys:

- [Custom
  Fields](https://netboxlabs.com/docs/netbox/en/stable/customization/custom-fields/)
- [Config
  Context](https://netboxlabs.com/docs/netbox/en/stable/models/extras/configcontext/)

"Custom Fields" will be accessible through API calls and can be used to
set extra attributes on VM objects that are not available in Netbox by
default, such as `operating_system`, `team_responsible` and so on.
Tangentially, since about 2022, you can also set up "custom object
fields" to model relations between objects rather than just setting
string values in a custom field, there's a [YouTube video on that
here](https://youtu.be/Vo0c9qw2L7Y).

"Config Context" is essentially a JSON blob in Netbox that you can fill
with whatever you want, also accessible through the API, which can be
really useful when the data you need to store is a bit more complicated
than just one field of data related to a specific VM object (like
`ticket_id: 1234`). You'll see some examples of this later.

In simple terms, the main use of Netbox (or any DCIM) is that you can
create consensus on what is "true" and then trust this when you deploy,
avoiding the despair that comes with things like IP conflicts, "ghost
ship" VMs that noone is responsible for, and so on.

For simpler setups, just storing JSON data in git might be a better
solution, but the main benefit of web based applications like Netbox is
that the threshold for participation is a lot lower, which is pretty
important when you want a system that many people should respect as your
source of truth. If everyone involved knows git, maybe just start there.

Let's talk about the Netbox API and how it can be a bit difficult for VM
deployments. First of all, let's just look at the structure: if your API
query to Netbox results in multiple hits, you will get a response that
looks something like:

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

Meaning you will have to iterate over `results`, while using a more
specific endpoint querying an "id" will give you just one result (since
an id is unique). Let's have look at this example without the
redactions:

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

Ok, so we're looking at a VM that is "active", it's assigned to a
cluster and has two interfaces. Is this enough to deploy? Probably not
(and for VMware, definitely not). This leads to the first pain point if
you are deploying VMs from Netbox: while querying a VM will return its
interfaces, it will not return any IPs on those interfaces. To get them,
you must perform additional API lookups targeting the IDs of any
interfaces returned:

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

So a VM is an object, an interface is an object (related to a vm), but
only the interface has a relation to an ip, which is also an object.

I won't go into this much more apart from saying that in my experience,
to be able to deploy effectively from Netbox, you need to write your own
code that either performs multiple API calls when deplying, or creates
your own data structure that you can pass to whatever will handle the
deployment.

At this point, it might strike the reader that spending time writing
this probably does not make sense for smaller or individual use cases,
and you would be completely correct. For this reason, we will end the
Netbox section on a sort of "[how to draw an
owl](https://knowyourmeme.com/memes/how-to-draw-an-owl)" note:

After either creating it manually, or pain-stakingly writing code to
generate it for you, below is the custom built data structure that will
be used for the rest of this post; whether it's generated by some really
cool code that performs multiple API calls and smashes it together, or
just comes from a git repo, doesn't really matter:

```json
{
  "1234": {
    "name": "hostname.fqdn",
    "cluster_name": "test-cluster",
    "provided_cluster_name": "testcluster12",
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
      "server_os": "freebsd14",
      "service_id": 100200
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

This gives us everything we need to be able to deploy. Some of the
values will become clearer as we go along, but here's a short summary:

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

Examples of how this might be generated automatically from Netbox might
be the subject of a future blog post, but I assure you it would probably
be as long as this entire post, so we'll skip that for now.

### OpenTofu (2)

OpenTofu was forked from Terraform in 2023, when the latter stopped
being free and open source software with a license change. Let's call it
Tofu for short. It's a tool for "infrastructure as code", and if you've
never used it, it may seem confusingly similar to "configuration
management" tools like Ansible or Salt.

While it's true that they share some similarities (depending on how you
use configuration management), in my experience Tofu is nicer to use for
the "deployment", and if you wish the "state management" of those
deployments, since that is essentially all it does, and it does it
pretty well. Ideas that you'll find in "config management" like
**repeatedly** ensuring that your `sshd_config` files look the same
across all servers are nowhere to be found here, it's all about writing
general rules and attributes for things like VMs and virtual networks
from the perspective of the hypervisor.

There won't be much handholding on how to use Tofu here (there's plenty
of documentation and other resources available), but I'll give a general
overview on how configuration might look, and some neat functionality
you can use.

First of all, your `main.tf` file would look something like this:

```hcl
terraform {
  required_version = "1.8.2"
  required_providers {
    vsphere = {
      source  = "hashicorp/vsphere"
      version = "~> 2.9.1"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5.1"
    }
    cloudinit = {
      source  = "hashicorp/cloudinit"
      version = "~> 2.3.4"
    }
  }
}
```

This lets you pin both the required Tofu version, as well as the
required versions of the "providers" used when you initialize it for the
first run. These providers do pretty much what they sound like,
`vsphere` lets you deploy stuff to VMware, `local` lets you handle local
files (like the JSON above), and `cloudinit` helps you put together
templates into the obscure black magic that is base64 encoded, gzipped
strings of init instructions (yes, I'm serious).

You would then configure the provider like so:

```hcl
provider "vsphere" {
  user                 = var.vsphere_user
  password             = var.vsphere_password
  vsphere_server       = var.vsphere_server
  allow_unverified_ssl = true
}
```

Where `var.` refer to variables you have set in `terraform.tfvars`.
Providers are usually well documented, just have a look at the [2.9.1
docs
here](https://registry.terraform.io/providers/hashicorp/vsphere/2.9.1/docs)
for example.

When using providers, you will quickly encounter two object types:
`resource`, which refers to a "thing" that should be created (or exist)
such as a server or a virtual network, and `data` which refers to
existing information "objectified".

The syntax is pretty much:

```hcl
data "provider_existing_thing" "your_name" {
  (...)
}
```

Or as exemplified in the above documentation:

```hcl
data "vsphere_datacenter" "dc" {
  name = "dc-01"
}
```

You would then refer to this object as `data.vsphere_datacenter.dc`.

You might be half asleep at this point, so let's look at a more exciting
example:

```hcl
data "vsphere_compute_cluster" "cluster" {
  for_each      = local.unique_cluster_list
  name          = each.key
  datacenter_id = data.vsphere_datacenter.dc.id
}
```

The definition should be obvious enough, but the first line is more
interesting: `for_each` starts a loop over whatever is found in
`local.unique_cluster_list`, which is (as you may have already
suspected) a list. It also says this cluster is in the datacenter
specified by "id" in the `data.vsphere_datacenter.dc` object that we
manually defined just before --- note that we did not specify the id, it
was fetched from VMware based on the information we gave. Now, let's
look at the definition of this "unique cluster list". In `main.tf` it
could look something like this:

```hcl
locals {
  fetched_vms = jsondecode(
  data.local_file.fetch_netbox.content
  )
  unique_cluster_list = toset([
  for _,v in local.fetched_vms :
  v.provided_cluster_name
  ])
}
```

This might look intimidating, but it's not that complicated:

- `fetched_vms` is defined as the result of calling `jsondecode()` on an
  object which has loaded a local JSON file with the help of
  `local_file` from the `local` provider.
- `unique_cluster_list` begins with the `for _,v` (key, value where
  "key" is discarded) loop over the parsed JSON, extracting the
  `v.provided_cluster_name` from every VM. You can see this value in the
  JSON above. `toset()` converts this to a set, which will remove any
  duplicate values.

This means that one "cluster object" will be defined in Tofu for every
unique string found in the `provided_cluster_name` values of the N
virtual machines passed in by the JSON, with each having `name =
each.key`, which should mean that we can safely refer to any cluster we
expect to exist as object `data.vsphere_compute_cluster.cluster["name"]`

This might seem overkill, but if you want your config to be generally
useful rather than repetetive and hard-coded (which can be fine
depending on the circumstance), loops are essential. If you don't need
them, just create your objects manually and refer to them directly.

There's a few more things we need to go through before looking at the VM
definition itself, and one of them is "templates". This is an almost
criminally confusing word, but in this case we are speaking very
specifically about `vsphere_virtual_machine.template` which refers to a
_virtual machine template_ on the VMware side of things. In simple
terms, it's a VM that we've prepared and turned read-only.

When we create a new VM, we do so from a template, but if you have
multiple templates you need to decide which one to use. One way to do
this could be another `for_each` that uses the `server_os` custom field
handily available from Netbox:

```hcl
data "vsphere_virtual_machine" "templates" {
  for_each = {
    freebsd14  = "freebsd14_template"
    freebsd13  = "freebsd13_template"
  }
  name          = each.value
  datacenter_id = data.vsphere_datacenter.dc.id
}
```

In a sense, this is a mapping, which helps us figure out what template
to use by simply passing `server_os` as the index to this
`vsphere_virtual_machine.templates` object --- as long as that value is
one we have mapped, that is.

Let's jump into what defining a VM might look like. We still need to go
through how it's initialized, but that will come later.

This section is quite long, so I'll use some inline comments to make a
few short clarifications as we go.

```hcl
resource "vsphere_virtual_machine" "vm" {
  for_each = {
  for k, v in local.fetched_vms :
  k => v
  if (v.platform_id == 20 || v.platform_id == 21)
  }
  // for_each grabs key,value from fetched_vms, and creates a new map,
  // in practice "passing", if the platform_id from netbox is one we want.
  // this is only useful if they might differ, like linux and freebsd.
  name     = "${each.value.custom_fields.service_id == null ? "XXX" : each.value.custom_fields.service_id}-${each.value.name}"
  // vm name is set by combining values from fetched_vms, this example checks
  // if service_id is missing, and if so replaces it with "XXX"
  // note 1: at least in vmware, the name can be anything and is not
  // tied to the actual hostname of the server.
  // note 2: name must be unique, deploying with a name matching an
  // existing vm will fail.
  guest_id = data.vsphere_virtual_machine.templates[each.value.custom_fields.server_os].guest_id
  // vmware specific, this essentially means "just use whatever
  // the template we're basing this VM on has"
  datastore_id               = data.vsphere_datastore.datastore[each.value.vmware_datastore].id
  resource_pool_id           = data.vsphere_compute_cluster.cluster[each.value.provided_cluster_name].resource_pool_id
  num_cpus                   = each.value.vcpus
  memory                     = each.value.memory
  wait_for_guest_net_timeout = 0
  wait_for_guest_ip_timeout  = 0
  dynamic "network_interface" {
    for_each = local.fetched_vms[each.key]["interfaces"]
    // iterate over interfaces in this VM iteration
    content {
      network_id = data.vsphere_network.network[network_interface.key].id
    }
  }
  disk {
    label        = "tfd0"
    size         = each.value.disk
    datastore_id = data.vsphere_datastore.datastore[each.value.vmware_datastore].id
  }
  clone {
    template_uuid = (each.value.custom_fields.server_os != "" ? data.vsphere_virtual_machine.templates[each.value.custom_fields.server_os].id : null)
    // make sure the server_os value is not empty: if it's not, grab the
    // template that matches server_os
  }
  extra_config = {
    // these 'configuration parameters' are visible under
    // edit settings > advanced > configuration parameters in vcenter.
    "guestinfo.userdata"          = data.template_cloudinit_config.user_data[each.key].rendered
    "guestinfo.userdata.encoding" = "gzip+base64"
    "guestinfo.metadata" = base64encode(templatefile("templates/metadata.tftpl",
      {
        netbox_id = local.fetched_vms[each.key]["id"]
        hostname  = local.fetched_vms[each.key]["name"]
    }))
    "guestinfo.metadata.encoding" = "base64"
  }
  depends_on = [
    data.local_file.fetch_netbox,
    data.vsphere_network.network,
    local.fetched_vms,
    data.template_cloudinit_config.user_data,
  ]
}
```

There are probably at least two major things that are unfamiliar with
this configuration:

- Defining a `vsphere_network`
- Passing `template_cloudinit_config` for initialization

Since cloud-init has its own section below, let's focus on networks for
now. But first, a short tangent regarding `depends_on`:

Tofu is written in Go, which is great at running things in parallel,
which Tofu does, but in many cases you want to make sure that some stuff
has already happened before you attempt to create the VM. In this
example, this "depends_on" section has been very much left to marinate
due to the fact that it's "working", but it probably has redundancies.
An exercise to the reader, if you will.

Ok, back to networks. We are creating one `network_interface` for each
thing we find in "interfaces" in our JSON blob with the help of a
[dynamic
block](https://developer.hashicorp.com/terraform/language/expressions/dynamic-blocks)
which lets us use a loop. So far so confusing, but what about the
`vsphere_network` object it refers to by `network_id`?

Again, unfortunately, we need to dive into some complexity. Here is the
definition of the network object itself, after the virtual switches:

```hcl
data "vsphere_distributed_virtual_switch" "vds" {
  for_each      = local.unique_vswitch_list
  name          = each.key
  datacenter_id = data.vsphere_datacenter.dc.id
}

data "vsphere_network" "network" {
  for_each = { for x in local.iface_network_map : x.interface_id => {
    vmware_switch_name  = x.vmware_switch_name,
    vmware_network_name = x.vmware_network_name
  } }
  name                            = each.value.vmware_network_name
  datacenter_id                   = data.vsphere_datacenter.dc.id
  distributed_virtual_switch_uuid = data.vsphere_distributed_virtual_switch.vds[each.value.vmware_switch_name].id
}
```

Again we have `local.` variables, contained in the same `local{}` block
mentioned before in `main.tf`:

```hcl
  unique_vswitch_list = toset(distinct(flatten(
    [for k, v in local.fetched_vms : [for i, j in v.interfaces : j.vmware_switch_name]]
  )))

  iface_network_map = flatten([for k, v in local.fetched_vms : [
    for i, j in v.interfaces : {
      "interface_id" : i,
      "vmware_network_name" : j.vmware_network_name,
      "vmware_switch_name" : j.vmware_switch_name,
  }]])
```

I'm not even going to pretend I remember what I was thinking when I
wrote this, but at least the purpose of this list and map are pretty
clear:

- `unique_vswitch_list` ensures we have a list of every unique vswitch
  mentioned in the incoming JSON data (it's called `vmware_switch_name`
  there)
- `iface_network_map` ensures we have a map where we, by id, can look up
  the name of the vmware network and the associated switch for any
  interface.

A "network" on the vmware side is, and this may shock you, virtual. In a
sense I guess all networks are virtual, but this is really very virtual,
and so is the switch it's related to.

In order to _uniquely_ identify a network in VMware, we need both the
name of the network and its associated switch, which is why we first
create the `data.vsphere_distributed_virtual_switch` object(s), so that
they can be used when defining the network object(s), as they want
`distributed_virtual_switch_uuid`.

So when we define our VM, and create our interfaces like so:

```hcl
// this part was already shown above
  dynamic "network_interface" {
    for_each = local.fetched_vms[each.key]["interfaces"]
    content {
      network_id = data.vsphere_network.network[network_interface.key].id
    }
  }
```

When we define what network the interface should connect to, this
already exists as an object that we can look up with
`network_interface.key` and get the `.id` of, because we set that key
ourselves in the for loop when creating the networks: `x.interface_id =>
{...}`

If you feel confused at this point, don't worry: I wrote this and it's
confusing to me too, but really the only way to understand what is
happening here is to attempt to configure it yourself and fail about a
hundred times. Also, you don't have to use for loops, if you've never
used Tofu before, just defining the objects statically without any
looping is probably a better way to start --- and actually, this is the
type of configuration you'll usually find in the documentation for the
providers themselves (which I highly recommend you read).

All right, since we now know everything there is to know about virtual
networks in VMware (to be clear, this is sarcasm), let's move on to
cloud-init.

### cloud-init (3)

There are few technologies, and maybe even just things in general, that
have caused more feelings of frustration, despair, self loathing and
loud volume black metal sessions for me than cloud-init.

If you have no idea what cloud-init is, count yourself lucky, but you
won't be lucky for long because I'm about to tell you.

According to their own documentation, cloud-init is:

> _the industry standard multi-distribution method for cross-platform
> cloud instance initialisation_

Those are some pretty big words, but the worst part is that they're
right. It's not only the most widely used, it's also several hundred
megabytes to install, depends on python, only takes YAML, contains
dozens of modules all enabled by default to be able to "platform
independently" change your hostname, and about 60% of the time, it works
every time.

Regardless of the abusive relationship that cloud-init has forced me
into over the years, it does the trick, and it is actually cross
platform: if you learn it because you need it on VMware, you can, in
fact, re-use that knowledge when you encounter OpenStack, AWS, or
something else. Compared to [Microsoft answer
files](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/update-windows-settings-and-scripts-create-your-own-answer-file-sxs?view=windows-11),
it's probably like eating ice cream on a beach (don't click that link).

So, I'm not going to show you basic examples of how to use cloud-init,
those are everywhere on the Internet and for the purpose of this post,
we're talking about deploying FreeBSD on VMware. I am also mindful of
the fact that after more than 600 lines, this is the first time I'm
mentioning FreeBSD, but we will have plenty of time to focus on that
later when we talk about VM templates in the VMware section.

The first thing to understand is that Tofu has a templating language,
similar but not identical to
[Jinja](https://palletsprojects.com/projects/jinja/), with the
delightful file ending `.tftpl`, and we will use this to create our
cloud-init payloads.

In a very simplified sense, cloud-init works something like this:

- A cloud-init datasource specific for the hypervisor/environment in
  question fetches the "payload". In this scenario, we are using the
  [VMware](https://docs.cloud-init.io/en/latest/reference/datasources/vmware.html)
  datasource, which depends on `open-vm-tools`.
- The "payload" can arrive in many different ways, anything from HTTP to
  a mounted cdrom device, or as in this case, by simply looking up
  key/value-stuff in VMware.
- cloud-init runs through the modules it is configured to run, and "does
  stuff" depending on what instructions it finds in the payload.

The configuration in Tofu is actually pretty brief, but a lot is
happening behind the scenes:

```hcl
// already shown previously as a part of vm creation
  extra_config = {
    "guestinfo.userdata" = data.template_cloudinit_config.user_data[each.key].rendered
    "guestinfo.userdata.encoding" = "gzip+base64"
    "guestinfo.metadata" = base64encode(templatefile("templates/metadata.tftpl",
      {
        netbox_id = local.fetched_vms[each.key]["id"]
        hostname  = local.fetched_vms[each.key]["name"]
    }))
    "guestinfo.metadata.encoding" = "base64"
  }
```

We are passing "userdata" and "metadata", the former being a compressed
base64 string, and the latter just base64. Since formatting cloud-init
payloads is _not fun_, it's very convenient that
`template_cloudinit_config` helps us generate this. Here's what it looks
like:

```hcl
data "template_cloudinit_config" "user_data" {
  gzip          = true
  base64_encode = true
  for_each      = local.fetched_vms
  part {
    content_type = "text/cloud-config"
    content = (templatefile("templates/user-data.tftpl",
      {
        ifaces    = local.fetched_vms[each.key]["interfaces"]
        hostname  = local.fetched_vms[each.key]["name"]
        server_os = local.fetched_vms[each.key]["custom_fields"]["server_os"]
      }
    ))
  }
  part {
    content_type = "text/x-shellscript"
    content = (templatefile(
      "${lookup({
        "freebsd13"  = "templates/bootstrap.sh_freebsd13.tftpl",
        "freebsd14"  = "templates/bootstrap.sh_freebsd14.tftpl",
      }, local.fetched_vms[each.key]["custom_fields"]["server_os"], "NO_TEMPLATE_FOUND")}",
      {
        hostname  = local.fetched_vms[each.key]["name"]
        server_os = local.fetched_vms[each.key]["custom_fields"]["server_os"]
        ifaces    = local.fetched_vms[each.key]["interfaces"]
      }
    ))
  }
}
```

The observant reader notices that again, we are fully enjoying loops,
and this is because each VM requires a separate template: it _will_
contain very instance-specific information, such as hostnames.

You may also have noticed that this object has two "parts", one
`text/cloud-config` (the user-data), and one `text/x-shellscript`, which
unsurprisingly contains a shell script.

The steps are not that complicated as soon as you understand the syntax:

- `user-data.tftpl` is a template that is rendered and gets passed the
  `ifaces`, `hostname` and `server_os` variables.
- depending on the `server_os` of the VM, it gets passed one of two
  shell script templates, which in turn gets the same three variables,
  in a different order just to keep things confusing.

A more direct example of template generation is shown when setting
`guestinfo.metadata` in the VM creation.

Here's what `user-data.tftpl` might look like:

```yaml
hostname: "${hostname}"
keyboard:
  layout: "se"
locale: "en_US.UTF-8"
users:
  - default
  - name: "foo"
    lock_passwd: false
    # passwd: echo "something" | mkpasswd -m sha-512 -s
    passwd: "$6$15(...)"
    sudo: "ALL=(ALL) NOPASSWD:ALL"
%{ if server_os != "freebsd14" ~}
    shell: "/bin/bash"
%{ endif ~}
    ssh_authorized_keys:
      - "ssh-ed25519 AAAAC3N(...)"
      - "ssh-ed25519 AAAAC3N(...)"
```

Pretty basic stuff, and probably not dissimilar to many user-data
examples you'll find online (apart from the tftpl syntax).

Now to a point of contention: if you ask the internet, it will tell you
that user-data is an excellent place to define pretty much everything,
be it network interfaces, static routes, package upgrades and anything
else your heart may desire. I am here to tell you that these are lies,
and that they will lead you down a very dark path. You are free to take
it, but you have been warned.

In my opinion, if you want to "do stuff" in an automated fashion on
pretty much any \*NIX system, you can do it with shell scripts --- and
if you can't do it with shell scripts, maybe it's not worth doing.

You might think to yourself that doing things like interface
configuration or software updates in a shell script is stupid, because
you should do it the "right way" through the tool you are using, and if
I hadn't tried it myself I'd probably agree with you: instead I'd invite
you to not contact me about this and move immediately to trying this out
yourself by configuring interfaces, multiple conditional routes and
package updates on Ubuntu, Rocky and FreeBSD using only YAML and then
get back to me with what your new favorite black metal album and
preferred form of nicotine is.

We're doing shell scripts. Here's an example of how
`bootstrap.sh_freebsd14.tftpl` might look:

```sh
#!/bin/sh
log() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $*" | tee -a /var/log/bootstrap.log
}
err() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] [ERROR]: $*" | tee -a /var/log/bootstrap.log >&2
}
panic() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] [PANIC]: $*" | tee -a /var/log/bootstrap.log >&2
  exit 1
}

log "started running on ${hostname}"
log "netbox says: '${server_os}'."

log "setting default keymap to 'se'."
sysrc keymap="se"

log "setting hostname to '${hostname}'."
sysrc hostname="${hostname}"

log "assuming ZFS root filesystem on /dev/da0p5."
log "attempting resize and enabling compression."

if zpool status; then
  gpart recover /dev/da0 2>&1 | tee -a /var/log/bootstrap.log
  gpart resize -i 4 da0 2>&1 | tee -a /var/log/bootstrap.log
  zpool set autoexpand=on zroot 2>&1 | tee -a /var/log/bootstrap.log
  zpool online -e zroot /dev/da0p4 2>&1 | tee -a /var/log/bootstrap.log
  zfs set compression=lz4 zroot 2>&1 | tee -a /var/log/bootstrap.log
  log "resized ZFS root partition, compression set."
else
  err "ZFS operations failed, not ZFS?"
fi

log "replacing /etc/ssh/sshd_config."
cat << EOF > /etc/ssh/sshd_config
# restrict connections to ipv4
AddressFamily inet
Ciphers aes256-gcm@openssh.com,aes128-gcm@openssh.com
ClientAliveCountMax 3
ClientAliveInterval 300
Compression delayed
DisableForwarding yes
HostKey /etc/ssh/ssh_host_ed25519_key
HostKeyAlgorithms ssh-ed25519
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com,umac-128-etm@openssh.com
KbdInteractiveAuthentication no
KexAlgorithms sntrup761x25519-sha512@openssh.com,curve25519-sha256,curve25519-sha256@libssh.org,diffie-hellman-group18-sha512,diffie-hellman-group16-sha512
LoginGraceTime 30
LogLevel VERBOSE
MaxAuthTries 1
MaxStartups 3:30:10
PasswordAuthentication no
PermitRootLogin without-password
PermitTunnel no
Port 22
PrintMotd no
RekeyLimit 500M 60m
Subsystem       sftp    /usr/lib/openssh/sftp-server
TCPKeepAlive no
UseDNS no
UsePAM yes
VersionAddendum "SSH-2.0-Protocol"
X11Forwarding no
# ListenAddress is amended below

EOF

# begin interface loop
%{ for k,v in ifaces ~}
log "configuring interface ${v.name}."
sysrc ifconfig_${v.name}="inet ${v.ip}" 2>&1 | tee -a /var/log/bootstrap.log

%{ if can(v.gateway) ~}
log "${v.name} gave us default gateway ${v.gateway}"
sysrc defaultrouter="${v.gateway}" 2>&1 | tee -a /var/log/bootstrap.log
%{ endif ~}

%{ if v.name == "vmx0" ~}
log "special case for vmx0: 10.1.0.0/16 via ${cidrhost(v.REDACTED, 1)}"
sysrc route_specialcase="-net 10.1.0.0/16 ${cidrhost(v.REDACTED, 1)}" 2>&1 | tee -a /var/log/bootstrap.log
sysrc static_routes+="specialcase" 2>&1 | tee -a /var/log/bootstrap.log
log "adding sshd ListenAddress for vmx0 ip"
echo "ListenAddress ${split("/", v.ip)[0]}" | tee -a /etc/ssh/sshd_config
%{ endif ~}

%{ if can(v.routes) ~}
%{ for to,via in v.routes ~}
log "adding netbox static route: ${to} via ${via}"
sysrc route_${replace(replace(to, ".", "_"), "/", "_")}="-net ${to} ${via}" 2>&1 | tee -a /var/log/bootstrap.log
sysrc static_routes+="${replace(replace(to, ".", "_"), "/", "_")}" 2>&1 | tee -a /var/log/bootstrap.log
%{ endfor ~}
%{ endif ~}

%{ endfor ~}

log "restarting netif and routing."
service netif restart 2>&1 | tee -a /var/log/bootstrap.log
service routing restart 2>&1 | tee -a /var/log/bootstrap.log

# freebsd global DNS config
log "adding external DNS entries."
echo "nameserver 8.8.8.8" | tee /etc/resolv.conf
echo "nameserver 1.1.1.1" | tee -a /etc/resolv.conf

log "verifying network access, waiting for ping response using DNS (google.se)."
COUNT=0
while ! ping -c 1 google.se > /dev/null 2>&1; do
  sleep 1
  COUNT=$((COUNT + 1))
  if [ $COUNT -gt 10 ]; then
    panic "ping response failed, final pkg step will not happen. bailing out."
  fi
done

# VERIFY PACKAGES BEFORE ADDING: one incorrect package will break install
PACKAGES="bind-tools vim nano tree htop curl tmux terminfo-db"

log "updating all current packages with pkg."
pkg update 2>&1 | tee -a /var/log/bootstrap.log
pkg upgrade -y 2>&1 | tee -a /var/log/bootstrap.log

log "installing packages: '$PACKAGES'."
pkg install -y $PACKAGES 2>&1 | tee -a /var/log/bootstrap.log

log "enable sshd before reboot."
sysrc sshd_enable="YES" 2>&1 | tee -a /var/log/bootstrap.log

# user-data created the "foo" user for us
log "disabling and locking root user (bsd)"
pw lock root
pw usermod root -s /usr/sbin/nologin

SIGNOFF="finished on ${hostname}. rebooting."
log "$SIGNOFF"
shutdown -r now "$SIGNOFF"
```

Hopefully, this illustrates some of the benefits of using shell scripts:

- You can set up your own logging
- You can loop over and re-use incoming data freely without having to
  generate YAML (this will hurt you)
- You can handle errors
- It works, because it does exactly what you tell it
- It breaks for the same reason

At the end of the day, I'd rather troubleshoot **small** init scripts
than trying to understand why one specific cloud-init module isn't
working as expected on one specific OS. I'm not saying this is the best
way to do it, only that in my experience you can only take so much of
having to scrap all your work because it worked for A but breaks with B,
and if you want to move on you need to patch a cloud-init module.

Of course, I understand shell scripts aren't for everyone or every
situation, so until you experience the same frustration, which might be
never, feel free to try out one of [the many modules available by
default](https://cloudinit.readthedocs.io/en/latest/reference/modules.html).

Saving the best for last, let's move on to the part that actually has a
little do with FreeBSD: VMware and creating VM templates.

### VMware (4)

In order to deploy a VM in VMware, you need to have either a template,
or an existing VM to clone. In reality, as far as I can understand at
least, these two things are essentially the same thing, only that
templates are "read only".

There are many fun file formats to choose from, but these are the most
common you will probably come across, in no particular order:

- `QCOW2`: The QEMU copy on write format, perhaps the most commonly
  available, and the one I pick for FreeBSD and Rocky.
- `VMDK`: The virtual machine disk format, developed by VMware, it's
  somewhat less commonly available but can be easily converted into from
  QCOW2.
- `OVA`: Usually only available for Ubuntu, a lot easier if you're stuck
  with VMware, but pretty uncommon.

Now, before you say anything, I am well aware that there are third party
sites that offer things like OVA files for FreeBSD, even though they're
not officially available. My personal opinion is that using these is
bordering on insane, as you're giving up the safety of getting your OS
images directly from the source for a little bit of comfort --- and to
paraphrase what someone once said: those who gives up security for
comfort deserves neither. I'm not accusing anyone of anything, I'm sure
they're fine, but I won't use them, and if you wanted to spread a
rootkit around it sure would be a great way to do it.

The process of creating these templates is done on Linux. Unfortunately
I don't really know what the equivalent commands would be for FreeBSD,
but if you want me to add them feel free tell me what they are, because
I don't use FreeBSD as a desktop OS.

The process I'm currently using for creating FreeBSD templates isn't
exactly painless, but it isn't too bad either considering you won't be
doing it that often:

- Download your cloud image [from the official
  website](https://download.freebsd.org/ftp/releases/VM-IMAGES/),
  matching the architecture and file system you want.
- FreeBSD specifically does offer VMDK files, but some operating systems
  do not (I think Rocky is one), so we'll use the QCOW2 and convert it,
  just to show an example of how.
- Unpack the file if necessary.

The first thing we'll do is increase the allowed disk space usage, since
it by default is pretty close to full, and we will need to install a bit
of stuff. You can probably get away with less but I prefer expanding it
with at least 5G:

```bash
qemu-img resize FreeBSD-14.1-RELEASE-amd64-zfs.qcow2 +5G
```

Now we can boot it:

```bash
qemu-system-x86_64 \
 -drive \
 file=FreeBSD-14.1-RELEASE-amd64-zfs.qcow2,if=virtio \
 -m 4G \
 -enable-kvm \
 -smp 4 \
 -cpu host
```

Then login as "root" without a password. At this point we will do
whatever preparations we want in our template:

```sh
# you might want to change your keyboard layout
kbdcontrol -l se
# install cloud-init and open-vm-tools
pkg install net/cloud-init open-vm-tools-nox11
# install whatever other stuff you want by default
pkg install vim
# enable relevant services
sysrc cloudinit_enable="YES"
sysrc vmware_guest_vmblock_enable="YES"
sysrc vmware_guest_vmhgfs_enable="NO"    # YES if you want shared folders
sysrc vmware_guest_vmmemctl_enable="YES" # for memory ballooning
sysrc vmware_guest_vmxnet_enable="YES"   # vmxnet driver
sysrc vmware_guestd_enable="YES"         # vmware ntp, reboot etc
# not strictly necessary, but good to know if you ever want to
# reset your cloud-init config so it runs on next boot
cloud-init clean --logs --machine-id
# hide all our typos from shell history
unset savehist
poweroff
```

That's it, we now have a FreeBSD machine that is ready to be
initialized.

A short tangent regarding the packages we install: previously I had been
using vApp values to push cloud-init data into VMs, and while this
worked all right for both Ubuntu and Rocky, I never got it to work with
FreeBSD.

Looking around, I found that there seems to be a more modern (?) way of
passing this data, which doesn't require you to attach a CD-ROM to the
machine and grab it from there: all you need to do is ensure
`open-vm-tools` is already installed --- which you probably want anyway
since it adds a lot of basic VMware functionality --- and `cloud-init`
will be able to query what's called "guestinfo". It's important to note
though that for this to work, the vApp options need to be **disabled**
before creating a VM template: this is extra important for something
like Ubuntu OVA files where they are enabled and filled out by default.

The values we set on deploy for things like "userdata" or "metadata" can
be seen in the advanced configuration of the VM in vSphere, as mentioned
in the comments in under the Tofu VM definition.

Ok, so the machine is ready to go, but in our example it's in the wrong
format, so we need to convert it to VMDK:

```bash
qemu-img convert -p -f qcow2 -O vmdk -o subformat=streamOptimized -c FreeBSD-14.1-RELEASE-amd64-zfs.qcow2 freebsd14_$(date -I).vmdk
```

This will take some time due to compression, but when done you should
have a VMDK file that isn't larger than necessary and is ready to be
used as a disk surface for a VM.

The next steps will differ depending on your environment, so I'll
describe them in general:

- Upload your VMDK file to a datastore that can be reached from where
  you want to create your VM. You may be able to do it in vSphere, or
  you may have to log in directly against a host, or something else.
- When it's done, create a new virtual machine in vSphere. Add a new
  hard drive, but select "existing hard drive" and point it to your VMDK
  file.
- Remove the default drive, since we only want one.
- Save your VM, no need to boot it up (it might even fail).
- Create a template from this VM. This will be your main template for
  deploys.
- Make sure this template has a name that matches whatever you told Tofu
  to look for.

At this point, you should be ready to go. Let's do a short summary of
what happens on deploy:

- Data about the deploy comes from somewhere and ends up in a JSON file.
- This JSON file is parsed by Tofu, which creates and maps objects
  through the provider you configured.
- Tofu renders cloud-init template data which contain metadata, some
  basic instructions for what users to create or keys to add, as well as
  a shell script which runs automatically.
- Tofu tells VMware via the provider to create any objects that are
  defined but missing, and passes the rendered VM init template as
  base64.
- The VM (hopefully) deploys from the template
- cloud-init runs as it detects this is the first boot, with some help
  from open-vm-tools it finds the init payload that Tofu passed on and
  runs it.
- The VM is now running and configured, with the correct interface
  configurations, routes, packages installed, and whatever else was set
  up by either cloud-init yaml configuration or the shell script.

All right, we're well past a thousand lines now so this will have to do.
Hopefully this has been of some use, maybe you learned something or
maybe you saw something that looks really odd and unnecessary. In either
case, I hope it was of some use, and feel free to contact me with any
feedback (preferably the positive kind) or any suggestions on
improvements.

#### Changelog

- _2024-09-23 (#1)_ --- initial post.
