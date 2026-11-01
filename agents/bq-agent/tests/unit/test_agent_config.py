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

"""Offline unit tests for the BigQuery bug-search agent."""

import json
from types import SimpleNamespace
from unittest import mock

from app import agent as agent_module
from app.agent import app, find_similar_bugs, root_agent


def test_agent_identity() -> None:
    """The agent and app are named as expected."""
    assert root_agent.name == "bq_agent"
    assert app.name == "app"


def test_find_similar_bugs_tool_is_wired() -> None:
    """The root agent exposes the find_similar_bugs tool."""
    assert len(root_agent.tools) == 1
    assert root_agent.tools[0] is find_similar_bugs


def test_find_similar_bugs_embeds_and_queries_bigquery() -> None:
    """find_similar_bugs embeds the query with text-embedding-004 and runs VECTOR_SEARCH."""
    fake_genai_client = mock.MagicMock()
    fake_genai_client.models.embed_content.return_value = SimpleNamespace(
        embeddings=[SimpleNamespace(values=[0.1] * 768)]
    )

    fake_bq_client = mock.MagicMock()
    fake_row = {
        "bug_id": "BUG-1001",
        "title": "FastAPI service returns 500 on startup",
        "description": "Pydantic v2 migration error",
        "resolution": "Migrate models to Pydantic v2 ConfigDict",
        "distance": 0.07,
    }
    fake_bq_client.query.return_value.result.return_value = [fake_row]

    with (
        mock.patch.object(agent_module.genai, "Client", return_value=fake_genai_client),
        mock.patch.object(agent_module.bigquery, "Client", return_value=fake_bq_client),
    ):
        output = find_similar_bugs("FastAPI 500 PydanticUserError")

    fake_genai_client.models.embed_content.assert_called_once_with(
        model="text-embedding-004",
        contents="FastAPI 500 PydanticUserError",
    )
    fake_bq_client.query.assert_called_once()
    sql_arg = fake_bq_client.query.call_args.args[0]
    assert "VECTOR_SEARCH" in sql_arg
    assert "code_assist_bugs.known_bugs" in sql_arg
    assert "COSINE" in sql_arg

    parsed = json.loads(output)
    assert len(parsed) == 1
    assert parsed[0]["bug_id"] == "BUG-1001"
    assert parsed[0]["resolution"] == "Migrate models to Pydantic v2 ConfigDict"
    assert parsed[0]["distance"] == 0.07
