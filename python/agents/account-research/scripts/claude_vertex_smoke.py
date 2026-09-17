#!/usr/bin/env python3
"""Prove Claude on Vertex AI works for this project before running the agent.

    python scripts/claude_vertex_smoke.py

Uses the same environment the agent uses: GOOGLE_CLOUD_PROJECT,
GOOGLE_CLOUD_LOCATION (Claude accepts "global") and ACCOUNT_RESEARCH_CLAUDE_MODEL.
Auth is Application Default Credentials: `gcloud auth application-default login`.
"""

import os
import sys

from anthropic import (
    AnthropicVertex,
    APIConnectionError,
    APIStatusError,
    NotFoundError,
    PermissionDeniedError,
)

MODEL = os.getenv("ACCOUNT_RESEARCH_CLAUDE_MODEL", "claude-fable-5-1")

# The values .env-example ships. Copying it and loading it without editing
# leaves these in the environment, and sending one to Vertex returns an
# opaque 403/404 -- so treat them as "not configured", like an empty value.
PLACEHOLDERS = {"", "YOUR_PROJECT_ID", "YOUR_VALUE_HERE", "YOUR_BUCKET"}


def main() -> int:
    project = (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    if project.upper() in PLACEHOLDERS:
        what = "is not set" if not project else f"is still the placeholder {project!r}"
        print(f"GOOGLE_CLOUD_PROJECT {what}.", file=sys.stderr)
        print("Edit .env, set GOOGLE_CLOUD_PROJECT to your project ID (not the "
              "number), then: set -o allexport; . .env; set +o allexport", file=sys.stderr)
        return 2
    region = os.getenv("GOOGLE_CLOUD_LOCATION", "global")

    client = AnthropicVertex(project_id=project, region=region)
    print(f"project={project} region={region} model={MODEL}")

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello! In one sentence, what can you help me with?"}],
        )
    except NotFoundError as exc:
        # Most often: the model is not enabled in Model Garden for this project,
        # or Vertex does not serve this id in this region.
        print(f"NotFound: {exc.message}", file=sys.stderr)
        print(f"Enable {MODEL} in Vertex AI Model Garden for project {project}, "
              "or set ACCOUNT_RESEARCH_CLAUDE_MODEL=claude-opus-5 and retry.", file=sys.stderr)
        return 1
    except PermissionDeniedError as exc:
        print(f"PermissionDenied: {exc.message}", file=sys.stderr)
        print("Your ADC identity needs the Vertex AI User role on this project; "
              "also check that aiplatform.googleapis.com is enabled.", file=sys.stderr)
        return 1
    except APIStatusError as exc:
        print(f"HTTP {exc.status_code}: {exc.message}", file=sys.stderr)
        return 1
    except APIConnectionError as exc:
        print(f"Could not reach Vertex AI: {exc}", file=sys.stderr)
        return 1

    # Fable 5.1 can decline a request with HTTP 200 and stop_reason "refusal";
    # check it before reading content. Vertex has no server-side fallbacks.
    if message.stop_reason == "refusal":
        details = message.stop_details
        print(f"Refused ({details.category if details else 'no category'}): "
              f"{details.explanation if details else ''}", file=sys.stderr)
        return 1

    text = "".join(block.text for block in message.content if block.type == "text")
    print(text.strip())
    print(f"stop_reason={message.stop_reason} "
          f"input_tokens={message.usage.input_tokens} output_tokens={message.usage.output_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
