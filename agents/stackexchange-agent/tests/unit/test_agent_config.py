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

"""Offline tests for the LangGraph Stack Exchange graph."""

from types import SimpleNamespace
from unittest import mock

from app import agent as agent_module
from app.agent import graph, search


def test_graph_compiles_with_search_node() -> None:
    """The exported graph is a compiled LangGraph with the search node."""
    assert type(graph).__name__ == "CompiledStateGraph"
    assert "search" in graph.get_graph().nodes


def test_search_errors_without_query() -> None:
    """With no messages the node returns a clear error, not a crash."""
    result = search({"messages": []})
    assert "no query" in result["messages"][0].content.lower()


def test_search_invokes_stackexchange_tool() -> None:
    """The node runs the Stack Exchange tool on the latest message content."""
    fake_tool = mock.Mock()
    fake_tool.invoke.return_value = "ANSWER"
    with mock.patch.object(agent_module, "_stackexchange_tool", fake_tool):
        result = search({"messages": [SimpleNamespace(content="fix 422 in FastAPI")]})
    fake_tool.invoke.assert_called_once_with("fix 422 in FastAPI")
    assert result["messages"][0].content == "ANSWER"
