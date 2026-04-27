"""Chargeur de configuration — JSON uniquement (ADR-006)."""

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
    """Charge la config depuis config/agent_config.json.

    Overrides possibles via variables d'env MODEL_ID et BQ_DATASET_ID.
    """
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
