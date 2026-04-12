#!/usr/bin/env python3
"""Crée les politiques d'alerte décrites dans infra/monitoring_alert.yaml."""

from __future__ import annotations

import argparse
import os
import sys

import yaml
from google.cloud import monitoring_v3
from google.cloud.monitoring_v3.types import AlertPolicy
from google.protobuf.json_format import ParseDict


def main() -> int:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    import env_bootstrap

    env_bootstrap.load_dotenv_if_missing()

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "yaml_path",
        nargs="?",
        default=os.path.join(os.path.dirname(__file__), "..", "infra", "monitoring_alert.yaml"),
        help="Chemin vers monitoring_alert.yaml",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les politiques parsées sans appeler l'API",
    )
    args = p.parse_args()

    channel = (os.environ.get("MONITORING_SLACK_CHANNEL") or "").strip()
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or (
        env_bootstrap.project_id_from_notification_channel(channel)
        if channel
        else None
    )

    if not args.dry_run:
        if not channel:
            print(
                "Définissez MONITORING_SLACK_CHANNEL (nom de ressource complet du webhook Slack), "
                "ex. projects/YOUR_GCP_PROJECT_ID/notificationChannels/12345678901234567890",
                file=sys.stderr,
            )
            return 2
        if not env_bootstrap.notification_channel_looks_configured(channel):
            print(
                "MONITORING_SLACK_CHANNEL semble encore un placeholder "
                "(remplacez <ID_RÉEL> par l’ID affiché dans la console GCP après création du webhook).",
                file=sys.stderr,
            )
            return 2
        if not project_id:
            print(
                "Définissez GOOGLE_CLOUD_PROJECT ou utilisez un MONITORING_SLACK_CHANNEL du type "
                "projects/PROJECT_ID/notificationChannels/CHANNEL_ID.",
                file=sys.stderr,
            )
            return 2

    path = os.path.abspath(args.yaml_path)
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)

    policies = doc.get("alertPolicies") or []
    if not policies:
        print("alertPolicies vide", file=sys.stderr)
        return 2

    client = None if args.dry_run else monitoring_v3.AlertPolicyServiceClient()
    parent = f"projects/{project_id}" if project_id else ""

    for raw in policies:
        policy = AlertPolicy()
        ParseDict(raw, policy._pb, ignore_unknown_fields=True)
        if channel:
            policy.notification_channels = [channel]
        if args.dry_run:
            print(policy.display_name, "→", len(policy.conditions), "condition(s)")
            continue
        assert client is not None
        created = client.create_alert_policy(name=parent, alert_policy=policy)
        print("created", created.name, created.display_name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
