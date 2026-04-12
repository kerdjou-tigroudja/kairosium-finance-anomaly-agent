"""Tool trigger_alert — crée une Cloud Monitoring custom metric pour les transactions ALERTE."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import uuid
from datetime import UTC, datetime

from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

_METRIC_TYPE = "custom.googleapis.com/agent/anomaly_alert"


def _notify_slack_webhook(tx_id: str, amount: float, motifs: str) -> None:
    """POST non bloquant sur Incoming Webhook Slack si SLACK_WEBHOOK_URL est défini."""
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return
    text = (
        f":rotating_light: *Anomalie détectée* — `{tx_id}` | Montant : {amount} | Motifs : {motifs}"
    )
    payload = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.warning("Slack webhook failed: %s", e)


def _log_alert_failure_to_bigquery(tx_id: str, error: str, project_id: str) -> None:
    """Insère un enregistrement d'échec d'alerte dans BigQuery agent_events (non-bloquant)."""
    try:
        from google.cloud import bigquery  # type: ignore

        dataset_id = os.environ.get("BQ_DATASET_ID", "agent_prod")
        client = bigquery.Client(project=project_id)
        table_ref = f"{project_id}.{dataset_id}.agent_events"

        row = {
            "event_type": "alert_monitoring_error",
            "tx_id": tx_id,
            "error": error,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        errors = client.insert_rows_json(table_ref, [row])
        if errors:
            logger.debug("BigQuery agent_events insert partiel : %s", errors)
    except Exception as bq_exc:
        logger.debug("BigQuery agent_events indisponible : %s", bq_exc)


def trigger_alert(tx_id: str, motifs: str, amount: float, tool_context: ToolContext) -> dict:
    """Crée une time series Cloud Monitoring pour une transaction ALERTE.

    Metric custom : agent/anomaly_alert (DESIGN_SPEC §3.2).
    Chaque appel utilise un invocation_id unique pour éviter les collisions GAUGE
    (contrainte Cloud Monitoring : pas deux points sur la même série en < 1 minute).
    Ne bloque aucun paiement — supervision humaine requise (AI Act Art. 14).

    Args:
        tx_id: Identifiant de la transaction ALERTE.
        motifs: Motifs de l'alerte (séparés par ';').
        amount: Montant de la transaction en EUR.

    Returns:
        dict avec statut de création de la métrique Cloud Monitoring.
    """
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    invocation_id = uuid.uuid4().hex[:16]

    if not project_id:
        logger.warning(
            "GOOGLE_CLOUD_PROJECT non défini — alerte simulée pour tx_id=%s", tx_id
        )
        return {
            "status": "simulated",
            "metric": _METRIC_TYPE,
            "tx_id": tx_id,
            "amount": amount,
            "motifs": motifs,
            "note": "GOOGLE_CLOUD_PROJECT absent, alerte non envoyée à Cloud Monitoring",
        }

    try:
        from google.cloud import monitoring_v3  # type: ignore

        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        series = monitoring_v3.TimeSeries()
        series.metric.type = _METRIC_TYPE
        series.metric.labels["tx_id"] = tx_id[:64]  # limite label Cloud Monitoring
        series.metric.labels["motifs"] = motifs[:64]
        # invocation_id garantit une série distincte par appel : évite les erreurs 500
        # "TimeSeries could not be written" dues à deux points GAUGE sur la même série
        # dans un intervalle < 1 minute (ex : retry orchestrateur).
        series.metric.labels["invocation_id"] = invocation_id
        series.resource.type = "global"

        now = time.time()
        seconds = int(now)
        nanos = int((now - seconds) * 10**9)
        interval = monitoring_v3.TimeInterval(
            {
                "end_time": {"seconds": seconds, "nanos": nanos},
            }
        )
        point = monitoring_v3.Point(
            {"interval": interval, "value": {"double_value": amount}}
        )
        series.points = [point]

        client.create_time_series(
            request={"name": project_name, "time_series": [series]}
        )

        logger.info(
            "Alerte Cloud Monitoring créée : metric=%s tx_id=%s amount=%.2f invocation_id=%s",
            _METRIC_TYPE,
            tx_id,
            amount,
            invocation_id,
        )

        _notify_slack_webhook(tx_id, amount, motifs)

        return {
            "status": "success",
            "metric": _METRIC_TYPE,
            "tx_id": tx_id,
            "amount": amount,
            "motifs": motifs,
        }

    except Exception as exc:
        error_msg = str(exc)
        logger.warning(
            "Échec alerte Cloud Monitoring tx_id=%s invocation_id=%s — %s "
            "(non-bloquant : pipeline continue)",
            tx_id,
            invocation_id,
            error_msg,
        )
        _log_alert_failure_to_bigquery(tx_id, error_msg, project_id)
        return {
            "status": "error",
            "metric": _METRIC_TYPE,
            "tx_id": tx_id,
            "error": error_msg,
        }
