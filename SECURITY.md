# Security

Do not include credentials, tokens, private documents, or exploit details in a public issue. Use GitHub private vulnerability reporting if it is enabled for this repository; otherwise establish a private channel with the repository owner before sharing sensitive details. No response-time commitment or supported release series has been established.

Security checks cover the current source, newly introduced commits, frontend dependencies, and resolved backend deployment profiles. Production rejects WhisperX and Diart runtimes while their dependency advisories remain unresolved. Development-only access is not a statement that these runtimes are safe for untrusted workloads. See [dependency review](docs/security-python-dependencies.md) and [authentication ingress](docs/security-auth-ingress.md).

The repository is already public. Historical exposures require containment and validation across installations; unresolved exposures and restricted runtime dependencies keep the release-readiness checks red. Passing ordinary pull-request checks does not establish that exposed credentials are revoked. See [historical review and owner actions](docs/security-history-review.md). The manual release-readiness workflow audits the complete fetched history and every Python profile. It cannot prevent or change repository visibility and does not publish anything.
