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

"""Stack Exchange agent (LangGraph, served natively over A2A).

Same functionality as the adk_lab agent: a single-node graph whose node runs the
LangChain StackExchangeTool on the latest user message and returns the result.
No LLM. The LangGraph Agent Server (langgraph-api) exposes this graph over A2A
at /a2a/{assistant_id} with an auto-generated agent card, so the root Code
Assist agent can consume it via A2A.

The state has a `messages` key (required for A2A "text" parts).
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_community.tools import StackExchangeTool
from langchain_community.utilities import StackExchangeAPIWrapper
from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

# Stack Exchange search tool (anonymous read access via StackAPI; no key).
_stackexchange_tool = StackExchangeTool(api_wrapper=StackExchangeAPIWrapper())


class State(TypedDict):
    """Graph state: the running message list (A2A text parts land here)."""

    messages: Annotated[list[AnyMessage], add_messages]


def search(state: State) -> dict[str, Any]:
    """Runs the Stack Exchange search on the latest user message.

    Args:
        state: The graph state carrying the message history.

    Returns:
        A state update whose assistant message holds the search results.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"messages": [AIMessage(content="Error: no query was provided.")]}
    last = messages[-1]
    query = last.content if hasattr(last, "content") else last.get("content", "")
    result = _stackexchange_tool.invoke(query)
    return {"messages": [AIMessage(content=result)]}

graph = (
    StateGraph(State)
    .add_node("search", search)
    .add_edge(START, "search")
    .add_edge("search", END)
    .compile()
)