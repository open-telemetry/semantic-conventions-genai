# google-adk

The Google Agent Development Kit (ADK) is an agent framework. It calls models
through its model layer (e.g. `google-genai`), so it **delegates inference**. It
owns the agent, workflow, tool, and memory operations it runs directly.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the model client (`google-genai`) | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — agent run | ✅ Implemented |
| invoke_workflow | Yes — workflow agents (e.g. `SequentialAgent`) | ✅ Implemented |
| execute_tool | Yes — ADK runs the tool | ✅ Implemented |
| memory | Yes — memory service upsert / search | ✅ Implemented |
| workflow inference/tool call counts | Yes — runner plugin over a `SequentialAgent` run | ✅ Implemented |

The workflow-count example runs a researcher with a weather tool followed by a
writer in a `SequentialAgent`. A runner plugin counts calls from every agent,
and the totals are recorded in a `finally` so a failed run still reports.
