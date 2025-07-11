---
title: 'Enrolling Linux systems into Active Directory with SSSD'
date: 2025-07-10T21:00:00+02:00
draft: false
tags:
  - sysadmin
  - linux
---

If you already have Active Directory in your environment, it might make
sense to use that directly for SSH authentication, here's an example of
how it can be done.

The scope for this article is strictly SSH authentication. There are
probably many more benefits to using SSSD this way, like automatic
DNS entries.

## What is SSSD?

According to Wikipedia, SSSD is a piece of Linux software that:

> provides a set of daemons to manage access to remote directory
> services and authentication mechanisms

This article will show an example of using Ansible to "enroll" Linux
systems against an existing Active Directory, and what configuration
options need to be paid attention to.

If you're not comfortable with Ansible, the examples will probably still
make sense as they're really only running commands and changing
configuration files.

## Ansible examples

### Handling secrets

You will need at least one secret, being the password of the user that
is allowed to enroll new devices into AD. For this reason, you probably
want to use Ansible vault:

```yaml
- name: 'include_vars .ansible_vault'
  include_vars: .ansible_vault
```

### Validating DNS

If you are in an AD environment, those systems are probably responsible
for DNS, so you want to check that the system you're trying to enroll is
actually able to reach, and using the expected DNS:

```yaml
- name: Try pinging internal DNS
  shell: 'ping -c 1 1.2.4.4'
  check_mode: false # always run, ping is safe
  register: ping_result
  ignore_errors: yes
  changed_when: false

- name: Internal DNS ping failed
  debug:
    msg: |
      INTERNAL DNS PING FAILED
      This system cannot reach our internal DNS servers, AD enrollment
      will not work.
  when: ping_result.rc != 0

- name: INTERNAL DNS PING FAILED, END PLAY FOR HOST IMMEDIATELY
  meta: end_host
  when: ping_result.rc != 0
```

Then try checking that they're actually being used:

```yaml
- name: Check for IP of internal DNS in /etc/netplan/ (ubuntu)
  command: "grep -rq '1.2.3.4' /etc/netplan/"
  check_mode: false # always run, grep is safe
  register: grep_result_ubuntu
  ignore_errors: yes
  failed_when: false
  when: ansible_os_family == "Debian"

# similar for rocky, or whatever else might be encountered

- name: Incorrect DNS configuration
  debug:
    msg: |
      INCORRECT DNS CONFIGURATION
      This system CAN reach our internal DNS servers, but is not
      configured to use them. This must be fixed manually.
      This play will now abort.

      Useful instructions on how to fix this goes here.
  when: >
    (ping_result.rc == 0 and ping_result is defined) and
    (
      (ansible_os_family == "Debian" and grep_result_ubuntu.rc != 0)
      or
      (ansible_os_family == "RedHat" and grep_result_rocky.rc != 0)
    )
```

### Installing packages

Now that you know DNS is set up correctly, you can install the required
packages for your distro. This might take some experimenting, and
there's no guarantees this list is by any means perfect.

```yaml
- name: Installing packages necessary for AD enrollment.
  debug:
    msg: |
      INSTALLING PACKAGES
      Slow if package operations are required. Please wait.

- name: Install necessary APT packages (Ubuntu/Debian)
  apt:
    update_cache: true
    name:
      - sssd
      - sssd-tools
      - sssd-ad
      - realmd
      - libnss-sss
      - libpam-sss
      - adcli
      - samba-common-bin
      - oddjob-mkhomedir
      - winbind
    force_apt_get: yes
  become: true
  register: sssd_packages
  when: ansible_os_family == "Debian"

- name: Install necessary DNF packages (Enterprise Linux)
  dnf:
    update_cache: true
    state: present
    enablerepo: epel
    name:
      - sssd
      - sssd-tools
      - sssd-ad
      - sssd-common
      - realmd
      - adcli
      - samba-common-tools
      - oddjob
      - oddjob-mkhomedir
      - openldap-clients
      - samba-winbind
      - selinux-policy-targeted
      - krb5-workstation
  become: true
  register: sssd_packages
  when: ansible_os_family == "RedHat"

- name: SELinux booleans
  seboolean:
    name: '{{ item }}'
    state: true
    persistent: true
  loop:
    - authlogin_nsswitch_use_ldap
  when: ansible_os_family == "RedHat"
  # selinux being disabled on this system is not a reason to stop
  ignore_errors: yes
```

