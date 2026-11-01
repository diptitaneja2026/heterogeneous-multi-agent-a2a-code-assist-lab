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

"""BigQuery bug-search sub-agent served over A2A on GKE."""

import json
import os

from dotenv import load_dotenv
from google import genai
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.cloud import bigquery
from google.genai import types

load_dotenv()

MODEL = os.environ.get("MODEL", "gemini-3.5-flash")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT")
EMBEDDING_LOCATION = os.environ.get("BQ_LOCATION", "us-central1")
EMBEDDING_MODEL = "text-embedding-004"
BUG_TABLE = "code_assist_bugs.known_bugs"


def find_similar_bugs(query: str) -> str:
    """Finds the top 3 semantically similar known bugs in BigQuery.

    Embeds the error description using Vertex AI `text-embedding-004` (768-dim)
    in `us-central1` and runs a BigQuery `VECTOR_SEARCH` (`COSINE` distance,
    top 3) against `code_assist_bugs.known_bugs` on `description_embedding`.

    Args:
        query: The error description or stack trace query to search for.

    Returns:
        A JSON-formatted string containing each match's `bug_id`, `title`,
        `description`, `resolution`, and cosine `distance` (ordered ascending).
    """
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or PROJECT_ID
    genai_client = genai.Client(
        vertexai=True,
        project=project,
        location=EMBEDDING_LOCATION,
    )
    embed_response = genai_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=query,
    )
    query_embedding = list(embed_response.embeddings[0].values)

    bq_client = bigquery.Client(project=project)
    sql = f"""
        SELECT
            base.bug_id AS bug_id,
            base.title AS title,
            base.description AS description,
            base.resolution AS resolution,
            distance
        FROM
            VECTOR_SEARCH(
                TABLE `{BUG_TABLE}`,
                'description_embedding',
                (SELECT @query_embedding AS embedding),
                top_k => 3,
                distance_type => 'COSINE'
            )
        ORDER BY distance ASC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter(
                "query_embedding", "FLOAT64", query_embedding
            )
        ]
    )
    rows = bq_client.query(sql, job_config=job_config).result()
    matches = [
        {
            "bug_id": row["bug_id"],
            "title": row["title"],
            "description": row["description"],
            "resolution": row["resolution"],
            "distance": float(row["distance"]),
        }
        for row in rows
    ]
    return json.dumps(matches, indent=2)


root_agent = Agent(
    name="bq_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    description=(
        "Specialized assistant that searches the internal BigQuery bug database "
        "(`code_assist_bugs.known_bugs`) by semantic vector similarity."
    ),
    instruction=(
        "You are the BigQuery Bug Database Specialist Agent. "
        "For every user request, you MUST call `find_similar_bugs` with the "
        "error query or description. Never answer from your own knowledge alone. "
        "Summarize the matching bugs, explicitly cite each matching `bug_id` and "
        "`title`, and clearly state its `resolution` and cosine `distance`."
    ),
    tools=[find_similar_bugs],
)

app = App(
    root_agent=root_agent,
    name="app",
)
