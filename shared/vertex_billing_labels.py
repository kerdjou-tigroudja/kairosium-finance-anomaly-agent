"""Labels Vertex AI (facturation) sur chaque appel generateContent — couche 1 cost tracking."""

from __future__ import annotations

import logging
import os
import uuid

from google.adk.agents.context import Context
from google.adk.models.llm_request import LlmRequest

logger = logging.getLogger(__name__)

_STATE_PIPELINE_RUN_ID = "pipeline_run_id"

# Libellés facturation alignés sur la spec (orchestrator, pas finance_anomaly_orchestrator).
_AGENT_LABEL_NAMES: dict[str, str] = {
    "finance_anomaly_orchestrator": "orchestrator",
    "ingestion_agent": "ingestion_agent",
    "scoring_agent": "scoring_agent",
}


def _billing_agent_label(adk_agent_name: str) -> str:
    return _AGENT_LABEL_NAMES.get(adk_agent_name, adk_agent_name)


def _environment_label() -> str:
    raw = os.environ.get("PIPELINE_ENVIRONMENT") or os.environ.get("KAIROSIUM_ENV") or "dev"
    v = raw.strip().lower()
    return v if v in ("dev", "prod") else "dev"


def attach_vertex_billing_labels(
    callback_context: Context,
    llm_request: LlmRequest,
) -> None:
    """Renseigne ``GenerateContentConfig.labels`` pour Vertex AI (ignoré côté Google AI Studio).

    ADK supprime les labels si le backend n'est pas Vertex
    (voir ``Gemini._preprocess_request`` dans google/adk).
    """
    agent_label = _billing_agent_label(callback_context.agent_name)

    state = callback_context.state
    if _STATE_PIPELINE_RUN_ID not in state or not state.get(_STATE_PIPELINE_RUN_ID):
        state[_STATE_PIPELINE_RUN_ID] = str(uuid.uuid4())
    run_id = str(state[_STATE_PIPELINE_RUN_ID])

    env = _environment_label()
    new_labels = {
        "agent_name": agent_label,
        "pipeline_run_id": run_id,
        "environment": env,
    }
    existing = dict(llm_request.config.labels or {})
    existing.update(new_labels)
    llm_request.config.labels = existing
    logger.debug("Vertex billing labels: %s", new_labels)


def vertex_billing_before_model(
    callback_context: Context,
    llm_request: LlmRequest,
):
    """Callback ``before_model`` : injecte les labels sans court-circuiter le LLM."""
    attach_vertex_billing_labels(callback_context, llm_request)
    return None
