"""Chargement optionnel de .env et helpers pour les scripts CLI (sans dépendance python-dotenv)."""

from __future__ import annotations

import json
import os
import re


def repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_dotenv_if_missing(path: str | None = None) -> None:
    """Charge KEY=VALUE depuis .env pour les clés absentes de os.environ."""
    env_path = path or os.path.join(repo_root(), ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value


def project_id_from_notification_channel(channel: str) -> str | None:
    """Extrait le project id ou number depuis projects/.../notificationChannels/..."""
    m = re.match(r"^projects/([^/]+)/notificationChannels/[^/]+$", channel.strip())
    return m.group(1) if m else None


def notification_channel_looks_configured(channel: str) -> bool:
    if not channel or not channel.strip():
        return False
    lowered = channel.lower()
    if "<" in channel or ">" in channel:
        return False
    placeholders = (
        "id_réel",
        "id_reel",
        "channel_id",
        "votre_projet",
        "xxx/",
        "yyy",
        "zzz",
    )
    return not any(p in lowered for p in placeholders)


def agent_engine_resource_from_deployment_metadata() -> str | None:
    meta = os.path.join(repo_root(), "deployment_metadata.json")
    if not os.path.isfile(meta):
        return None
    try:
        with open(meta, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("remote_agent_engine_id") or None
    except (json.JSONDecodeError, OSError):
        return None
