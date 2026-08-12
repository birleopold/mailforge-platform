# Domain onboarding

## User experience

### Step 1 — Add domain
User enters `example.com`.

Reject:

- malformed names;
- domains already owned by another tenant;
- reserved/internal domains;
- obvious public suffixes.

### Step 2 — Prove ownership

MailForge displays:

```text
Type: TXT
Name: _mailforge-verify.example.com
Value: mailforge-verification=<random-token>
```

Verification runs asynchronously.

### Step 3 — Provision backend

After ownership is confirmed:

- create domain in mailcow;
- apply quotas;
- create/obtain DKIM data;
- save backend identifiers.

### Step 4 — DNS checklist

Show each record with:

- host/name;
- record type;
- expected value;
- observed value;
- status;
- last checked time.

### Step 5 — Activate

Inbound can be enabled once routing is correct.

Outbound should require the minimum safety set selected by policy (for example SPF + DKIM and valid server routing).

### Step 6 — Continuous health

Re-check DNS on a schedule and warn rather than immediately destroying service when a temporary DNS failure occurs.
