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

"""ADC-based auth helpers: an httpx client for auth-gated A2A sub-agents, and
request headers for the Developer Knowledge MCP.

`google.auth.default()` resolves to your user credentials locally (via
`gcloud auth application-default login`) and to the runtime service account when
deployed on Agent Runtime, so the same helpers work in both environments without
code changes.
"""

import google.auth
import httpx
from google.auth.transport.requests import Request


class GoogleADCAuth(httpx.Auth):
    """httpx auth that attaches an ADC OAuth2 access token.

    Token refresh is delegated to google-auth's `before_request` (refreshes when
    expired), so there is no manual expiry handling.
    """

    def __init__(
        self, scopes=("https://www.googleapis.com/auth/cloud-platform",)
    ) -> None:
        self._creds, _ = google.auth.default(scopes=list(scopes))
        self._req = Request()

    def _apply(self, request: httpx.Request) -> None:
        self._creds.before_request(
            self._req, request.method, str(request.url), request.headers
        )

    def sync_auth_flow(self, request):
        self._apply(request)
        yield request

    async def async_auth_flow(self, request):
        self._apply(request)
        yield request


def google_authed_client(timeout: float = 600.0) -> httpx.AsyncClient:
    """Returns an httpx client that authenticates as the ambient ADC identity."""
    return httpx.AsyncClient(auth=GoogleADCAuth(), timeout=httpx.Timeout(timeout))


def developer_knowledge_headers(project_id: str) -> dict[str, str]:
    """Builds auth headers for the Developer Knowledge MCP from ADC.

    The MCP is a Google API, so it accepts a standard OAuth bearer token and a
    quota-project header. Credentials come from Application Default Credentials
    (your ADC locally, the runtime service account when deployed).

    Stays offline-safe: if ADC or the network is unavailable (for example during
    offline unit tests), the bearer token is omitted and the constant headers are
    still returned, so building the toolset never fails at import time. The token
    is resolved for real when credentials are present at runtime.

    Args:
        project_id: The Google Cloud project id for the quota-project header.

    Returns:
        The HTTP headers to attach to the streamable-HTTP MCP connection.
    """
    headers = {
        "X-Goog-User-Project": project_id,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        headers["Authorization"] = f"Bearer {credentials.token}"
    except Exception:  # no ADC / no network (e.g. offline tests) — skip token.
        pass
    return headers
