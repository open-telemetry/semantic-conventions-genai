"""Mock LLM server for reference implementation testing.

Provides OpenAI-compatible, Anthropic-compatible, Google GenAI, AWS Bedrock,
Cohere, and OpenAI Assistants endpoints that return deterministic responses.
No real LLM calls are made.

Provider endpoints are split across per-provider modules and registered as
Flask blueprints on a single app.
"""

import argparse

from flask import Flask

from . import anthropic, assistants, bedrock, bedrock_agent, bedrock_agentcore, cohere, google_genai, openai

app = Flask(__name__)

for module in (openai, anthropic, google_genai, bedrock, bedrock_agent, bedrock_agentcore, cohere, assistants):
    app.register_blueprint(module.bp)


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


def main():
    parser = argparse.ArgumentParser(description="Mock LLM server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