### Check if system is already enrolled

This should only work on an only enrolled system, so if it does, let's
skip the enroll and move on to config validation:

```yaml
- name: Check if system is already enrolled in ACTIVE DIRECTORY
  shell: "realm list | grep -q 'realm-name: INTERNAL.YOUR.AD'"
  when: sssd_packages is succeeded
  register: ad_enrolled
  ignore_errors: yes
  failed_when: false
  changed_when: false

- name: System already enrolled
  debug:
    msg: |
      SYSTEM ALREADY ENROLLED
      No enrollment attempt will be done.
      Play will continue and perform config validation, if it exists.
  when: ad_enrolled.rc == 0
```

Config validation examples are shown later.

### Enroll the system

In this example, `tenant_id` is used as this is an identifier from
Netbox that is designed to tie into the name of the OU created in AD.
This is in no way generally useful, but can be used as an example of how
you could structure groups in AD. The values for `credentials` come from
the imported Ansible vault.

```yaml
- name: Check if OU '{{ tenant_id | lower }}' already exists
  shell:
    # -x  Use simple authentication instead of SASL.
    # -w  passwd
    #     Use passwd as the password for simple authentication.
    # -D  binddn
    #      Use the Distinguished Name binddn to bind to the LDAP
    #      directory.  For SASL binds, the server is expected to
    #      ignore this value.
    # -b searchbase
    #      Use searchbase as the starting point for the search instead of the default.
    cmd: |
      ldapsearch -H ldap://internal.your.ad -x -D "{{ credentials.ad_enrollment.user }}@internal.your.ad" \
      -w '{{ credentials.ad_enrollment.pass }}' -b "OU=Linux,OU=Servers,DC=internal,DC=your,DC=ad" "(ou={{ tenant_id | lower }})"
  when: (sssd_packages is succeeded) and (ad_enrolled.rc != 0)
  # DO NOT LOG -- DO NOT COMMENT OUT IN PRODUCTION!
  # THIS COMMAND CONTAINS ENROLLMENT CREDENTIALS
  no_log: true
  ignore_errors: true
  register: ou_exists

- name: OU lookup failed
  debug:
    msg: |
      OU LOOKUP FAILED. STDERR BELOW
      {{ ou_exists.stderr }}
  when: ou_exists.failed | default(false)

- name: OU lookup failed, end play for host immediately.
  meta: end_host
  when: ou_exists.failed | default(false)

- name: OU lookup OK, but OU is missing
  debug:
    msg: |
      OU IS MISSING IN AD
      AD query response does not contain 'numEntries', this indicates
      the OU does not exist. We will attempt to create it!
  when: "'numEntries' not in ou_exists.stdout | default('numEntries')"

- name: Create OU '{{ tenant_id | lower }}'.
  shell:
    cmd: |
      ldapadd -H ldap://internal.your.ad -x -D "svc_user@internal.your.ad" \
      -w '{{ credentials.ad_enrollment.pass }}' <<EOF
      dn: OU={{ tenant_id | lower }},OU=Linux,OU=Servers,DC=internal,DC=your,DC=ad
      objectClass: organizationalUnit
      ou: {{ tenant_id | lower }}
      EOF
  when: "'numEntries' not in ou_exists.stdout | default('numEntries')"
  # DO NOT LOG -- DO NOT COMMENT OUT IN PRODUCTION!
  # THIS COMMAND CONTAINS ENROLLMENT CREDENTIALS
  no_log: true
  ignore_errors: true
  register: ou_created

- name: OU creation failed
  debug:
    msg: |
      OU CREATION FAILED. STDERR BELOW
      {{ ou_created.stderr }}
  when: ou_created.failed | default(false)

- name: OU creation failed, end play for host immediately.
  meta: end_host
  when: ou_created.failed | default(false)

- name: OU created!
  debug:
    msg: |
      OU CREATED OK. STDOUT BELOW
      {{ ou_created.stdout }}
  when: ou_created.succeeded | default(false)

- name: Pre-enroll | Cut hostname and convert to uppercase
  set_fact:
    short_hostname: '{{ ansible_hostname[:10] | upper }}'
  when: ad_enrolled.rc != 0
- name: Pre-enroll | Generate 4 random alphanumeric characters and convert to uppercase
  set_fact:
    random_suffix: "{{ lookup('password', '/dev/null length=4 chars=ascii_letters,digits') | upper }}"
  when: ad_enrolled.rc != 0
- name: Pre-enroll | Combine short hostname with random suffix as hostname for enroll
  set_fact:
    new_hostname: '{{ short_hostname }}-{{ random_suffix }}'
  when: ad_enrolled.rc != 0
- name: Pre-enroll | Hostname generated
  debug:
    msg: "System will attempt to enroll into AD as '{{ new_hostname }}'."
  when: ad_enrolled.rc != 0

- name: Ensure rdns is disabled in krb5.conf
  ini_file:
    path: /etc/krb5.conf
    section: libdefaults
    option: rdns
    value: false
    no_extra_spaces: yes

# computer-name: random generated as 10 characters of hostname + random
#           alphanumeric, so superlonghostname01 -> SUPERLONGH-7EB2
#           this is due to the 15 char limit in AD. note from realm
#           doc: "The system's FQDN will still be saved in the
#           dNSHostName attribute."
# computer-ou: places the device under linux systems in a OU named as the
#           tenant_id
#
# 'credentials' comes from .ansible_vault

- name: Enroll this device with 'realm join'
  shell:
    cmd: |
      echo '{{ credentials.ad_enrollment.pass }}' | \
      realm join \
      --computer-ou=OU={{ tenant_id | lower }},OU=Linux,OU=Servers,DC=internal,DC=your,DC=ad \
      --computer-name={{ new_hostname }} \
      --user={{ credentials.ad_enrollment.user }} \
      internal.your.ad
  when: (sssd_packages is succeeded) and (ad_enrolled.rc != 0)
  # DO NOT LOG -- DO NOT COMMENT OUT IN PRODUCTION!
  # THIS COMMAND CONTAINS ENROLLMENT CREDENTIALS
  no_log: true
  # keep running if enrollment fails, we still want to check config
  ignore_errors: true
  register: realm_join

- name: Enroll failed, STDERR
  debug:
    msg: |
      ENROLLMENT FAILED. STDERR BELOW
      "{{ realm_join.stderr }}"

      Play will continue if sssd.conf already exists to validate config.
  when: realm_join.failed | default(false)
```

