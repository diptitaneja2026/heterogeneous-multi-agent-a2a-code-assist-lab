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

"""Root "Code Assist" orchestrator built as an ADK 2.0 graph `Workflow`.

The graph distills the user's error into a clean query, fans out to five
specialists in parallel, joins their results, then synthesizes one cited answer::

    START -> query_extractor -> (github_agent | stackexchange_agent |
                                 salesforce_agent | bug_db_agent |
                                 manual_search_agent) -> merge -> synthesizer

`query_extractor` reads any uploaded file and emits a focused search query.
`github_agent`, `stackexchange_agent`, `salesforce_agent`, and `bug_db_agent`
are remote specialists reached over A2A via `RemoteA2aAgent` (github/salesforce/
bug_db are ADK agents; stackexchange is a LangGraph app); `manual_search_agent`
searches the team's engineering handbook (Vertex AI Search) and Google's official
developer documentation (the Developer Knowledge MCP, guided by the
`using-developer-knowledge-mcp` skill discovered on demand from the GCP Skill
Registry). `merge` (a `JoinNode`) waits for all five branches, and `synthesizer`
blends them into one source-attributed resolution.
"""

import os

import dotenv
from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.apps import App
from google.adk.integrations.skill_registry.gcp_skill_registry import (
    GCPSkillRegistry,
)
from google.adk.models import Gemini
from google.adk.tools import VertexAiSearchTool, load_artifacts
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.workflow import JoinNode, Workflow
from google.genai import types

from app.app_utils.a2a import user_id_meta_provider
from app.app_utils.clean_query_a2a import CleanQueryRemoteA2aAgent
from app.auth import developer_knowledge_headers, google_authed_client
from app.callbacks import capture_response_to_state

dotenv.load_dotenv()


PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]
LOCATION = os.environ["GOOGLE_CLOUD_LOCATION"]

MODEL = os.environ["MODEL"]
DATASTORE_ID = os.environ["DATASTORE_ID"]
GITHUB_AGENT_URL = os.environ["GITHUB_AGENT_URL"]
STACKEXCHANGE_AGENT_URL = os.environ["STACKEXCHANGE_AGENT_URL"]
SALESFORCE_AGENT_URL = os.environ["SALESFORCE_AGENT_URL"]
BQ_AGENT_URL = os.environ["BQ_AGENT_URL"]
DEVELOPER_KNOWLEDGE_MCP_URL = os.environ["DEVELOPER_KNOWLEDGE_MCP_URL"]
SKILL_REGISTRY_LOCATION = os.environ["SKILL_REGISTRY_LOCATION"]

DATASTORE_PATH = (
    f"projects/{PROJECT_ID}/locations/{LOCATION}"
    f"/collections/default_collection/dataStores/{DATASTORE_ID}"
)


def _model() -> Gemini:
    """Builds the shared Gemini model configuration.

    Returns:
        A `Gemini` model configured from the `MODEL` env var, with retries.
    """
    return Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    )


vais_tool = VertexAiSearchTool(
    data_store_id=DATASTORE_PATH,
    bypass_multi_tools_limit=True,
)

developer_knowledge_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=DEVELOPER_KNOWLEDGE_MCP_URL,
        headers=developer_knowledge_headers(PROJECT_ID),
    ),
)

skill_registry = GCPSkillRegistry(
    project_id=PROJECT_ID,
    location=SKILL_REGISTRY_LOCATION,
)

developer_knowledge_skill = SkillToolset(registry=skill_registry)


# --- Remote specialists over A2A ----------------------------------------------
github_agent = RemoteA2aAgent(
    name="github_agent",
    description="Searches GitHub repositories, issues, and pull requests.",
    agent_card=GITHUB_AGENT_URL,
    httpx_client=google_authed_client(),
    use_legacy=False,
    after_agent_callback=capture_response_to_state("github_findings"),
)

stackexchange_agent = CleanQueryRemoteA2aAgent(
    name="stackexchange_agent",
    description="Searches Stack Exchange for programming questions and errors.",
    agent_card=STACKEXCHANGE_AGENT_URL,
    after_agent_callback=capture_response_to_state("stackexchange_findings"),
)

