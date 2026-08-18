# openai-assistants

The OpenAI Assistants API creates and runs assistants server-side. The client
owns the create-agent and invoke-agent client operations and executes
function-tool calls locally. The model call runs server-side inside the
assistant run; the `file_search` tool also runs server-side.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| create_agent | Yes — creates the assistant | ✅ Implemented |
| invoke_agent (client) | Yes — runs the assistant (threads / runs) | ✅ Implemented |
| execute_tool | Yes — client-side function-tool execution | ✅ Implemented |
| inference (`chat`) | No — runs server-side inside the assistant run | ✅ Correctly not emitted |
| retrieval | No — `file_search` runs server-side | ✅ Correctly not emitted |
