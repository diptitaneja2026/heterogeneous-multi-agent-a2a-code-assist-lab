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

"""Workflow callbacks for the Code Assist root."""

from collections.abc import Callable

from google.adk.agents.callback_context import CallbackContext


def capture_response_to_state(state_key: str) -> Callable:
    """Builds an ``after_agent_callback`` that saves the agent's final text
    reply into ``state[state_key]``.

    A ``RemoteA2aAgent`` is a non-LlmAgent: it has no ``output_key``, and the
    workflow ``JoinNode`` does not capture its output. Persisting the reply to
    shared state (a tracked state delta) lets the synthesizer read it via an
    ``{state_key?}`` instruction template.

    Args:
        state_key: The session-state key to write the agent's reply into.

    Returns:
        An async ``after_agent_callback(callback_context)`` function.
    """

    async def _after_agent_callback(callback_context: CallbackContext):
        name = callback_context.agent_name
        for event in reversed(callback_context.session.events):
            if event.author == name and event.content and event.content.parts:
                texts = [p.text for p in event.content.parts if p.text]
                if texts:
                    callback_context.state[state_key] = "\n".join(texts)
                    break
        return None

    return _after_agent_callback