salesforce_agent = RemoteA2aAgent(
    name="salesforce_agent",
    description=(
        "Searches other teams' architecture decision records (ADRs) and "
        "org-wide engineering policies in the Salesforce document library."
    ),
    agent_card=SALESFORCE_AGENT_URL,
    use_legacy=False,
    a2a_request_meta_provider=user_id_meta_provider,
    after_agent_callback=capture_response_to_state("salesforce_findings"),
)

bug_db_agent = RemoteA2aAgent(
    name="bug_db_agent",
    description="Searches the internal bug database in BigQuery.",
    agent_card=BQ_AGENT_URL,
    use_legacy=False,
    after_agent_callback=capture_response_to_state("bug_findings"),
)


# --- Graph nodes --------------------------------------------------------------
query_extractor = Agent(
    name="query_extractor",
    model=_model(),
    instruction=(
        "You are a code-incident intake step. If a file or image was uploaded, "
        "call load_artifacts to read it. From the user's message and any file, "
        "identify the main error/exception, key stack-trace tokens, and the "
        "language/framework, and distill them into a single short 'clean_query' "
        "of key terms only (no prose, no explanation, no fixes)."
    ),
    tools=[load_artifacts],
    output_key="clean_query",
)

manual_search_agent = Agent(
    name="manual_search_agent",
    model=_model(),
    description=(
        "Searches this team's engineering handbook (how-to guides, runbooks, "
        "coding standards) via Vertex AI Search, plus Google's official "
        "developer documentation via the Developer Knowledge tools."
    ),
    instruction=(
        "Find guidance for: {clean_query?}\n"
        "You have two documentation sources:\n"
        "1. The team's engineering handbook — how-to guides, runbooks, and "
        "coding standards (how we are supposed to do things here) — via Vertex "
        "AI Search.\n"
        "2. Google's official developer documentation (Cloud, Firebase, Android, "
        "Maps, Flutter, Go, ADK, and more) via the Developer Knowledge tools. "
        "When the error involves a Google product, call search_skills and "
        "load_skill to load the 'using-developer-knowledge-mcp' skill first, "
        "then follow it for how to drive those tools and when a topic is "
        "outside Google's docs.\n"
        "Prefer the internal handbook; add official Google docs when the error "
        "involves a Google product. Summarize the matching guidance and cite "
        "each source. If neither covers it, say so."
    ),
    tools=[vais_tool, developer_knowledge_skill, developer_knowledge_mcp],
    output_key="manual_findings",
)


merge = JoinNode(name="merge")

synthesizer = Agent(
    name="code_assist_synthesizer",
    model=_model(),
    description="Blends all findings into one source-attributed answer.",
    instruction=(
        "You are the Code Assist synthesis agent. Produce a single resolution "
        "for the user's reported error using these findings:\n"
        "- Bug database (past incidents and their fixes): {bug_findings?}\n"
        "- Engineering handbook & official Google docs: {manual_findings?}\n"
        "- Salesforce (other teams' ADRs and org-wide policies): {salesforce_findings?}\n"
        "- GitHub: {github_findings?}\n"
        "- Stack Exchange: {stackexchange_findings?}\n\n"
        "Rules:\n"
        "1. Prefer internal sources (bug database, engineering handbook, Salesforce "
        "ADRs/policies) and official Google docs over community sources (GitHub, "
        "Stack Exchange) when they conflict.\n"
        "2. Explicitly cite the source of each fact (Bug Database, Engineering "
        "Handbook, Official Google Docs, Salesforce, GitHub, or Stack Exchange).\n"
        "Give the best helpful answer with no follow-up questions."
    ),
)


# --- Workflow graph -----------------------------------------------------------
root_agent = Workflow(
    name="code_assist_agent",
    description=(
        "Researches an error across GitHub, Stack Exchange, Salesforce, and a bug "
        "database (all over A2A) plus code manuals in parallel, then blends a "
        "cited answer."
    ),
    edges=[
        ("START", query_extractor),
        (
            query_extractor,
            (
                github_agent,
                stackexchange_agent,
                salesforce_agent,
                bug_db_agent,
                manual_search_agent,
            ),
        ),
        (
            (
                github_agent,
                stackexchange_agent,
                salesforce_agent,
                bug_db_agent,
                manual_search_agent,
            ),
            merge,
        ),
        (merge, synthesizer),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
