#!/usr/bin/env python3
"""Supprime un Reasoning Engine (Agent Engine) par resource name complet."""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "name",
        nargs="?",
        default=os.environ.get("AGENT_ENGINE_RESOURCE_NAME"),
        help="projects/.../locations/.../reasoningEngines/ID (ou env AGENT_ENGINE_RESOURCE_NAME)",
    )
    p.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    p.add_argument("--location", default=os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1"))
    args = p.parse_args()
    if not args.name:
        print("resource name manquant", file=sys.stderr)
        return 2
    import vertexai

    vertexai.init(project=args.project, location=args.location)
    client = vertexai.Client(project=args.project, location=args.location)
    op = client.agent_engines.delete(name=args.name)
    print(op)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
