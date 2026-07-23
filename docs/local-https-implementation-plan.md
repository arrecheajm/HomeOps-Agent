# Local HTTPS Implementation Plan

Status: planned; no DNS, router, certificate, port, or live-service changes have
been made.

## Decision Summary

Use a pinned Caddy container as the single LAN-only HTTPS ingress for HomeOps.
Use service names under the special-use `home.arpa` domain and Caddy's private
certificate authority. Keep `homevpnserver.myftp.biz` dedicated to the existing
OpenVPN/DDNS role.

This is the best fit for the current constraints:

- services remain reachable only from the home LAN or through OpenVPN;
- no router WAN port forwarding is introduced;
- no recurring domain or DNS service is required;
- one proxy owns certificates and HTTPS policy instead of configuring every
  application separately;
- backend application traffic stays on Docker networks and does not need TLS;
- the HomeOps agent can build, deploy, verify, back up, restore, and roll back
  the server side.

One client-side trust step cannot be automated by the server: each phone,
tablet, or computer must trust the HomeOps root CA once. The exact instructions
depend on the phone platform.

## Why The Free No-IP Hostname Is Not The Ingress Name

`homevpnserver.myftp.biz` is a Free Dynamic DNS hostname owned under No-IP's
`myftp.biz` zone. It remains useful for locating the OpenVPN endpoint when the
home public IP changes, but it does not provide the DNS control needed for the
HomeOps HTTPS design:

- Free No-IP hostnames cannot create fourth-level service names such as
  `grafana.homevpnserver.myftp.biz`.
- The Free plan does not provide TXT records, so it cannot perform a DNS-01
  certificate challenge.
- A public certificate for the one exact hostname could instead use HTTP-01 or
  TLS-ALPN-01, but that requires inbound Internet access to port 80 or 443.
- Reusing one hostname would also force fragile path-based routing or continued
  nonstandard ports for unrelated applications.

No No-IP username or password will be stored in this repository or passed to
Caddy. No-IP, OpenVPN, and router WAN rules are outside the HTTPS action scope.

Official references:

