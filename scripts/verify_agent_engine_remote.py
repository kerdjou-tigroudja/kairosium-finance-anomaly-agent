#!/usr/bin/env python3
"""Teste un Agent Engine déployé (async_stream_query) et optionnellement prépare un gs:// pour le CSV."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys


async def _stream(agent, message: str, user_id: str) -> None:
    n = 0
    async for ev in agent.async_stream_query(message=message, user_id=user_id):
        n += 1
        print(json.dumps(ev, default=str)[:2000])
    print(f"--- fin stream ({n} événements) ---", file=sys.stderr)


def _ensure_gcs_csv(project: str, bucket: str, local_csv: str) -> str:
    from google.cloud import storage

    client = storage.Client(project=project)
    b = client.bucket(bucket)
    if not b.exists():
        b.create(location="europe-west1")
    blob = b.blob("demo/golden_set.csv")
    blob.upload_from_filename(local_csv)
    return f"gs://{bucket}/demo/golden_set.csv"


def main() -> int:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import env_bootstrap

    env_bootstrap.load_dotenv_if_missing()

    p = argparse.ArgumentParser()
    p.add_argument(
        "--resource-name",
        default=os.environ.get("AGENT_ENGINE_RESOURCE_NAME"),
        help="projects/.../locations/.../reasoningEngines/ID",
    )
    p.add_argument("--project", default=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    p.add_argument("--location", default=os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1"))
    p.add_argument("--message", default="Dis bonjour en une phrase.")
    p.add_argument("--user-id", default="verify-cli")
    p.add_argument(
        "--prepare-gcs",
        action="store_true",
        help="Crée le bucket si besoin et envoie data/golden_set.csv puis utilise le pipeline complet",
    )
    p.add_argument(
        "--bucket",
        default="",
        help="Bucket GCS (nom seul) pour --prepare-gcs ; défaut: {project}-kairosium-agent-csv",
    )
    args = p.parse_args()

    resource_name = args.resource_name or env_bootstrap.agent_engine_resource_from_deployment_metadata()
    project = args.project or os.environ.get("GOOGLE_CLOUD_PROJECT")

    if not resource_name or not project:
        print(
            "Renseignez --resource-name et --project, ou définissez dans .env : "
            "GOOGLE_CLOUD_PROJECT, AGENT_ENGINE_RESOURCE_NAME "
            "(sinon remote_agent_engine_id dans deployment_metadata.json est utilisé pour l’engine).",
            file=sys.stderr,
        )
        if not resource_name:
            print("  → AGENT_ENGINE_RESOURCE_NAME / --resource-name manquant.", file=sys.stderr)
        if not project:
            print("  → GOOGLE_CLOUD_PROJECT / --project manquant.", file=sys.stderr)
        return 2

    import vertexai

    vertexai.init(project=project, location=args.location)
    client = vertexai.Client(project=project, location=args.location)
    agent = client.agent_engines.get(name=resource_name)

    message = args.message
    if args.prepare_gcs:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        csv_path = os.path.join(root, "data", "golden_set.csv")
        if not os.path.isfile(csv_path):
            print(f"CSV introuvable: {csv_path}", file=sys.stderr)
            return 2
        bucket = args.bucket or f"{project}-kairosium-agent-csv".replace("_", "-")[:63]
        gcs_uri = _ensure_gcs_csv(project, bucket, csv_path)
        print(f"CSV sur {gcs_uri}", file=sys.stderr)
        message = (
            f"Analyse les transactions du fichier {gcs_uri} "
            "et génère le rapport d'audit."
        )

    asyncio.run(_stream(agent, message=message, user_id=args.user_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