### Config validation

If enrollment succeeded, or the system is already enrolled, we move on
to validating `/etc/sssd/sssd.conf`. This file is in an INI format, and
cannot really be pushed out statically since it will differ on every
system. Instead of having to set up some overly complex templating,
let's just leave the original file alone and use Ansible's `ini_file` to
ensure one key/value at a time. Not exactly the quickest solution, but I
think it makes sense. Here's my list of values to assert:

```yaml
- name: Look for sssd.conf
  stat:
    path: /etc/sssd/sssd.conf
  register: conf_stat

- name: assert sssd.conf exists
  assert:
    that: conf_stat.stat.exists
    fail_msg: "/etc/sssd/sssd.conf does not exist, can't perform config validation. Bailing out."

# override_homedir: Sets the default user home directory path, with %u
# replaced by the username.
- name: set 'override_homedir'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: override_homedir
    value: '/home/%u'

# fallback_homedir: Specifies fallback home directory if
# override_homedir isn't used (or taken, probably)
- name: set 'fallback_homedir' (_internal_your_ad)
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: fallback_homedir
    value: '/home/%u_internal_your_ad'

# ldap_user_ssh_public_key: Specifies the LDAP attribute used to store
# SSH public keys for users.
- name: set 'ldap_user_ssh_public_key'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: ldap_user_ssh_public_key
    value: 'sshPublicKey'

# ldap_use_tokengroups: Enables use of Active Directory tokenGroups for
# efficient group membership retrieval.
- name: set 'ldap_use_tokengroups'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: ldap_use_tokengroups
    value: 'true'

# use_fully_qualified_names: Disables the use of domain-qualified user
# names (e.g., user@domain).
- name: set 'use_fully_qualified_names'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: use_fully_qualified_names
    value: 'false'

# ad_gpo_access_control: Disables the use of Active Directory GPO (Group
# Policy Object) for access control.
- name: set 'ad_gpo_access_control'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: ad_gpo_access_control
    value: 'disabled'

# sudo_provider: Disables SSSD's sudo integration, we set this in the
# sudo file itself
- name: set 'sudo_provider'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: sudo_provider
    value: 'none'

# ad_gpo_map_remote_interactive: Removes the option for mapping remote
# interactive sessions with GPO. this crashes sssd, probably since
# ad_gpo_access_control is disabled :)
- name: ensure 'ad_gpo_map_remote_interactive' does not exist
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: ad_gpo_map_remote_interactive
    state: absent

# entry_cache_timeout: Sets the SSSD entry cache timeout to 60 seconds.
- name: set 'entry_cache_timeout'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: entry_cache_timeout
    value: '60'

# subdomain_inherit: Ignores group members when inheriting
# configurations for subdomains.
- name: set 'subdomain_inherit'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: subdomain_inherit
    value: 'ignore_group_members'

# ldap_network_timeout: Sets LDAP network timeout for connections to 10
# seconds.
- name: set 'ldap_network_timeout'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: ldap_network_timeout
    value: '10'

# https://sssd.io/design-pages/active_directory_access_control.html

# ad_access_filter: Sets LDAP filter for AD group membership to control
# access.
- name: set 'ad_access_filter'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: ad_access_filter
    value: >
      DOM:internal.your.ad:(|
      (memberOf:1.2.840.113556.1.4.1941:=CN=USERS_SSH_{{ tenant_id | lower }},OU=UserGroups,OU=Rules,OU=Groups,DC=internal,DC=your,DC=ad)
      (memberOf:1.2.840.113556.1.4.1941:=CN=SUPERUSERS_SSH_{{ tenant_id | lower }},OU=SuperuserGroups,OU=Rules,OU=Groups,DC=internal,DC=your,DC=ad)
      (memberOf:1.2.840.113556.1.4.1941:=CN=ADMINS_SSH,OU=AdminGroups,OU=Rules,OU=Groups,DC=internal,DC=your,DC=ad)
      )

- name: set 'ldap_user_name'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: ldap_user_name
    value: 'sAMAccountName'

- name: set 'ldap_group_name'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: ldap_group_name
    value: 'sAMAccountName'

# cache_credentials: Disables caching credentials on disk.
- name: set 'cache_credentials'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: cache_credentials
    value: 'false'

# memcache_timeout: Sets memory cache timeout for NSS to 60 seconds.
- name: set 'memcache_timeout'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'nss'
    option: memcache_timeout
    value: '60'

# If the OU has been created by us (using ldapadd), which it probably
# has, by default users will be denied because of some missing
# attributes in AD that I have no idea how to create or if they are
# even necessary. The error is:

# Group Policy Container with DN (...)
# is unreadable or has unreadable or missing attributes. In order to
# fix this make sure that this AD object has following attributes
# readable: nTSecurityDescriptor, cn, gPCFileSysPath,
# gPCMachineExtensionNames, gPCFunctionalityVersion, flags.

# Probably this has something to do with permissions on the enrolled
# system object itself being different due to how the OU was created
# (from Linux CLI) -- the assumption is we don't really care about
# system permissions, because access is decided by 'ad_access_filter'
# which looks for user group membership.

# This issue is bypassed by setting 'ad_gpo_ignore_unreadable'. Doc:
#
#     "Normally when some group policy containers (AD object) of
#     applicable group policy objects are not readable by SSSD then
#     users are denied access. This option allows to ignore group
#     policy containers and with them associated policies if their
#     attributes in group policy containers are not readable for SSSD."

- name: set 'ad_gpo_ignore_unreadable'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'domain/internal.your.ad'
    option: ad_gpo_ignore_unreadable
    value: 'true'

# full_name_format: Sets the format of full user names.
- name: set 'full_name_format'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'sssd'
    option: full_name_format
    value: '%1$s'

# override_space: Replaces spaces with dashes in groups for example
- name: set 'override_space'
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'sssd'
    option: override_space
    value: '-'

- name: set 'services' to EMPTY (socket activated on Debian/Ubuntu)
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'sssd'
    option: services
    value: ''
  when: ansible_os_family == "Debian"

- name: set 'services' (Enterprise Linux)
  ini_file:
    path: '/etc/sssd/sssd.conf'
    section: 'sssd'
    option: services
    value: 'nss, pam, ssh'
  when: ansible_os_family == "RedHat"

- name: Restore SELinux context for SSSD configuration
  command: restorecon -v /etc/sssd/sssd.conf
  when: ansible_os_family == "RedHat"

- name: restarting sssd
  systemd:
    name: sssd
    state: restarted
```

