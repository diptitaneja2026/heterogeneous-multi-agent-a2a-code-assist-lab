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

"""Offline wiring tests for the root Code Assist Workflow graph."""

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

from app.agent import (
    DATASTORE_ID,
    DATASTORE_PATH,
    LOCATION,
    MODEL,
    app,
    bug_db_agent,
    github_agent,
    manual_search_agent,
    query_extractor,
    root_agent,
    stackexchange_agent,
    synthesizer,
)


def test_model_is_parameterized_from_env() -> None:
    """The model name comes from the MODEL env var (conftest sets it)."""
    assert MODEL == "gemini-3.5-flash"


def test_datastore_path_built_from_short_id() -> None:
    """The full data store path is constructed from the short DATASTORE_ID."""
    assert DATASTORE_ID == "test-datastore"
    assert DATASTORE_PATH.startswith("projects/")
    assert DATASTORE_PATH.endswith(
        f"/locations/{LOCATION}/collections/default_collection"
        f"/dataStores/{DATASTORE_ID}"
    )


def test_root_is_workflow_graph() -> None:
    """The root is an ADK 2.0 graph Workflow."""
    assert type(root_agent).__name__ == "Workflow"
    assert root_agent.name == "code_assist_agent"
    assert app.name == "app"


def test_query_extractor_cleans_query_and_loads_artifacts() -> None:
    """The intake node reads any upload and emits a clean query to state."""
    assert query_extractor.name == "query_extractor"
    assert query_extractor.output_key == "clean_query"
    assert [type(t).__name__ for t in query_extractor.tools] == ["LoadArtifactsTool"]


def test_remote_specialists_are_remote_a2a_agents() -> None:
    """The GitHub / Stack Exchange / Bug DB specialists are RemoteA2aAgents.

    Bug DB was externalized to its own ADK agent on GKE, so like the other remote
    specialists it's a RemoteA2aAgent whose reply is captured to state via an
    after_agent_callback (no output_key). Stack Exchange uses a RemoteA2aAgent
    subclass (CleanQueryRemoteA2aAgent), so check by instance, not exact type.
    """
    for remote in (github_agent, stackexchange_agent, bug_db_agent):
        assert isinstance(remote, RemoteA2aAgent)
    assert github_agent.name == "github_agent"
    assert stackexchange_agent.name == "stackexchange_agent"
    assert bug_db_agent.name == "bug_db_agent"


def test_local_branch_uses_ootb_tool_with_output_key() -> None:
    """The manual-search branch runs in-process with Vertex AI Search plus the
    Developer Knowledge skill/MCP tools, and writes to output_key."""
    assert [type(t).__name__ for t in manual_search_agent.tools] == [
        "VertexAiSearchTool",
        "SkillToolset",
        "McpToolset",
    ]
    assert manual_search_agent.output_key == "manual_findings"


def test_synthesizer_has_no_tools() -> None:
    """The synthesizer just blends findings into a cited answer (no tools)."""
    assert list(synthesizer.tools) == []
