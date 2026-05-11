# Dependency update tooling

This repository uses **both** Renovate and Dependabot, with strictly
separated responsibilities. Do not enable a feature in one tool that the
other already owns.

## Split of responsibilities

| Concern                                    | Tool        |
| ------------------------------------------ | ----------- |
| Routine version updates (direct deps)      | Renovate    |
| GitHub Actions updates                     | Renovate    |
| `versions.env` custom regex updates        | Renovate    |
| Security updates for **direct** deps       | Dependabot  |
| Security updates for **transitive** deps   | Dependabot  |
| Lockfile bumps triggered by CVE alerts     | Dependabot  |

Configuration files:

- [renovate.json5](renovate.json5)
- [dependabot.yml](dependabot.yml)

## Why the split

Renovate does not manage transitive dependencies and only raises OSV
vulnerability alerts for **direct** dependencies. From the Renovate docs:

> Renovate does not currently manage any transitive dependencies - instead
> leaving that to package managers and lockFileMaintenance.
> &mdash; <https://docs.renovatebot.com/key-concepts/minimum-release-age/#what-happens-to-transitive-dependencies>

and

> You will only get OSV-based vulnerability alerts for direct dependencies.
> &mdash; <https://docs.renovatebot.com/configuration-options/#osvvulnerabilityalerts>

The workarounds inside Renovate (scheduled `lockFileMaintenance`) are
blunt: they refresh every transitive on a timer regardless of whether a
CVE exists, and they are not driven by GitHub security advisories.

Dependabot, in contrast, is alert-driven: when a GitHub advisory matches a
direct or transitive dependency in any tracked manifest/lockfile, it opens
a PR that bumps exactly what is needed to resolve the advisory, and links
the advisory in the PR body for audit purposes.
