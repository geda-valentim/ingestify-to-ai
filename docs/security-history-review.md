# Historical security review

Reviewed on 2026-10-06 using Gitleaks 8.30.1 over every locally available Git ref (`git --log-opts=--all`). The original scan produced 50 occurrences. Private raw reports remain outside the repository; this document contains no credential values.

| Classification | Occurrences | Disposition |
| --- | ---: | --- |
| Example curl credentials or placeholders | 21 | Proven false positives |
| Synthetic generic API-key fixtures | 5 | Proven false positives |
| Synthetic JWT redaction fixture | 1 | Proven false positive |
| Descriptive cryptographic construction text | 1 | Proven false positive |
| Public React Fast Refresh hook signatures | 2 | Proven false positives |
| Historical API key in conversion-monitor script | 1 | Publicly exposed; containment unresolved |
| Next.js build encryption/signing material | 19 | Publicly exposed; containment unresolved |

The 30 false positives have exact historical fingerprint exceptions in `.gitleaksignore`. Source examples additionally have exact literal, rule and file exceptions in `.gitleaks.toml`, so moving an example does not require ignoring its whole file. New credentials in those same files must still trigger the scanner. The Compose healthcheck's literal environment-variable reference and an additional Portuguese documentation placeholder found on another local ref are also narrowly excluded. The latter extends the original 50-occurrence scan by one proven false positive; it does not add a historical fingerprint ignore. None of the 20 exposures is ignored. The repository is already PUBLIC, as confirmed by the owner through GitHub on this date; these are existing public exposures, not merely a future publication risk.

The historical API key appeared in `scripts/test_conversion_monitor.py`, commit `73429472a68858eba2e40c666889591a5e26932b`, line 25. A private hash comparison found zero matching rows in the inspected current development database. The Next.js material represents 13 distinct values across 19 occurrences in committed `.next` build metadata and server-reference manifests. Private hash comparisons found zero matches in the inspected current frontend manifests. These checks establish absence in that inspected installation only; they do not establish revocation or non-use elsewhere.

## Owner actions for containment and release approval

1. Inventory every installation, environment, image, build artifact, backup, and database that could have used these revisions. Confirmation about other installations is still pending.
2. Compare historical API-key hashes against each installation privately. Revoke or rotate any matching or potentially reused key and confirm old keys are rejected. Record installation identifiers and completed actions without recording credentials.
3. Regenerate and redeploy affected Next.js builds with fresh preview/signing and server-action encryption material. Account for explicitly configured shared encryption keys, cached images, and old instances still serving traffic. Verify exposed values no longer match active deployments.
4. Review forks, clones, CI artifacts and distribution caches. Rotation addresses credential use; it does not remove already distributed history. Any history rewrite or visibility change requires an explicit owner decision and is outside this change.
5. Run the manual `Release readiness checks` workflow and resolve both history findings and restricted runtime dependency advisories. Do not interpret ordinary PR checks as containment or release clearance.

This change did not rewrite history, change repository visibility, or send external incident messages. The repository was already public. The full-history scanner intentionally remains red for the 20 historical exposures. Local refs cannot prove coverage of deleted remote refs, unknown forks, other installations, or artifacts outside Git.

## CI behavior

`Security checks` runs on pushes and pull requests with read-only permissions and pinned action commits. It scans a snapshot of tracked and non-ignored untracked source plus the introduced commit range. Generated ignored files are omitted only when Git does not track them; tracked historical artifacts are never exempted by directory. Symlinks are scanned as link text rather than followed outside the checkout. A new branch with an all-zero previous revision scans from its merge base with the fetched repository default branch. An unavailable base fails the check; historical exposures are handled by the separate release-readiness workflow. Gitleaks is downloaded at a pinned version and verified against a fixed SHA-256 checksum. Reports are redacted, remain temporary, and only finding metadata is printed.

Frontend checks use `npm ci --ignore-scripts`, audit all dependency categories, and build explicitly. Backend checks install hash-locked audit tools, resolve six ordinary deployment profiles, and audit every resolved package plus test, audit-tool and Modal locks. The manual release-readiness workflow also audits all seven restricted ASR/Diart locks. Direct wheel URLs are converted to their actual package versions for advisory lookup; malformed, unpinned, skipped or unavailable advisory coverage fails the gate. Restricted-profile advisories are not suppressed. Python platform coverage here is Linux x86_64, Python 3.13 resolution; other platforms require their own resolved audits.
