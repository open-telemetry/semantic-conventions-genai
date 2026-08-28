---
name: pr-description
description: Write or edit concise pull request descriptions for this repository. Use whenever drafting, creating, opening, or updating a pull request, or when reviewing whether a pull request description matches its diff.
---

# Pull request descriptions

Write for maintainers who need to understand the change and why it belongs in this repository without reading a second version of the diff.

## Drafting

1. Read the complete diff against the pull request's base branch. Read linked issues when they explain requirements or decisions that the diff does not.
2. Start from [.github/PULL_REQUEST_TEMPLATE.md](../../PULL_REQUEST_TEMPLATE.md). Keep its required sections and checklist, but delete all instructional comments.
3. Open `Description` with one or two short sentences that state what changes and why it matters. Do not repeat the title.
4. In `Motivation`, name the user journey or decision the telemetry supports and cite relevant prior art. Do not use this section to repeat the implementation.
5. In `Prototype`, point to the reference scenarios or other end-to-end evidence. Explain only gaps or constraints that a reviewer cannot infer from the diff.
6. Keep checklist answers accurate. Do not add validation commands, a changed-files list, or extra boilerplate sections.
7. Add a concrete example near the top only when it explains a new public convention, compatibility concern, or migration. Keep it to the smallest example that makes the behavior clear.
8. Preserve issue-closing references, compatibility notes, risks, and design constraints that reviewers need.

For repository-only changes where a template section does not apply, use one short `N/A` sentence rather than inventing justification.

## Compression pass

Treat the first draft as raw material, then shorten it.

- Remove details visible from the diff, including file names and exhaustive lists of attributes.
- Remove chronological narration, review history, and arguments already settled in a linked issue.
- Remove repeated context across sections.
- Replace long paragraphs with one or two sentences. Use bullets only for genuinely parallel facts.
- Remove generic sections such as `Summary`, `Changes`, `Details`, `Testing`, and `Validation`.
- Keep the body as short as the change allows. There is no target word count.
- Do not hard-wrap prose.

Before creating or updating the pull request:

1. Apply the repository's [unslop skill](../unslop/SKILL.md) to the complete title and body.
2. Compare the result with the diff once more. Every sentence must help a reviewer understand the purpose, user-visible behavior, compatibility, risk, or a decision that the diff cannot explain by itself.
