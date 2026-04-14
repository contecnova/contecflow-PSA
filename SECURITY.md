# Security Governance

## Vulnerability Exception Policy

The repository uses `security/vulnerability-exceptions.json` as the single source of truth
for temporary vulnerability exceptions.

Rules:

- Every exception must include a ticket, reason, approvers and expiry date.
- Expired exceptions fail CI immediately.
- Exceptions are temporary risk acceptance only.
- PRs changing the exception file require dual approval.
- A security approver is required when defined in `.github/security-approvers.txt`.

## CI/CD Supply Chain Controls

Mandatory controls enforced in CI:

- SAST: Semgrep + Bandit
- SCA: pip-audit + npm audit + Trivy vuln scan
- DAST: OWASP ZAP baseline
- SBOM: Syft CycloneDX generation
- Signature: cosign sign/verify for SBOM artifact

Mandatory controls enforced in CD:

- Container image signing by digest (cosign keyless)
- Signature verification in-pipeline
- Image SBOM generation and cosign attestations

## Setup Notes

Maintain `.github/security-approvers.txt` with GitHub usernames to enforce
that at least one security owner approves vulnerability exception changes.