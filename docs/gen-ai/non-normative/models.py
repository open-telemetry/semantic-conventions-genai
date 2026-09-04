"""
GenAI messages Python models.

Defines Python models for system instructions, input/output messages, tool
definitions, retrieval documents, and memory records. These models are
provided for reference only.

Running this script regenerates the JSON schemas committed under
`model/gen-ai/gen-ai-*.json`.

Dependencies and their locked versions are declared in the sibling
`pyproject.toml` / `uv.lock`, so the generation is reproducible.

Run with:

    cd docs/gen-ai/non-normative && uv run models.py [output_dir]

or, from the repo root, `make generate-json-schemas`.
"""

from __future__ import annotations

import argparse
import json
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, List, Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
    RootModel,
)
from pydantic_core import core_schema


# --------------------------------------------------------------------------
# Common message-part models
# --------------------------------------------------------------------------


class TextPart(BaseModel):
    """
    Represents text content sent to or received from the model.
    """

    type: Literal["text"] = Field(
        description="The type of the content captured in this part."
    )
    content: str = Field(description="Text content sent to or received from the model.")

    model_config = ConfigDict(extra="allow")


class ToolCallRequestPart(BaseModel):
    """
    Represents a tool call requested by the model.
    """

    type: Literal["tool_call"] = Field(
        description="The type of the content captured in this part."
    )
    id: Optional[str] = Field(
        default=None, description="Unique identifier for the tool call."
    )
    name: str = Field(description="Name of the tool.")
    arguments: Any = Field(default=None, description="Arguments for the tool call.")

    model_config = ConfigDict(extra="allow")


class ToolCallResponsePart(BaseModel):
    """
    Represents a tool call result sent to the model or a built-in tool call outcome and details.
    """

    type: Literal["tool_call_response"] = Field(
        description="The type of the content captured in this part."
    )
    id: Optional[str] = Field(default=None, description="Unique tool call identifier.")
    response: Any = Field(description="Tool call response.")

    model_config = ConfigDict(extra="allow")


class GenericServerToolCall(BaseModel):
    """
    Represents an arbitrary server tool call with any type and properties.
    This allows for extensibility with custom server tool types.
    """

    type: str = Field(description="Type identifier for the server tool call.")

    model_config = ConfigDict(extra="allow")


class GenericServerToolCallResponse(BaseModel):
    """
    Represents an arbitrary server tool call response with any type and properties.
    This allows for extensibility with custom server tool response types.
    """

    type: str = Field(description="Type identifier for the server tool call response.")

    model_config = ConfigDict(extra="allow")


# Polymorphic server tool call / response unions. The catch-all Generic*
# variants are the only members today; add concrete provider-specific types
# (e.g. web search, code interpreter) here as they are modeled.
ServerToolCall = Union[GenericServerToolCall,]

ServerToolCallResponse = Union[GenericServerToolCallResponse,]


class ServerToolCallPart(BaseModel):
    """Represents a server-side tool call invocation. Server tool calls are executed by the model provider on the server side rather than by the client application. Provider-specific tools (e.g., code_interpreter, web_search) can have well-defined schemas defined by the respective providers."""

    type: Literal["server_tool_call"] = Field(
        description="The type of the content captured in this part."
    )
    id: Optional[str] = Field(
        default=None, description="Unique identifier for the server tool call."
    )
    name: str = Field(description="Name of the server tool.")
    server_tool_call: ServerToolCall = Field(
        description="Polymorphic server tool call details with type discriminator. The structure varies based on the tool type.",
    )

    model_config = ConfigDict(extra="allow")


class ServerToolCallResponsePart(BaseModel):
    """Represents a server-side tool call response. Contains the outcome and details of a server tool execution. Provider-specific tools (e.g., code_interpreter, web_search) can have well-defined response schemas defined by the respective providers."""

    type: Literal["server_tool_call_response"] = Field(
        description="The type of the content captured in this part."
    )
    id: Optional[str] = Field(
        default=None,
        description="Unique server tool call identifier matching the original call.",
    )
    server_tool_call_response: ServerToolCallResponse = Field(
        description="Polymorphic server tool call response with type discriminator. The structure varies based on the tool type.",
    )

    model_config = ConfigDict(extra="allow")


