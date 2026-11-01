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

"""A2A bridge for the LangGraph Stack Exchange graph.

Adapts the compiled LangGraph ``graph`` (see ``app/agent.py``) to the A2A
protocol using the official ``a2a-sdk`` 1.x (unified ``Message``/``Part`` API).
No LangGraph Platform server, no LLM, no datastore.

The server (``app/server.py``) advertises both a ``1.0`` and a ``0.3`` interface
and enables ``v0_3`` compatibility, so 0.3.x clients (e.g. the root Code Assist
agent's ADK ``RemoteA2aAgent``) can consume this 1.x server unchanged.
"""

from __future__ import annotations

import asyncio
import logging

from a2a.helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils.errors import (
    InternalError,
    InvalidParamsError,
    UnsupportedOperationError,
)
from langchain_core.messages import HumanMessage

from app.agent import graph

logger = logging.getLogger(__name__)


class StackExchangeExecutor(AgentExecutor):
    """Bridges incoming A2A requests to the LangGraph search graph."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Runs the graph on the user's query and returns the answer.

        Args:
            context: The A2A request context (carries the user message).
            event_queue: The queue used to publish the response back to the client.
        """
        query = context.get_user_input()
        if not query:
            raise InvalidParamsError(message="User query cannot be empty.")

        try:
            # graph.invoke is synchronous and does blocking network I/O
            # (StackAPI), so run it off the event loop.
            final_state = await asyncio.to_thread(
                graph.invoke, {"messages": [HumanMessage(content=query)]}
            )
            content = final_state["messages"][-1].content
            # new_text_message defaults to role=ROLE_AGENT.
            await event_queue.enqueue_event(new_text_message(content))
        except InvalidParamsError:
            raise
        except Exception as e:
            logger.exception("Stack Exchange agent execution failed: %s", e)
            raise InternalError() from e

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancellation is unsupported: the search completes in a single step."""
        raise UnsupportedOperationError()
