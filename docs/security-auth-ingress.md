# Authentication and ingress rate limits

Login uses two Redis budgets: requests per effective client IP (one minute),
and attempts per account (the configured lockout window). Username and email
aliases share the same user ID; username matching takes precedence over an
email match, just as authentication does. An unknown login has a normalized
name budget. Redis keys hash identities to avoid exposing email addresses in
key names; these hashes are pseudonymous, not anonymized.

The account attempt is reserved atomically before password verification.
Concurrent attempts therefore consume the same budget before bcrypt starts.
Successful authentication clears account attempts and failures; IP requests
remain counted. A rejected password records a failure. All counters are
created together with a TTL in a Redis transaction, preventing permanent
lockouts after a process crash. Registration uses an independent hourly IP
budget. Shared NAT users still share an IP budget; administrators can tune
`RATE_LIMIT_PER_MINUTE` and `REGISTER_LIMIT_PER_HOUR` for their audience.

If Redis is unavailable, login and registration return **503** with
`Retry-After: 30`. Failure recording and resetting must also succeed before
login can issue a token. There is no local fallback, because multiple workers
or replicas would each provide an independent attack budget. Existing JWT/API
key authorization does not acquire these login budgets. Normal limits return
**429** with the remaining TTL in `Retry-After`.

## Client IP trust boundary

The application reads only the ASGI `request.client`, never arbitrary
`X-Forwarded-For`, `X-Real-IP` or `CF-Connecting-IP` headers. It canonicalizes
IPv6 and IPv4-mapped IPv6 addresses before selecting a budget. A missing or
invalid ASGI peer fails with 503 instead of creating a bypassable identity.

For a direct API, disable Uvicorn proxy headers. For a reverse proxy, enable
Uvicorn proxy headers and set `--forwarded-allow-ips` to the explicit IP(s) of
that proxy. Never use `*` or a subnet shared with untrusted containers. The
proxy must replace client-provided forwarding headers with the address it
established from a trusted upstream. Hide the backend port from public
clients; Docker publication should bind to loopback or be omitted.

For the locally inspected Cloudflare Tunnel layout, the expected chain is:

```text
Cloudflare edge -> cloudflared -> loopback Caddy listener -> private API
                                 trusted connector IP     trusted Caddy IP
```

Caddy accepts Cloudflare's client address only from the declared connector
address and overwrites upstream `X-Forwarded-For`; Uvicorn trusts only Caddy's
fixed private IP. The production overlay takes `TRUSTED_PROXY_IPS` as a
comma-separated list of exact peer addresses; its empty default disables
forwarded-header trust. Settings reject wildcard and CIDR values. Trusting the Docker gateway also trusts other host processes
using that path: the host is part of this deployment's trust boundary.
The connector must be the only remotely reachable path to Caddy. A deployment
that exposes Caddy directly to the internet needs a different trust list and
must not accept arbitrary Cloudflare headers.

## Validation and deployment limits

`backend/tests/test_login_rate_limit.py` exercises real HTTP ASGI requests
through Uvicorn's `ProxyHeadersMiddleware`, including spoofed headers from an
untrusted peer, distinct clients behind a trusted ingress, attacker-added
forwarded chains, Redis outages, and no token issuance when reset fails.
Tests also cover an account whose username equals another account's email.

These tests validate the server's trust contract, not the external Cloudflare
edge. Before publication, inspect effective Compose commands/ports, check
that proxy trust contains only the actual ingress IP, and exercise requests
through the deployed ingress. Keep edge/ingress request limits enabled to
protect the API during Redis outages and before request bodies are parsed;
Redis failure protection itself remains fail-closed without that extra layer.
