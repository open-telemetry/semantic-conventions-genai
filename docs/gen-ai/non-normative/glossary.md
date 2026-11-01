<!--- Hugo front matter used to generate the website version of this page:
linkTitle: Glossary
--->

# GenAI glossary

This non-normative glossary explains terms used in the GenAI semantic conventions.
The linked conventions define the recording requirements. Frameworks may use
different names for the same operations.

<!-- toc -->

- [GenAI glossary](#genai-glossary)
  - [Agent](#agent)
  - [Conversation](#conversation)
  - [Embeddings](#embeddings)
  - [Inference](#inference)
  - [Memory](#memory)
  - [Planning](#planning)
  - [Reasoning](#reasoning)
  - [Retrieval](#retrieval)
  - [Tool call](#tool-call)
  - [Workflow](#workflow)

<!-- tocstop -->

## Agent

A framework or service concept that uses model inference to carry out a task,
possibly by calling tools or other agents. An agent invocation need not include
a tool call, for example when an agent plans or routes a request using inference.

The conventions distinguish invoking a remote agent service with an
[`invoke_agent` client span](../gen-ai-agent-spans.md#invoke-agent-client-span)
from local agent execution with an
[`invoke_agent` internal span](../gen-ai-agent-spans.md#invoke-agent-internal-span).

## Conversation

A sequence of related messages and its associated state, also called a session
or thread by some libraries. A conversation can continue across several agent
or workflow invocations. A workflow involving multiple agents can use several
conversations.

[`gen_ai.conversation.id`](../../registry/attributes/gen-ai.md#gen-ai-conversation-id)
identifies an existing conversation; a trace identifier is not a substitute.

## Embeddings

An operation that converts input into numerical vectors used to represent that
input, for example for similarity search. The corresponding operation is
[`embeddings`](../gen-ai-spans.md#embeddings). Generating a query embedding and
retrieving matching documents are distinct operations.

## Inference

A model operation that generates a response or requests a tool call from input.
The [inference span](../gen-ai-spans.md#inference) covers operations such as
`chat`, `generate_content`, and `text_completion`. The conventions describe
embedding operations separately.

## Memory

Information maintained by a memory system for later use by an agent or
application. [Memory operations](../gen-ai-spans.md#memory) cover memory store
lifecycle and creating, updating, upserting, searching, or deleting records.
The term refers to the library's memory abstraction, not process RAM.

## Planning

An agent's decision phase that formulates a strategy or decomposes a task before
execution. A [`plan` span](../gen-ai-agent-spans.md#plan-span) represents an
operation that instrumentation can distinguish from generic reasoning or
ordinary inference. A model call that produces a plan can be a child of that
operation.

## Reasoning

A model's thinking or intermediate reasoning during inference. The conventions
can capture reasoning content in a `reasoning` message part and the provider's
reported usage in
[`gen_ai.usage.reasoning.output_tokens`](../../registry/attributes/gen-ai.md#gen-ai-usage-reasoning-output-tokens).
Reasoning content alone does not identify a separate planning operation.

## Retrieval

An operation that obtains relevant information or context from a search system
or vector database. The corresponding operation is
[`retrieval`](../gen-ai-spans.md#retrievals). A framework may use retrieval as
part of an agent or workflow, or expose it directly to the caller.

## Tool call

A request to execute a tool, such as a function, an extension, or a data-store
query. A model can request a tool call as part of its inference output; the
request and the subsequent execution are different operations.

The [`execute_tool` span](../gen-ai-spans.md#execute-tool-span) describes the
execution. Tool calls can also represent agent handoffs when the framework
implements a handoff as a tool.

## Workflow

A coordinated process composed of multiple agents or other operations involving
generative AI. Frameworks may call this a graph, chain, crew, or orchestrator.
The [`invoke_workflow` span](../gen-ai-agent-spans.md#invoke-workflow-span)
represents an invocation of that process. Workflows can nest; a workflow is not
necessarily the outermost operation in a trace. A standalone agent invocation
does not, by itself, constitute a workflow invocation.
