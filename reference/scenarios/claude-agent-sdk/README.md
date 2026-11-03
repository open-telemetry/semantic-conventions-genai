# claude-agent-sdk

The Claude Agent SDK drives an agent loop inside the Claude CLI subprocess. It
**owns the model call** across that subprocess boundary — no in-process
instrumentable library observes it — so it is the inference boundary here. The
run is itself an agent invocation (tools, multiple turns). Tools run inside the
CLI subprocess, but the CLI calls the SDK's `PreToolUse`, `PostToolUse`, and
`PostToolUseFailure` hook callbacks in-process around each tool execution.

`ClaudeAgentOptions.settings` enables a plugin from a directory marketplace.
The `init` system message lists each loaded plugin with its name, version, and
`name@marketplace` source. Claude Code addresses plugin skills as
`<plugin>:<skill>`, so a `Skill` tool call names the plugin that provides the
skill. `gen_ai.skill.name` records that name unchanged. Plugins loaded from
`ClaudeAgentOptions.plugins` report a placeholder source such as
`name@inline`, which only restates the name, so `gen_ai.plugin.id` is not
recorded for them.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| invoke_agent | Yes — `query()` drives the Claude Code agent loop (tools, multiple turns) | ❌ Not implemented (the scenario models the run as `chat`) |
| inference (`chat`) | Yes — owns the model call across the CLI subprocess | ✅ Implemented |
| execute_tool | Yes — `PreToolUse` / `PostToolUse` hook callbacks run in-process around each tool execution | ✅ Implemented for a plugin skill loaded through the `Skill` tool |