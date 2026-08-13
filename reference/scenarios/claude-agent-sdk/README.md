# claude-agent-sdk

The Claude Agent SDK drives an agent loop inside the Claude CLI subprocess. It
**owns the model call** across that subprocess boundary — no in-process
instrumentable library observes it — so it is the inference boundary here. The
run is itself an agent invocation (tools, multiple turns); tool execution
happens inside the CLI subprocess and is not observable in-process.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| invoke_agent | Yes — `query()` drives the Claude Code agent loop (tools, multiple turns) | ❌ Not implemented (the scenario models the run as `chat`) |
| inference (`chat`) | Yes — owns the model call across the CLI subprocess | ✅ Implemented |
| execute_tool | No — runs inside the Claude CLI subprocess | ✅ Correctly not emitted |