# Security Policy

## Reporting a Vulnerability

- Please email security@hummingbot.org with a detailed report.
- Include steps to reproduce, affected versions/commits, and impact assessment.
- We will acknowledge within 72 hours and provide a remediation timeline.

## Supported Versions

We generally support the latest minor release on the main branch. Security fixes are backported on a best-effort basis.

## Dependency Updates

- Automated dependency updates via Dependabot/Renovate are enabled where possible.
- High and critical CVEs are prioritized; patches released as soon as validated.
- We pin base images and OS packages in Dockerfiles.

## Secrets Management

- Never commit secrets. Use environment variables, Kubernetes Secrets, or SealedSecrets.
- See `SECRETS_MANAGEMENT.md` for guidance, including rotation practices.

## Disclosure Policy

- Coordinated disclosure preferred. We will credit reporters when desired.