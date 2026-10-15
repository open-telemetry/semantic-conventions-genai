"""The MCP server `scenario.py` talks to, built with the SDK's lowlevel `Server` and served over stdio.

Its stdout is the MCP channel, so nothing in this process prints to it.
"""

import contextlib
import sys

import anyio
from mcp import MCPError, types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from reference_shared import flush_and_shutdown, setup_otel
from scenario import instrument_streams, suppress_sdk_spans

WEATHER_TOOL = types.Tool(
    name="get_weather",
    description="Get the current weather for a city.",
    input_schema={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)
WEATHER_PROMPT = types.Prompt(
    name="weather_report",
    description="Ask for a short weather report for a city.",
    arguments=[types.PromptArgument(name="city", required=True)],
)
WEATHER_RESOURCE = types.Resource(name="paris_weather", uri="weather://paris", mime_type="text/plain")


async def list_tools(ctx, params):
    return types.ListToolsResult(tools=[WEATHER_TOOL])


async def call_tool(ctx, params: types.CallToolRequestParams):
    if params.name != WEATHER_TOOL.name:
        # MCP answers a call to an unknown tool with a JSON-RPC protocol error.
        raise MCPError(code=types.INVALID_PARAMS, message=f"Unknown tool: {params.name}")
    city = params.arguments["city"]
    return types.CallToolResult(content=[types.TextContent(type="text", text=f"Sunny in {city}")])


async def list_prompts(ctx, params):
    # Serving prompts/list is what makes the server advertise the prompts capability.
    return types.ListPromptsResult(prompts=[WEATHER_PROMPT])


async def get_prompt(ctx, params: types.GetPromptRequestParams):
    city = params.arguments["city"]
    message = types.PromptMessage(
        role="user", content=types.TextContent(type="text", text=f"Write a short weather report for {city}.")
    )
    return types.GetPromptResult(messages=[message])


async def list_resources(ctx, params):
    # Serving resources/list is what makes the server advertise the resources capability.
    return types.ListResourcesResult(resources=[WEATHER_RESOURCE])


async def read_resource(ctx, params: types.ReadResourceRequestParams):
    if params.uri != WEATHER_RESOURCE.uri:
        raise MCPError(code=-32002, message=f"Resource not found: {params.uri}")
    contents = types.TextResourceContents(uri=params.uri, mime_type="text/plain", text="Sunny, 22°C")
    return types.ReadResourceResult(contents=[contents])


async def serve():
    server = Server(
        "weather",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        on_list_prompts=list_prompts,
        on_get_prompt=get_prompt,
        on_list_resources=list_resources,
        on_read_resource=read_resource,
    )
    async with stdio_server() as (read_stream, write_stream):
        # stdio talks to the client over this process's stdin and stdout pipes.
        read_stream, write_stream = instrument_streams(read_stream, write_stream, network_transport="pipe")
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    tp, lp, mp = setup_otel()
    suppress_sdk_spans()
    anyio.run(serve)
    # Keep flush_and_shutdown's progress output off the MCP channel.
    with contextlib.redirect_stdout(sys.stderr):
        flush_and_shutdown(tp, lp, mp)


if __name__ == "__main__":
    main()