- [No-IP Free and Enhanced hostname limitations](https://www.noip.com/support/knowledgebase/free-enhanced-limitations)
- [Caddy automatic and local HTTPS](https://caddyserver.com/docs/automatic-https)
- [Let's Encrypt integration and challenge guidance](https://letsencrypt.org/docs/integration-guide/)

If a custom domain with API-controlled DNS is purchased later, HomeOps can
migrate to publicly trusted certificates using DNS-01 without exposing the
services to the Internet. That is an optional later design, not a prerequisite.

## Target Names And Routes

All names resolve only to `192.168.86.58`.

| Client URL | Internal target | Purpose |
|---|---|---|
| `https://homeops.home.arpa` | `homepage:3000` | Household landing page |
| `https://grafana.home.arpa` | `grafana:3000` | Fleet and container monitoring |
| `https://kuma.home.arpa` | `uptime-kuma:3001` | Reachability monitoring |
| `https://ntfy.home.arpa` | `ntfy:8080` | Local notifications |

Portainer remains temporary administration infrastructure. It must not block
the core cutover. A later bounded action will either retire it or add
`https://portainer.home.arpa` and remove its direct HTTP port.

Reserve these names without deploying their applications yet:

- `homeassistant.home.arpa`
- `mealie.home.arpa`
- `paperless.home.arpa`
- `git.home.arpa`

## Target Architecture

```text
phone or computer on LAN/VPN
        |
        | local DNS: *.home.arpa -> 192.168.86.58
        v
Caddy on 192.168.86.58:80/443
        |
        | internal HTTP on dedicated Docker ingress network
        +--> Homepage :3000
        +--> Grafana :3000
        +--> Uptime Kuma :3001
        +--> ntfy :8080
```

There will be no WAN forwarding for TCP 80 or 443. OpenVPN remains the only
remote-access boundary.

## Desired-State Requirements

Create `stacks/ingress/` with:

- an exact Caddy version and Linux/amd64 digest;
- a read-only tracked Caddyfile;
- a persistent named data volume for the CA, certificates, and renewal state;
- a persistent config volume only if the pinned image requires it;
- a read-only container filesystem with bounded writable volumes and `tmpfs`;
- no Docker socket;
- no privileged mode;
- `no-new-privileges`, minimal capabilities, resource/PID limits, log rotation,
  a restart policy, and a health check;
- bindings only on `192.168.86.58:80` and `192.168.86.58:443`;
- modern TLS defaults managed by Caddy;
- security headers that do not prematurely enable long-lived HSTS.

Create a dedicated external Docker network named `homeops-ingress`. Attach only
Caddy and the four proxied application containers. Keep every application's
existing private network. After cutover, remove direct LAN port mappings for
Homepage, Grafana, Uptime Kuma, and ntfy.

Update application desired state:

- Homepage allowed hosts and links use the HTTPS names.
- Homepage service monitors continue to use internal HTTP targets.
- Grafana receives the public root URL and domain needed for correct redirects.
- ntfy's public base URL becomes `https://ntfy.home.arpa`.
- Uptime Kuma continues to monitor and notify over internal Docker HTTP where
  credentials or tokens never leave the host.
- The Grafana dashboard's reciprocal HomeOps link uses HTTPS.
- Health checks remain internal and do not depend on DNS or the private CA.

## Certificate Authority Lifecycle

Caddy creates the root and intermediate CA material in its persistent data
volume. The root certificate is public; the root private key is sensitive.

HomeOps must:

1. Start Caddy with direct HTTP application ports still available.
2. Export only the public root certificate to a Git-ignored workstation
   location.
3. Display and record its SHA-256 fingerprint without exposing private material.
4. Give the operator platform-specific phone trust instructions.
5. Verify that a trusted client rejects a deliberately wrong hostname.
6. Create an authenticated encrypted backup of the Caddy data volume.
7. Prove a bounded restore before direct HTTP application ports are removed.

Loss of the Caddy data volume without a backup would require creating a new CA
and trusting the new root on every client. The CA backup therefore becomes part
of the normal HomeOps backup set.

## DNS Gate

Implementation cannot select a safe local-DNS method until the home router model
and capabilities are known.

Preferred order:

1. Use router-managed local host records if the router supports them.
2. If it does not, design a separately reviewed local DNS service and DHCP
   transition; do not silently make the home server a network-wide DNS
   dependency.
3. A purchased custom domain with DNS-01 is a later alternative.

DNS must work from both the normal home Wi-Fi and an OpenVPN client. Public DNS
must never be changed to point the Free No-IP hostname at the container host.

## Approval-Gated Delivery Sequence

### 1. Read-Only Discovery

- record the router make/model and local DNS options;
- record the phone platform;
- confirm TCP ports 80 and 443 are unused on `container-host`;
- inventory Docker networks and the four target containers;
- confirm no router WAN forwarding targets `container-host` ports 80 or 443;
- verify LAN and OpenVPN routing to `192.168.86.58`.

This stage does not pull images or change DNS.

### 2. Implement And Test Desired State In Git

- add the ingress Compose bundle and Caddyfile;
- update monitoring and Mission Control Compose/configuration;
- update backup and restore coverage for Caddy's data volume;
- add regression tests for exact images, bindings, networks, private backends,
  URLs, headers, health, backup, recovery, and rollback;
- add fixed action registrations and exact approval phrases.

No live deployment occurs in this stage.

### 3. Approved Image And Network Preflight

`preflight_https_ingress` will:

- pull and inspect the exact Caddy image;
- validate Linux/amd64 and required commands;
- verify fixed container, volume, network, and port identities;
- validate the composed configuration;
- make no running-service changes.

### 4. Approved Parallel HTTPS Deployment

`deploy_https_ingress` will:

- create the fixed external ingress network;
- stage hash-verified desired-state files;
- attach the four application containers to the ingress network;
- start Caddy on LAN ports 80 and 443;
- leave the existing direct HTTP ports available as rollback access;
- export only the public CA root and fingerprint;
- verify all four HTTPS routes from the server and workstation.

Failure restores the prior Compose/configuration and leaves direct HTTP working.

### 5. Client Trust Acceptance

The operator installs and explicitly enables trust for the HomeOps root CA on
the phone. Acceptance requires:

- all four HTTPS names open without a certificate warning;
- Grafana, Uptime Kuma, and ntfy login succeeds;
- Homepage contains no mixed-content or API errors;
- the certificate name and CA fingerprint match the recorded values;
- the same names work while connected through OpenVPN.

This is a required human acceptance step, not an action the server can safely
perform on an unmanaged phone.

### 6. Approved CA Backup And Restore Proof

Back up the Caddy data volume with the same authenticated-encryption model used
for Mission Control, transfer it to the workstation, and prove a bounded
restore. Do not remove direct application ports until this passes.

### 7. Approved Private-Backend Cutover

`cutover_https_ingress` will:

- remove the four direct LAN application port mappings;
- recreate only the affected application containers;
- verify that ports 3000, 3001, 8081, and 8082 no longer accept LAN traffic;
- verify HTTPS routes, authentication, Homepage content, Kuma monitors, ntfy
  ACLs/notifications, Grafana provisioning, and all container identities;
- automatically restore the direct bindings and old URLs if acceptance fails.

### 8. Reboot Acceptance

Use the existing bounded reboot action, then verify:

- Caddy and all seven monitoring/Mission Control containers are healthy;
- DNS and HTTPS work from Wi-Fi and OpenVPN;
- certificates and the CA fingerprint are unchanged;
- direct backend ports remain closed;
- Kuma state, ntfy ACLs, Grafana login, and Homepage links persist.

## Explicit Non-Goals

- no public website;
- no WAN exposure of ports 80 or 443;
- no change to the No-IP hostname or credentials;
- no change to OpenVPN;
- no router or DHCP change without a separately reviewed exact scope;
- no single sign-on in the first HTTPS phase;
- no HSTS preload or long-duration HSTS during rollout;
- no Portainer lifecycle expansion hidden inside the core ingress deployment.

## Remaining Operator Inputs

Before implementation begins, record:

- home router make and model;
- phone platform: Android or iPhone/iOS;
- whether HTTPS names must work through OpenVPN immediately;
- whether one manual root-CA installation per client is acceptable.
