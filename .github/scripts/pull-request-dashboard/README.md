# Pull request dashboard implementation notes

This directory contains the scripts behind the pull request dashboard workflow.
The dashboard is a maintainer aid, not a transactional notification system, so
some rare timing and notification edge cases are intentionally accepted.

## Intentional tradeoffs

- The Slack notification state is PR-granular. It does not track notification
  history separately for each assignee.
- When the notification state is first created, existing approver-routed PRs
  may receive initial notifications on the next run. Avoiding that bootstrap
  case would require storing a separate seen-but-not-notified state.
- When a mapped assignee is added after the PR was already notified during the
  same waiting period, that assignee may wait until the next follow-up cadence
  instead of receiving an immediate initial notification.
- Slack notifications are sent only for dashboard state that has already been
  accepted on the state branch. A newer dashboard update can land after the
  notification job checks out state, so a notification can be slightly late
  relative to the newest state, but it still reflects an accepted dashboard
  state rather than a fabricated one.
- The notification job preserves just-written notification state across normal
  state-branch CAS retries. If Slack delivery succeeds and every state-branch
  push attempt is rejected, a later run can send the same notification again.
  Recording the state before sending Slack would avoid that duplicate window,
  but could instead record notifications that were never delivered.
- Dashboard publishing is serialized and each publish job fetches the accepted
  state branch while holding the publish slot. If another update advances the
  state branch while a publish job is already editing the issue, the live issue
  can briefly lag the newest accepted state until the next publish job runs.
