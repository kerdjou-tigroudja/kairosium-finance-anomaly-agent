"""Chargeur de configuration — Firestore d'abord, fallback config/agent_config.json."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from shared.models import AgentConfig

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "agent_config.json"


@lru_cache(maxsize=1)
def load_config() -> AgentConfig:
    """Charge la config depuis Firestore si disponible, sinon depuis agent_config.json.

    Firestore : collection `config`, document `agent_config`.
    Variables d'env requises pour Firestore : GOOGLE_CLOUD_PROJECT.
    """
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")

    if project_id:
        try:
            from google.cloud import firestore  # type: ignore

            db = firestore.Client(project=project_id)
            doc = db.collection("config").document("agent_config").get()
            if doc.exists:
                data = doc.to_dict()
                logger.info("Config chargée depuis Firestore (project=%s)", project_id)
                return AgentConfig(**data)
        except Exception as exc:
            logger.warning(
                "Firestore indisponible (%s), fallback sur agent_config.json", exc
            )

    with open(_CONFIG_PATH, encoding="utf-8") as f:
        data = json.load(f)
    logger.info("Config chargée depuis %s", _CONFIG_PATH)
    config = AgentConfig(**data)

    # Overrides depuis les variables d'environnement (priorité sur agent_config.json)
    if model_id_env := os.environ.get("MODEL_ID"):
        config = config.model_copy(update={"model_id": model_id_env})
        logger.info("model_id overridé depuis MODEL_ID env : %s", model_id_env)
    if dataset_id_env := os.environ.get("BQ_DATASET_ID"):
        config = config.model_copy(update={"dataset_id": dataset_id_env})

    return config


def reload_config() -> AgentConfig:
    """Force le rechargement de la config (invalide le cache)."""
    load_config.cache_clear()
    return load_config()
