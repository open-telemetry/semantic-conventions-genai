---
name: code-review
description: Review a changelist against the team's review policy. Use when asked to review, critique, or sign off on a code change.
---

# Code review

1. Read `references/review_policy.md` for the rules this team enforces.
2. Run `scripts/run_checks.py` over the changed files.
   Run `scripts/check_format.py` to confirm the change is formatted.
3. Report each violation with the policy rule it breaks.
