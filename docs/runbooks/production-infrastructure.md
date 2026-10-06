# Production infrastructure

Use Python 3 and Compose 2.24.4+ and `scripts/start-production.sh`; `start.sh` and
`docker-compose.infra.yml` are development workflows and may reuse unauthenticated
shared infrastructure. The production overlay must be **last**, including after
GPU, audio or live overlays. It replaces source mounts, isolates network/data
names from development, removes infrastructure host ports, and binds application
ports to loopback for an HTTPS reverse proxy. Do not attach this network to a
shared development network. Restrict access to Docker itself: it is root access.

Create a new `.env.production` (mode 600), without copying a live installation's
secrets. Configure unique `JWT_SECRET_KEY`, `MINIO_ROOT_USER`,
`MINIO_ROOT_PASSWORD`, `REDIS_PASSWORD`, `ELASTICSEARCH_PASSWORD`, `DATABASE_URL`,
`CORS_ALLOWED_ORIGINS`, `NEXT_PUBLIC_API_URL` and `MINIO_PUBLIC_ENDPOINT`.
`MINIO_PUBLIC_ENDPOINT` is the browser-facing TLS S3 hostname and optional port,
without a URL scheme; it must route to this MinIO server and preserve the Host
used by presigned signatures. API/frontend are exposed through an HTTPS proxy;
the S3 endpoint needs an HTTPS proxy or a dedicated TLS ingress. Do not expose
the MinIO console publicly. Database credentials should have only application
schema privileges, and external database transport must use verified TLS via
the SQL driver's supported URL/connect arguments.

Set `PRODUCTION_TLS_DIR` to an absolute directory outside the source tree with:

- `ca.crt`: issuing CA bundle trusted by all three infrastructure services.
- `redis.crt`, `redis.key`: server certificate with DNS SAN `redis`.
- `elasticsearch.crt`, `elasticsearch.key`: SANs `elasticsearch`, `localhost`.
- `minio/public.crt`, `minio/private.key`: SANs `minio`, `localhost`, and public S3 hostname.
- `minio/CAs/ca.crt`: the same CA bundle for MinIO health checks.

Use certificates issued by your organizational CA, or generate a private CA for
this installation with OpenSSL. Keep the CA signing key offline; never mount it.
Certificate files must be readable by the service account; private keys should
be readable only by its service group (Elasticsearch uses uid 1000, gid 0).
The mounted app CA contains no private key. Redis uses server TLS + password,
without requiring client certificates. HTTP Elasticsearch and Redis plaintext
ports are disabled. All clients validate certificates and hostnames; production
configuration refuses missing authentication or plaintext infrastructure.

Run `PRODUCTION_ENV_FILE=.env.production scripts/start-production.sh`.
For GPU use `scripts/start-production.sh docker-compose.gpu.yml`.
Review effective configuration privately (it contains secrets):
`docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml --profile infra config`.
Run health checks and verify anonymous requests fail before routing public traffic.
For managed infrastructure, override Redis host/port, `CELERY_BROKER_URL` and
`CELERY_RESULT_BACKEND` with `rediss://` URLs, Elasticsearch URL with `https://`,
and MinIO endpoint; supply the appropriate combined CA bundle. Start application
services explicitly instead of enabling the infra profile. Never disable
certificate verification to accommodate self-signed certificates.

The stock Elasticsearch account is bootstrap/admin access: after initial setup,
provision an application user with privileges restricted to `job_results`,
`page_results`, `crawler_jobs` (including index creation and read/write), then set
`ELASTICSEARCH_USER/PASSWORD` on applications. Keep `ELASTIC_BOOTSTRAP_PASSWORD` set to the server's bootstrap password when
configuring a separate application account. Likewise provision MinIO
application credentials limited to the five configured buckets when possible.

Image tags remain updateable supply-chain inputs: review and pin image digests in
a deployment-specific override, scan images, and rebuild for patched base images.
Python CPU/GPU dependency builds outside the hashed ASR locks currently resolve
unpinned transitive dependencies; reproducible hashed locks remain follow-up work.

Set `TRUSTED_PROXY_IPS` to the exact IP address(es) of your ingress peer as seen
by the API container, separated by commas. Empty disables forwarded-header
trust. Never use `*` or a broad CIDR. See [authentication ingress](../security-auth-ingress.md).
