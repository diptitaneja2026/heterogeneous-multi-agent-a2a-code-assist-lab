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

"""A RemoteA2aAgent that sends only the distilled ``clean_query``.

The default ``RemoteA2aAgent`` builds its outgoing A2A message from the whole
session (``_construct_message_parts_from_session``): the user's original message
plus every upstream agent's output, wrapped as
``For context: [query_extractor] said: ...``. LLM-backed specialists tolerate
that extra context, but a deterministic keyword-search specialist (Stack
Exchange) searches the blob literally and finds nothing.

This subclass overrides the message construction to send a single text part
containing only ``state["clean_query"]`` (the focused query produced by the
``query_extractor`` node). It falls back to the default behavior when no
``clean_query`` is present, so nothing breaks if the extractor is skipped.
"""

from __future__ import annotations

from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.genai import types


class CleanQueryRemoteA2aAgent(RemoteA2aAgent):
    """RemoteA2aAgent whose outgoing message is only ``state["clean_query"]``."""

    def _construct_message_parts_from_session(self, ctx: InvocationContext):
        clean_query = ctx.session.state.get("clean_query")
        if not clean_query:
            # No distilled query yet: preserve the default session-based behavior.
            return super()._construct_message_parts_from_session(ctx)
        converted = self._genai_part_converter(types.Part(text=clean_query))
        if not isinstance(converted, list):
            converted = [converted] if converted else []
        return converted, None
