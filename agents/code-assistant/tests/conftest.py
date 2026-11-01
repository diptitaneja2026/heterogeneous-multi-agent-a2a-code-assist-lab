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

"""Test bootstrap: provide required env before `app.agent` is imported.

`app.agent` reads required config via `os.environ[...]` at import time
(fail-fast). This runs first (conftest is imported before test modules), using
`setdefault` so a real `.env` / shell value still wins when present.
"""

import os

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
os.environ.setdefault("MODEL", "gemini-3.5-flash")
os.environ.setdefault("DATASTORE_ID", "test-datastore")
os.environ.setdefault("BIGQUERY_DATASET", "bugs")
os.environ.setdefault("BIGQUERY_TABLE", "known_bugs")
os.environ.setdefault("GITHUB_AGENT_URL", "https://github-agent.test")
os.environ.setdefault("STACKEXCHANGE_AGENT_URL", "https://stackexchange-agent.test")
os.environ.setdefault("SALESFORCE_AGENT_URL", "https://salesforce-agent.test")
os.environ.setdefault("BQ_AGENT_URL", "https://bq-agent.test")
os.environ.setdefault(
    "DEVELOPER_KNOWLEDGE_MCP_URL", "https://developerknowledge.googleapis.com/mcp"
)
os.environ.setdefault("SKILL_REGISTRY_LOCATION", "us-central1")