You also have to set up the SSH daemon and `/etc/pam.d/sshd`. The
`configure-sshd` task below essentially only adds this logic to whatever
sshd configuration you already have:

```jinja
{% if ad_enrolled %}
# ad-enroll: {{ ad_enrolled }} -- use PAM, allow sssd to validate pubkeys
UsePAM yes
AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys
{% if ansible_os_family == "Debian" %}
AuthorizedKeysCommandUser root
{% elif ansible_os_family == "RedHat" %}
AuthorizedKeysCommandUser nobody
{% endif %}
{% else %}
# ad_enroll: {{ ad_enrolled }}
UsePAM no
{% endif %}
```

```yaml
# configure sshd
- name: Configure SSH daemon
  ansible.builtin.import_tasks: 'tasks/configure-sshd.yml'

# these templates currently hold no logic, but they might in the future.
- name: push pam.d/sshd template (Ubuntu/Debian)
  template:
    src: pam_d_sshd_ubuntu.j2
    dest: /etc/pam.d/sshd
    mode: 0644
    owner: root
    group: root
  when: ansible_os_family == "Debian"

- name: push pam.d/sshd template (Enterprise Linux)
  template:
    src: pam_d_sshd_rocky.j2
    dest: /etc/pam.d/sshd
    mode: 0644
    owner: root
    group: root
  when: ansible_os_family == "RedHat"
```

