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

"""Guard tests for CleanQueryRemoteA2aAgent's message override.

These catch a future ADK change to the protected
``_construct_message_parts_from_session`` hook (rename or shape change) and
confirm the fallback path still delegates to the base class.
"""

from types import SimpleNamespace

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

from app.app_utils.clean_query_a2a import CleanQueryRemoteA2aAgent


def _agent() -> CleanQueryRemoteA2aAgent:
    return CleanQueryRemoteA2aAgent(
        name="stackexchange_agent", agent_card="https://example.test/card.json"
    )


def test_sends_only_clean_query():
    agent = _agent()
    ctx = SimpleNamespace(session=SimpleNamespace(state={"clean_query": "my query"}))

    parts, context_id = agent._construct_message_parts_from_session(ctx)

    assert context_id is None
    assert len(parts) == 1
    assert any(getattr(p.root, "text", None) == "my query" for p in parts)


def test_falls_back_when_no_clean_query(monkeypatch):
    agent = _agent()
    sentinel = (["FALLBACK"], "ctx-id")
    monkeypatch.setattr(
        RemoteA2aAgent,
        "_construct_message_parts_from_session",
        lambda self, ctx: sentinel,
    )
    ctx = SimpleNamespace(session=SimpleNamespace(state={}))

    assert agent._construct_message_parts_from_session(ctx) == sentinel
