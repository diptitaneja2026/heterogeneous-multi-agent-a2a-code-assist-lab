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

"""Publish an Agent Skill to the GCP (Vertex AI) Skill Registry.

`manual_search_agent` loads the ``using-developer-knowledge-mcp`` skill on demand
from the Skill Registry (see ``app/agent.py``). This script publishes the skill
source under ``app/skills/<skill-id>/`` to the registry so the agent can find it.

Create-only: if the skill already exists it is left untouched (updating an
existing skill does not refresh the registry's semantic-search index, which would
make the skill undiscoverable). Run it once per project/region. To change a
published skill, delete it and recreate it.

Usage:
    uv run python scripts/publish_skill.py \
        --project my-gcp-project \
        --location us-central1 \
        --skill-id using-developer-knowledge-mcp

Config resolution (flags override environment):
    --project   / GOOGLE_CLOUD_PROJECT
    --location  / SKILL_REGISTRY_LOCATION (default: us-central1)
    --skill-id  (default: using-developer-knowledge-mcp)
    --skill-dir (default: app/skills/<skill-id> relative to the repo)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

_DEFAULT_SKILL_ID = "using-developer-knowledge-mcp"
_DEFAULT_LOCATION = "us-central1"


def _default_skill_dir(skill_id: str) -> pathlib.Path:
    """Returns the in-repo source directory for the given skill id.

    Args:
        skill_id: The skill identifier (also its directory name).

    Returns:
        The path to ``app/skills/<skill_id>`` relative to this script.
    """
    return pathlib.Path(__file__).resolve().parent.parent / "app" / "skills" / skill_id


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parses command-line arguments.

    Args:
        argv: The argument vector (excluding the program name).

    Returns:
        The parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        help="Google Cloud project id (default: $GOOGLE_CLOUD_PROJECT).",
    )
    parser.add_argument(
        "--location",
        default=os.environ.get("SKILL_REGISTRY_LOCATION", _DEFAULT_LOCATION),
        help="Skill Registry region (default: $SKILL_REGISTRY_LOCATION or "
        f"{_DEFAULT_LOCATION}).",
    )
    parser.add_argument(
        "--skill-id",
        default=_DEFAULT_SKILL_ID,
        help=f"Skill id to publish (default: {_DEFAULT_SKILL_ID}).",
    )
    parser.add_argument(
        "--skill-dir",
        default=None,
        help="Skill source directory (default: app/skills/<skill-id>).",
    )
    parser.add_argument(
        "--description",
        default=(
            "Search Google's official developer documentation via the Developer "
            "Knowledge MCP; grounded, and admits when a topic is out of corpus."
        ),
        help="Skill description shown in the registry catalog.",
    )
    return parser.parse_args(argv)


def publish_skill(
    *,
    project: str,
    location: str,
    skill_id: str,
    skill_dir: pathlib.Path,
    description: str,
) -> str:
    """Creates a skill in the GCP Skill Registry if it does not already exist.

    Create-only by design: an existing skill is left untouched, because updating
    a skill does not refresh the registry's semantic-search index (the skill
    would stop being discoverable via search_skills).

    Args:
        project: Google Cloud project id.
        location: Skill Registry region.
        skill_id: The skill identifier.
        skill_dir: Local directory holding the skill's SKILL.md and resources.
        description: Human-readable description for the registry catalog.

    Returns:
        The full resource name of the published skill.
    """
    # Imported here so the module is importable (e.g. for --help) without the
    # Vertex SDK, and so import errors surface with actionable context.
    from vertexai import Client
    from vertexai._genai.types import CreateSkillConfig

    if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
        raise FileNotFoundError(
            f"Skill source not found: expected {skill_dir}/SKILL.md"
        )

    client = Client(project=project, location=location)
    full_name = f"projects/{project}/locations/{location}/skills/{skill_id}"

    try:
        client.skills.get(name=full_name)
        print(f"Skill already exists, leaving it unchanged: {full_name}")
        print(
            "To change it, delete the skill and re-run this script "
            "(a deleted skill id is reserved for 24h)."
        )
        return full_name
    except Exception:  # not found -> create it.
        pass

    print(f"Creating skill: {skill_id} in {project}/{location}")
    result = client.skills.create(
        display_name=skill_id,
        description=description,
        config=CreateSkillConfig(
            local_path=str(skill_dir),
            skill_id=skill_id,
            wait_for_completion=True,
        ),
    )
    return getattr(result, "name", None) or full_name


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code (0 on success, non-zero on error).
    """
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if not args.project:
        print(
            "error: --project or GOOGLE_CLOUD_PROJECT is required.",
            file=sys.stderr,
        )
        return 2

    skill_dir = (
        pathlib.Path(args.skill_dir).resolve()
        if args.skill_dir
        else _default_skill_dir(args.skill_id)
    )

    try:
        name = publish_skill(
            project=args.project,
            location=args.location,
            skill_id=args.skill_id,
            skill_dir=skill_dir,
            description=args.description,
        )
    except Exception as exc:  # surface a clean, actionable error.
        print(f"error: failed to publish skill: {exc}", file=sys.stderr)
        return 1

    print(f"Published skill: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
