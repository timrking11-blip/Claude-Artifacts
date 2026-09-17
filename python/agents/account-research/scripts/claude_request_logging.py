#!/usr/bin/env python3
"""Read or set Vertex request/response logging for the Claude publisher model.

Vertex can mirror prompts and completions into a BigQuery table. For Gemini
that is configured on the model object
(`GenerativeModel.set_request_response_logging_config`), but that class never
sees Claude traffic -- Claude on Vertex is served through
`rawPredict`/`streamRawPredict` under the `anthropic` publisher. For Anthropic
models the configuration is REST-only, via setPublisherModelConfig, and the
Terraform google provider does not support it yet
(hashicorp/terraform-provider-google#24092), which is why this is a script.

    python scripts/claude_request_logging.py --show
    python scripts/claude_request_logging.py --enable --dataset crm --table claude_logs
    python scripts/claude_request_logging.py --enable ... --dry-run
    python scripts/claude_request_logging.py --disable

Environment matches the agent: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION,
ACCOUNT_RESEARCH_CLAUDE_MODEL. Auth is Application Default Credentials.

The logged rows carry prompts and completions -- customer data. Point it at a
dataset whose access, region and retention you have chosen deliberately.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

PLACEHOLDERS = {"", "YOUR_PROJECT_ID", "YOUR_VALUE_HERE"}
SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def endpoint(location: str) -> str:
    """Global uses the bare host; every region is prefixed."""
    return (
        "https://aiplatform.googleapis.com"
        if location == "global"
        else f"https://{location}-aiplatform.googleapis.com"
    )


def model_path(project: str, location: str, model: str) -> str:
    return (
        f"projects/{project}/locations/{location}"
        f"/publishers/anthropic/models/{model}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    action = ap.add_mutually_exclusive_group(required=True)
    action.add_argument("--show", action="store_true", help="fetch the current config")
    action.add_argument("--enable", action="store_true", help="turn logging on")
    action.add_argument("--disable", action="store_true", help="turn logging off")
    ap.add_argument("--dataset", help="existing BigQuery dataset (required with --enable)")
    ap.add_argument("--table", default="claude_request_response",
                    help="table to write to; Vertex creates it (default: %(default)s)")
    ap.add_argument("--sampling-rate", type=float, default=1.0,
                    help="fraction of requests to log, in (0,1] (default: %(default)s)")
    ap.add_argument("--otel", action="store_true", help="also emit OpenTelemetry logs")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the request that would be sent, and exit")
    args = ap.parse_args()

    project = (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    if project.upper() in PLACEHOLDERS:
        what = "is not set" if not project else f"is still the placeholder {project!r}"
        print(f"GOOGLE_CLOUD_PROJECT {what}. Load .env first.", file=sys.stderr)
        return 2
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global").strip() or "global"
    model = os.getenv("ACCOUNT_RESEARCH_CLAUDE_MODEL", "claude-fable-5-1")

    if args.enable:
        if not args.dataset:
            print("--enable needs --dataset (an existing BigQuery dataset).", file=sys.stderr)
            return 2
        if not 0 < args.sampling_rate <= 1:
            print("--sampling-rate must be in (0, 1].", file=sys.stderr)
            return 2

    name = model_path(project, location, model)
    base = f"{endpoint(location)}/v1beta1/{name}"

    if args.show:
        url, payload, method = f"{base}:fetchPublisherModelConfig", None, "GET"
    else:
        logging_config = {"enabled": bool(args.enable)}
        if args.enable:
            logging_config.update({
                "samplingRate": args.sampling_rate,
                "bigqueryDestination": {
                    "outputUri": f"bq://{project}.{args.dataset}.{args.table}"
                },
                "enableOtelLogging": args.otel,
            })
        url = f"{base}:setPublisherModelConfig"
        payload = {"publisherModelConfig": {"loggingConfig": logging_config}}
        method = "POST"

    print(f"{method} {url}")
    if payload is not None:
        print(json.dumps(payload, indent=2))
    if args.dry_run:
        print("\n(dry run: nothing sent)")
        return 0

    try:
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError, RefreshError
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        print(f"google-auth is required: {exc}", file=sys.stderr)
        return 1

    try:
        credentials, _ = google.auth.default(scopes=[SCOPE])
        session = AuthorizedSession(credentials)
        resp = (session.get(url, timeout=60) if method == "GET"
                else session.post(url, json=payload, timeout=60))
    except DefaultCredentialsError:
        print("No Application Default Credentials.", file=sys.stderr)
        print("Run: gcloud auth application-default login", file=sys.stderr)
        return 1
    except RefreshError as exc:
        print(f"Credentials could not be refreshed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - network/transport
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    body = resp.text
    try:
        body = json.dumps(resp.json(), indent=2)
    except ValueError:
        pass

    if resp.status_code >= 400:
        print(f"HTTP {resp.status_code}\n{body}", file=sys.stderr)
        if resp.status_code == 403:
            print("\nThe caller needs roles/aiplatform.user (or admin) on the project, "
                  "and the BigQuery dataset must exist and be writable.", file=sys.stderr)
        elif resp.status_code == 404:
            print(f"\nIs {model!r} enabled in Model Garden for this project, "
                  "and served in this location?", file=sys.stderr)
        return 1

    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
