"""App ADK avec BigQueryAgentAnalyticsPlugin — observabilité distribuée (DESIGN_SPEC §7.3)."""

from __future__ import annotations

import logging
import os

import vertexai
from google.adk.apps import App
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from config.loader import load_config
from orchestrator.agent import root_agent

# Initialisation Vertex AI via ADC (gcloud auth application-default login)
if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true":
    vertexai.init(
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1"),
    )

logger = logging.getLogger(__name__)

# Configure OpenTelemetry pour distributed tracing (peuple trace_id/span_id en BQ)
trace.set_tracer_provider(TracerProvider())


def create_app() -> App:
    """Crée l'App ADK avec BigQueryAgentAnalyticsPlugin si GOOGLE_CLOUD_PROJECT est défini."""
    config = load_config()
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    plugins = []

    if project_id:
        try:
            from google.adk.plugins.bigquery_agent_analytics_plugin import (  # type: ignore
                BigQueryAgentAnalyticsPlugin,
                BigQueryLoggerConfig,
            )

            dataset_id = os.environ.get("BQ_DATASET_ID", config.dataset_id)
            location = os.environ.get("GOOGLE_CLOUD_LOCATION", "europe-west1")

            bq_config = BigQueryLoggerConfig(
                enabled=True,
                batch_size=1,        # faible latence (pas de buffering)
                shutdown_timeout=10.0,
                auto_schema_upgrade=True,
                create_views=True,
            )

            bq_plugin = BigQueryAgentAnalyticsPlugin(
                project_id=project_id,
                dataset_id=dataset_id,
                table_id="agent_events",
                config=bq_config,
                location=location,
            )
            plugins.append(bq_plugin)
            logger.info(
                "BigQueryAgentAnalyticsPlugin activé : %s.%s.agent_events",
                project_id,
                dataset_id,
            )
        except ImportError:
            logger.warning(
                "BigQueryAgentAnalyticsPlugin non disponible (version ADK insuffisante)"
            )
    else:
        logger.info(
            "GOOGLE_CLOUD_PROJECT absent — BigQueryAgentAnalyticsPlugin désactivé (mode dev)"
        )

    return App(
        name="orchestrator",
        root_agent=root_agent,
        plugins=plugins,
    )


# Instance globale — utilisée par les tests et le déploiement
app = create_app()
