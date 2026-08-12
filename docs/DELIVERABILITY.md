# Deliverability

Running SMTP is easy. Building and maintaining sender reputation is the difficult part.

## Required DNS

For each hosted domain, guide the customer through:

- MX
- SPF
- DKIM
- DMARC
- autoconfig/autodiscover where used

For the mail infrastructure:

- A/AAAA for the mail hostname
- PTR/rDNS matching the mail hostname
- valid TLS certificate

Recommended additions:

- MTA-STS
- TLS-RPT
- DNSSEC where operationally appropriate

## Sending reputation

- start with a clean static IP;
- confirm outbound TCP/25 before choosing a VPS;
- configure PTR before production sending;
- do not permit bulk marketing in the first release;
- throttle new accounts;
- track deferrals, hard bounces and blocks;
- maintain postmaster and abuse addresses;
- watch major reputation/blacklist signals;
- warm up sending volume gradually.

## Shared vs dedicated sending

### Shared route
Best for small tenants. Lowest infrastructure cost, but reputation is shared.

### Dedicated route/IP
Future premium feature for larger trusted tenants. Requires more operational work and careful IP warm-up.

### External smart host
Keep an adapter for an optional outbound relay. It can be used as a contingency or premium deliverability feature without changing tenant/domain models.

## DMARC rollout

A safe onboarding approach:

1. start with monitoring (`p=none`);
2. review alignment;
3. move to quarantine;
4. eventually reject when legitimate sources are known.

Do not automatically set a strict DMARC policy before the customer has identified all legitimate senders.
