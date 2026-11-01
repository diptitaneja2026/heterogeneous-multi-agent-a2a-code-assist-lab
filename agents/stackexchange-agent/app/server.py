# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A2A server for the Stack Exchange agent (a2a-sdk 1.x).

In a2a-sdk 1.x there is no ``A2AStarletteApplication`` wrapper; you mount A2A
routes onto an ASGI app yourself. We serve:

- the agent card at ``/.well-known/agent-card.json``
- the JSON-RPC endpoint at ``/a2a/jsonrpc``

For backward compatibility with 0.3.x clients (the root Code Assist agent's ADK
``RemoteA2aAgent``), the card advertises BOTH a ``1.0`` and a ``0.3`` interface
and the JSON-RPC routes are created with ``enable_v0_3_compat=True``. This makes
``agent_card_to_dict`` emit the legacy top-level ``url``/``preferredTransport``
fields a 0.3.x client requires, and lets the server accept legacy payloads.

Run it with::

    uvicorn app.server:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import os

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from starlette.applications import Starlette

from app.agent_executor import StackExchangeExecutor

# Media types this agent accepts/produces (must be valid media types in 1.x).
_CONTENT_TYPES = ["text/plain"]

# Path where the JSON-RPC endpoint is mounted.
RPC_PATH = "/a2a/jsonrpc"


def build_agent_card(public_url: str) -> AgentCard:
    """Builds the A2A agent card advertised at the well-known path.

    Advertises a 1.0 and a 0.3 interface (same JSON-RPC endpoint) so both
    modern and legacy clients can route to it.

    Args:
        public_url: Externally reachable base URL of this server (no trailing
            path), e.g. ``https://stackexchange.example.com``.

    Returns:
        The populated :class:`AgentCard`.
    """
    rpc_url = f"{public_url.rstrip('/')}{RPC_PATH}"
    return AgentCard(
        name="StackExchangeAgent",
        description=(
            "Searches Stack Exchange for programming questions and errors and "
            "returns a single consolidated answer. Deterministic (no LLM)."
        ),
        version="1.0.0",
        # TODO(challenge): Advertise BOTH a 1.0 and a 0.3 JSONRPC interface on the same rpc_url so the ADK 0.3 client can parse this 1.x card.
        supported_interfaces=[
            AgentInterface(
                url=rpc_url,
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            ),
            AgentInterface(
                url=rpc_url,
                protocol_binding="JSONRPC",
                protocol_version="0.3",
            ),
        ],
        default_input_modes=_CONTENT_TYPES,
        default_output_modes=_CONTENT_TYPES,
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="search_stackexchange",
                name="Search Stack Exchange",
                description=(
                    "Takes a query and returns a consolidated Stack Exchange "
                    "answer, useful for errors and debugging."
                ),
                tags=["search", "stackexchange", "errors", "debugging"],
                examples=["How do I fix a 500 Internal Server Error in FastAPI?"],
            )
        ],
    )


def build_app() -> Starlette:
    """Assembles the A2A Starlette application from env configuration."""
    port = int(os.environ.get("PORT", "8080"))
    # PUBLIC_URL is the external address clients use to reach this server. It
    # defaults to localhost for local runs; set it to the GKE ingress/LB URL in
    # production so the agent card advertises a reachable endpoint.
    public_url = os.environ.get("PUBLIC_URL", f"http://localhost:{port}")
    card = build_agent_card(public_url)

    request_handler = DefaultRequestHandler(
        agent_executor=StackExchangeExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    agent_card_routes = create_agent_card_routes(agent_card=card)
    jsonrpc_routes = create_jsonrpc_routes(
        request_handler=request_handler,
        rpc_url=RPC_PATH,
        enable_v0_3_compat=True,
    )
    return Starlette(routes=[*agent_card_routes, *jsonrpc_routes])


# ASGI app object for `uvicorn app.server:app`.
app = build_app()


def main() -> None:
    """Runs the server with uvicorn (container entrypoint)."""
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