The `pam.d` template looks like this for Ubuntu. Note
that these settings may be terrible, if they are let me know :)

```
########################################################################
# THIS FILE IS HANDLED BY ANSIBLE, DO NOT EDIT.                        #
# mirrors defaults, except for sections marked: ADDITIONS.             #
########################################################################

# PAM configuration for the Secure Shell service

# Standard Un*x authentication.
@include common-auth

# Disallow non-root logins when /etc/nologin exists.
account    required     pam_nologin.so

# Uncomment and edit /etc/security/access.conf if you need to set complex
# access limits that are hard to express in sshd_config.
# account  required     pam_access.so

# Standard Un*x authorization.
@include common-account

# SELinux needs to be the first session rule.  This ensures that any
# lingering context has been cleared.  Without this it is possible that a
# module could execute code in the wrong domain.
session [success=ok ignore=ignore module_unknown=ignore default=bad]        pam_selinux.so close

# ADDITIONS BEGIN #################################
session    required     pam_oddjob_mkhomedir.so skel=/etc/skel umask=0077
session    sufficient   pam_sss.so
password   sufficient   pam_sss.so
account    sufficient   pam_sss.so
auth       sufficient   pam_sss.so
# ADDITIONS END ###################################

# Set the loginuid process attribute.
session    required     pam_loginuid.so

# Create a new session keyring.
session    optional     pam_keyinit.so force revoke

# Standard Un*x session setup and teardown.
@include common-session

# Print the message of the day upon successful login.
# This includes a dynamically generated part from /run/motd.dynamic
# and a static (admin-editable) part from /etc/motd.
session    optional     pam_motd.so  motd=/run/motd.dynamic
session    optional     pam_motd.so noupdate

# Print the status of the user's mailbox upon successful login.
session    optional     pam_mail.so standard noenv # [1]

# Set up user limits from /etc/security/limits.conf.
session    required     pam_limits.so

# Read environment variables from /etc/environment and
# /etc/security/pam_env.conf.
session    required     pam_env.so # [1]
# In Debian 4.0 (etch), locale-related environment variables were moved to
# /etc/default/locale, so read that as well.
session    required     pam_env.so user_readenv=1 envfile=/etc/default/locale

# SELinux needs to intervene at login time to ensure that the process starts
# in the proper default security context.  Only sessions which are intended
# to run in the user's context should be run after this.
session [success=ok ignore=ignore module_unknown=ignore default=bad]        pam_selinux.so open

# Standard Un*x password updating.
@include common-password
```

