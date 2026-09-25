# Security Policy

This integration handles Glooko credentials and health data, so we take security reports seriously.

## Reporting a vulnerability

**Please do not open a public issue.** Use GitHub's private reporting instead:

1. Go to the repository's **Security** tab → **Report a vulnerability**
   (<https://github.com/mmxca/glookup-ha-integration/security/advisories/new>).
2. Describe the issue, how to reproduce it, and the impact. Do **not** include real credentials or
   real medical data. Synthetic examples are fine.

A maintainer will acknowledge the report as soon as practical, keep you updated, and credit you in
the advisory unless you prefer otherwise.

## In scope

- Credential or session-cookie leakage (logs, diagnostics, entity attributes, exceptions).
- Anything that causes the integration to **write** to a Glooko or pump account.
- Unsafe handling of API responses (e.g., injection into HA templates or the frontend).

## Out of scope

- Vulnerabilities in Glooko's or Insulet's own services. Report those to the vendor.
- Issues requiring an already-compromised Home Assistant host.

## Supported versions

Only the latest release on `main` receives fixes.
