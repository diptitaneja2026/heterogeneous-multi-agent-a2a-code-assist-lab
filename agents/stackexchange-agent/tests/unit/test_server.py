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

"""Tests for the A2A server: card contents and backward-compat, plus executor."""

from unittest import mock

import pytest
from a2a.server.request_handlers.response_helpers import agent_card_to_dict

from app import agent_executor as executor_module
from app.agent_executor import StackExchangeExecutor
from app.server import build_agent_card


def test_agent_card_advertises_skill_and_both_interfaces() -> None:
    """The card exposes the search skill and both 1.0 and 0.3 interfaces."""
    card = build_agent_card("https://se.example.com")
    assert card.name == "StackExchangeAgent"
    assert [s.id for s in card.skills] == ["search_stackexchange"]
    versions = sorted(i.protocol_version for i in card.supported_interfaces)
    assert versions == ["0.3", "1.0"]
    for iface in card.supported_interfaces:
        assert iface.url == "https://se.example.com/a2a/jsonrpc"


def test_agent_card_is_0_3_compatible() -> None:
    """Regression guard: the served card must carry the legacy top-level `url`.

    ADK's RemoteA2aAgent (a2a-sdk 0.3.x) requires a top-level `url`; a2a 1.x
    only emits it when a 0.3 interface is advertised. Without it the root
    cannot consume this agent.
    """
    card_dict = agent_card_to_dict(build_agent_card("https://se.example.com"))
    assert card_dict.get("url") == "https://se.example.com/a2a/jsonrpc"
    assert card_dict.get("preferredTransport") == "JSONRPC"


@pytest.mark.asyncio
async def test_executor_runs_graph_and_enqueues_result() -> None:
    """The executor runs the graph on the query and enqueues the answer."""
    fake_state = {"messages": [mock.Mock(content="ANSWER")]}
    context = mock.Mock()
    context.get_user_input.return_value = "how to fix 500 in FastAPI"
    event_queue = mock.Mock()
    event_queue.enqueue_event = mock.AsyncMock()

    with mock.patch.object(executor_module, "graph") as fake_graph:
        fake_graph.invoke.return_value = fake_state
        await StackExchangeExecutor().execute(context, event_queue)

    fake_graph.invoke.assert_called_once()
    event_queue.enqueue_event.assert_awaited_once()
    # The enqueued A2A message carries the graph's answer text.
    enqueued = event_queue.enqueue_event.await_args.args[0]
    assert "ANSWER" in str(enqueued)


@pytest.mark.asyncio
async def test_executor_rejects_empty_query() -> None:
    """An empty query raises a protocol error rather than running the graph."""
    from a2a.utils.errors import InvalidParamsError

    context = mock.Mock()
    context.get_user_input.return_value = ""
    event_queue = mock.Mock()
    event_queue.enqueue_event = mock.AsyncMock()

    with pytest.raises(InvalidParamsError):
        await StackExchangeExecutor().execute(context, event_queue)
    event_queue.enqueue_event.assert_not_called()
