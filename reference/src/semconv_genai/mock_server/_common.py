"""Shared helpers for mock server provider modules."""

import binascii
import json
import struct


def sse(obj):
    """Format an OpenAI-style SSE ``data:`` line."""
    return f"data: {json.dumps(obj)}\n\n"


def mock_tool_argument_value(name, schema):
    schema_type = (schema or {}).get("type")
    if name == "location":
        return "Seattle"
    if name == "message":
        return "This is a response from the mock server."
    if schema_type == "string":
        return f"mock-{name}"
    if schema_type in {"integer", "number"}:
        return 1
    if schema_type == "boolean":
        return True
    if schema_type == "array":
        return []
    if schema_type == "object":
        return {}
    return f"mock-{name}"


def mock_tool_arguments(tool):
    function = (tool or {}).get("function", {})
    parameters = function.get("parameters") or (tool or {}).get("parameters") or (tool or {}).get("input_schema", {})
    properties = parameters.get("properties", {})
    required = parameters.get("required", [])

    argument_names = list(required) or list(properties)
    if not argument_names:
        return {"value": "mock-value"}

    return {name: mock_tool_argument_value(name, properties.get(name, {})) for name in argument_names}


def encode_aws_event_stream_message(event_type, payload_bytes):
    """Encode a single AWS event-stream binary message.

    Format (all big-endian):
      total_length (4) | headers_length (4) | prelude_crc (4)
      headers (variable) | payload (variable) | message_crc (4)
    """

    def _crc32(data):
        return binascii.crc32(data) & 0xFFFFFFFF

    def _encode_header(name, value):
        name_bytes = name.encode("utf-8")
        value_bytes = value.encode("utf-8")
        # 1 byte name len + name + 1 byte type (7=string) + 2 bytes value len + value
        return (
            struct.pack("!B", len(name_bytes))
            + name_bytes
            + struct.pack("!B", 7)
            + struct.pack("!H", len(value_bytes))
            + value_bytes
        )

    headers = b""
    headers += _encode_header(":message-type", "event")
    headers += _encode_header(":event-type", event_type)
    headers += _encode_header(":content-type", "application/json")

    total_length = 4 + 4 + 4 + len(headers) + len(payload_bytes) + 4
    prelude = struct.pack("!II", total_length, len(headers))
    prelude_crc = struct.pack("!I", _crc32(prelude))
    message_no_crc = prelude + prelude_crc + headers + payload_bytes
    message_crc = struct.pack("!I", _crc32(message_no_crc))
    return message_no_crc + message_crc