class Modality(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class ReasoningPart(BaseModel):
    """
    Represents reasoning/thinking content received from the model.
    """

    type: Literal["reasoning"] = Field(
        description="The type of the content captured in this part."
    )
    content: str = Field(
        description="Reasoning/thinking content received from the model."
    )

    model_config = ConfigDict(extra="allow")


class CompactionPart(BaseModel):
    """
    Represents compacted conversation state sent to or received from the model.
    """

    type: Literal["compaction"] = Field(
        description="The type of the content captured in this part."
    )
    id: Optional[str] = Field(
        default=None,
        description="Provider-assigned identifier for the compaction item or block.",
    )
    content: Optional[str] = Field(
        default=None,
        description="The unencrypted compacted conversation summary, when available.",
    )

    model_config = ConfigDict(extra="allow")


class BlobPart(BaseModel):
    """Represents blob binary data sent inline to the model"""

    type: Literal["blob"] = Field(
        description="The type of the content captured in this part."
    )
    mime_type: Optional[str] = Field(
        default=None, description="The IANA MIME type of the attached data."
    )
    modality: Union[Modality, str] = Field(
        description="The general modality of the data if it is known. Instrumentations SHOULD also set the mimeType field if the specific type is known."
    )
    content: bytes = Field(
        description="Raw bytes of the attached data. This field SHOULD be encoded as a base64 string when serialized to JSON."
    )


class FilePart(BaseModel):
    """Represents an external referenced file sent to the model by file id"""

    type: Literal["file"] = Field(
        description="The type of the content captured in this part."
    )
    mime_type: Optional[str] = Field(
        default=None, description="The IANA MIME type of the attached data."
    )
    modality: Union[Modality, str] = Field(
        description="The general modality of the data if it is known. Instrumentations SHOULD also set the mimeType field if the specific type is known."
    )
    file_id: str = Field(
        description="An identifier referencing a file that was pre-uploaded to the provider."
    )

    model_config = ConfigDict(extra="allow")


class UriPart(BaseModel):
    """Represents an external referenced file sent to the model by URI"""

    type: Literal["uri"] = Field(
        description="The type of the content captured in this part."
    )
    mime_type: Optional[str] = Field(
        default=None, description="The IANA MIME type of the attached data."
    )
    modality: Union[Modality, str] = Field(
        description="The general modality of the data if it is known. Instrumentations SHOULD also set the mimeType field if the specific type is known."
    )
    uri: str = Field(
        description=(
            "A URI referencing attached data. It should not be a base64 data URL, "
            "which should use the `blob` part instead. The URI may use a scheme known to "
            "the provider api (e.g. `gs://bucket/object.png`), or be a publicly accessible location."
        )
    )

    model_config = ConfigDict(extra="allow")


class GenericPart(BaseModel):
    """
    Represents an arbitrary message part with any type and properties.
    This allows for extensibility with custom message part types.
    """

    type: str = Field(description="The type of the content captured in this part.")

    model_config = ConfigDict(extra="allow")


# This Union without discriminator will generate anyOf in JSON schema
MessagePart = Union[
    TextPart,
    ToolCallRequestPart,
    ToolCallResponsePart,
    ServerToolCallPart,
    ServerToolCallResponsePart,
    BlobPart,
    FilePart,
    UriPart,
    ReasoningPart,
    CompactionPart,
    GenericPart,  # Catch-all for any other type
    # Add other message part types here as needed,
    # e.g. structured output, hosted tool call, etc.
]

# System instructions are modeled as their own list of parts, independent of
# the input/output message parts. TextPart is the only member today;
# add other system instruction part types once there is an existing
# provider with non-text system instructions.
SystemInstructionPart = Union[
    TextPart,
    GenericPart,  # Catch-all for any other type
    # Add other message part types here as needed
]


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(BaseModel):
    role: Union[Role, str] = Field(
        description="Role of the entity that created the message."
    )
    parts: List[MessagePart] = Field(
        description="List of message parts that make up the message content."
    )
    name: Optional[str] = Field(
        default=None, description="The name of the participant."
    )

    model_config = ConfigDict(extra="allow")


# --------------------------------------------------------------------------
# `gen_ai.input.messages` model
# --------------------------------------------------------------------------


class InputMessages(RootModel[List[ChatMessage]]):
    """
    Represents the list of input messages sent to the model.
    """

    pass


# --------------------------------------------------------------------------
# `gen_ai.output.messages` model
# --------------------------------------------------------------------------


class FinishReason(StrEnum):
    """
    Represents the reason for finishing the generation.
    """

    STOP = "stop"
    LENGTH = "length"
    CONTENT_FILTER = "content_filter"
    TOOL_CALL = "tool_call"
    COMPACTION = "compaction"
    ERROR = "error"


class OutputMessage(ChatMessage):
    """
    Represents an output message generated by the model or agent. The output message captures
    specific response (choice, candidate).
    """

    finish_reason: Optional[Union[FinishReason, str]] = Field(
        default=None,
        description=(
            "Deprecated: report finish reasons in `gen_ai.response.finish_reasons` instead. "
            "Reason for finishing the generation."
        ),
        deprecated=True,
    )


class OutputMessages(RootModel[List[OutputMessage]]):
    """
    Represents the list of output messages generated by the model or agent.
    """

    pass


# --------------------------------------------------------------------------
# `gen_ai.system_instructions` model
# --------------------------------------------------------------------------


class SystemInstructions(RootModel[List[SystemInstructionPart]]):
    """
    Represents the system instructions provided to the model.
    """

    pass


# --------------------------------------------------------------------------
# `gen_ai.tool.definitions` model
# --------------------------------------------------------------------------


class JsonSchemaDraft7:
    """Metadata for Pydantic: exported JSON Schema references draft-07; core validation stays permissive."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ):
        return core_schema.any_schema()

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema_obj, handler: GetJsonSchemaHandler
    ):
        # Single-branch anyOf avoids a top-level $ref so Pydantic does not resolve the external meta-schema URL as #/defs.
        return {"anyOf": [{"$ref": "http://json-schema.org/draft-07/schema#"}]}


# Runtime values are plain dicts (JSON object); type checkers see dict[str, Any]. JsonSchemaDraft7 only customizes JSON Schema export.
JsonSchemaDraft7Dict = Annotated[dict[str, Any], JsonSchemaDraft7]


class GenericToolDefinition(BaseModel):
    """
    Represents a tool definition in any form.
    """

    type: str = Field(description="The type of the tool.")
    name: str = Field(description="The name of the tool.")

    model_config = ConfigDict(extra="allow")


class FunctionToolDefinition(GenericToolDefinition):
    """
    Represents a tool definition in the form of a function.
    """

    type: Literal["function"] = Field(description="The type of the tool.")
    description: Optional[str] = Field(
        default=None,
        description=(
            "The description of the tool. "
            "Since this attribute could be large, it's NOT RECOMMENDED to be populated by default. "
            "Instrumentations MAY provide a way to enable populating this property."
        ),
    )
    parameters: Optional[JsonSchemaDraft7Dict] = Field(
        default=None,
        description=(
            "JSON Schema document describing the parameters accepted by the tool. "
            "The value MUST conform to JSON Schema draft-07. "
            "Since this attribute could be large, it's NOT RECOMMENDED to be populated by default. "
            "Instrumentations MAY provide a way to enable populating this property."
        ),
    )

    model_config = ConfigDict(extra="allow")


ToolDefinition = Union[
    FunctionToolDefinition,
    GenericToolDefinition,  # Catch-all for any other type
    # Add other tool definition types here as needed,
    # e.g. file search, code interpreter, etc
]


class ToolDefinitions(RootModel[List[ToolDefinition]]):
    """
    Represents the list of tool definitions available to the GenAI agent or model.
    """

    pass


# --------------------------------------------------------------------------
# `gen_ai.retrieval.documents` model
# --------------------------------------------------------------------------


class RetrievalDocument(BaseModel):
    """
    Represents a single document retrieved from a vector database or search system.
    """

    id: str | None = Field(
        default=None, description="A unique identifier for the document."
    )
    score: float | None = Field(
        default=None, description="The relevance score of the document."
    )

    model_config = ConfigDict(
        extra="allow"
    )  # Allows additional properties like content, metadata, title, uri, etc.


class RetrievalDocuments(RootModel[List[RetrievalDocument]]):
    """
    Represents the list of documents retrieved from a vector database or search system.
    """

    pass


# --------------------------------------------------------------------------
# `gen_ai.memory.records` model
# --------------------------------------------------------------------------


class MemoryRecord(BaseModel):
    """
    Represents a single memory record stored in or retrieved from a memory store.
    """

    content: Any = Field(description="The content of the memory record.")
    id: Optional[str] = Field(
        default=None, description="A unique identifier for the memory record."
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Provider-specific metadata associated with the memory record.",
    )
    score: Optional[float] = Field(
        default=None,
        description="The relevance score of the memory record when populated on search results.",
    )

    model_config = ConfigDict(extra="allow")


class MemoryRecords(RootModel[List[MemoryRecord]]):
    """
    Represents the list of memory records stored in or retrieved from a memory store.
    """

    pass


# --------------------------------------------------------------------------
# `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result` models
# --------------------------------------------------------------------------


class ToolCallArguments(RootModel[dict[str, Any]]):
    """
    Represents object-like arguments passed to a tool call.
    """

    pass


class ToolCallResult(RootModel[dict[str, Any]]):
    """
    Represents object-like results returned by a tool call.
    """

    pass


# --------------------------------------------------------------------------
# `gen_ai.skills` model
# --------------------------------------------------------------------------


class SkillInfo(BaseModel):
    """
    Represents a single skill whose instructions are in the agent's context.
    """

    name: str = Field(
        description="Name of the skill, from its SKILL.md frontmatter."
    )
    compacted: bool = Field(
        description="Whether the skill's instructions have been replaced by a summary."
    )

    model_config = ConfigDict(extra="allow")


class Skills(RootModel[List[SkillInfo]]):
    """
    Represents the skills in the agent's context and their current compaction status.
    """

    pass


# --------------------------------------------------------------------------
# Schema generation entry point
# --------------------------------------------------------------------------

# Maps committed JSON file name (under model/gen-ai/) -> root model class.
SCHEMAS: dict[str, type[BaseModel]] = {
    "gen-ai-input-messages.json": InputMessages,
    "gen-ai-output-messages.json": OutputMessages,
    "gen-ai-system-instructions.json": SystemInstructions,
    "gen-ai-tool-definitions.json": ToolDefinitions,
    "gen-ai-tool-call-arguments.json": ToolCallArguments,
    "gen-ai-tool-call-result.json": ToolCallResult,
    "gen-ai-retrieval-documents.json": RetrievalDocuments,
    "gen-ai-memory-records.json": MemoryRecords,
    "gen-ai-skills.json": Skills,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate the JSON schemas from the pydantic models."
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parents[3] / "model" / "gen-ai",
        help="Directory where the JSON schema files will be written. Defaults to repo_root/model/gen-ai.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[3]

    for filename, model in SCHEMAS.items():
        target = output_dir / filename
        with target.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(model.model_json_schema(), f, indent=4)
            f.write("\n")
        try:
            print(f"wrote {target.relative_to(repo_root)}")
        except ValueError:
            print(f"wrote {target}")


if __name__ == "__main__":
    main()
