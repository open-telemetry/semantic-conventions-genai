# crewai

CrewAI is an **agent framework**. A crew is a workflow that invokes agents,
which call tools and plan. It delegates the actual model call to the underlying
LLM client, so it does **not** own inference — that belongs to the LLM library
and is captured as a child span.

| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | No — delegates to the LLM client | ✅ Correctly not emitted |
| invoke_agent (internal) | Yes — agent task execution (`Agent.kickoff`) | ✅ Implemented |
| invoke_workflow | Yes — crew execution (`Crew.kickoff`) | ✅ Implemented |
| plan | Yes — `CrewPlanner` planning phase | ✅ Implemented |
| execute_tool | Yes — CrewAI runs the tool | ✅ Implemented |

The tool execution error handlers record a correlated
`gen_ai.execute_tool.exception` WARN log and rethrow the exception. This scenario
does not exercise those paths.