### sudo and group logic

A short explanation of the idea behind this configuration:

- Every "tenant" has three groups in AD. For tenant `foo` these would be
  `USERS_SSH_foo`, `SUPERUSERS_SSH_foo` and `ADMINS_SSH`:
  - If you belong to USERS, you get non-sudo access to all systems in
    that tenant.
  - If you belong to SUPERUSERS, you get sudo access to all systems in
    that tenant.
  - If you belong to ADMINS, you get sudo access to systems in all
    tenants.

This logic is arbitrary, but is used when setting up the sudo file on
any enrolled system by mapping local groups on the Linux systems
(mirrored from AD).

The configuration seen above for the SSH daemon and PAM should give the
user access to the system thanks to the AD query asserted by our INI
module above.

The sudo file can be pushed out with logic that looks something like
this:

```yaml
- name: set up sudo rules
  copy:
    content: |
      %superusers_ssh_{{ tenant_id | lower }} ALL=(ALL) NOPASSWD: ALL
      %admins_ssh ALL=(ALL) NOPASSWD: ALL
    dest: /etc/sudoers.d/internal_your_ad
    mode: '0440'

# not sure if this is necessary, but it won't hurt
- name: Restore SELinux context for sshd, pam.d, sudo
  command: restorecon -v {{ item }}
  loop:
    - /etc/ssh/sshd_config
    - /etc/pam.d/sshd
    - /etc/sudoers.d/internal_your_ad
  when: ansible_os_family == "RedHat"

- name: restarting ssh daemon
  systemd:
    name: sshd
    state: restarted
```

Note the following:

- Groups on Linux are always lowercase
- Only two out of three groups should get sudo access: the "superusers"
  group for the tenant in question, and "admins".

### Summary

With all of this done, you should hopefully have:

- SSSD running and configured on a Linux system
- When connecting over SSH, you will get access if your username matches
  one in AD that has an `sshPublicKey` attribute matching the incoming
  key
- If this user has relevant group permissions, as mirrored from AD on
  the system by SSSD, you may have sudo rights.

Thoughts and feedback are welcome via
[@linus@telegrafverket.cc](https://telegrafverket.cc/@linus) -- email
works too.
