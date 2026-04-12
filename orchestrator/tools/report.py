"""Tool generate_audit_report — agrège les ScoredTransaction et écrit dans BigQuery."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime

from google.adk.tools import ToolContext

from shared.models import AuditReport, ScoredTransaction

logger = logging.getLogger(__name__)


def _write_to_bigquery(report: AuditReport, project_id: str, dataset_id: str) -> None:
    """Écrit le rapport dans BigQuery table audit_reports (DESIGN_SPEC §4)."""
    from google.cloud import bigquery  # type: ignore

    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.audit_reports"

    # Sérialiser les transactions pour BigQuery (ARRAY<STRUCT>)
    tx_rows = [
        {
            "tx_id": t.tx_id,
            "score": t.score,
            "motifs": t.motifs,
            "trace_id": t.trace_id,
        }
        for t in report.transactions
    ]

    row = {
        "report_id": report.report_id,
        "timestamp": report.timestamp.isoformat(),
        "total_transactions": report.total_transactions,
        "normal_count": report.normal_count,
        "suspect_count": report.suspect_count,
        "alert_count": report.alert_count,
        "transactions": tx_rows,
    }

    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        logger.error("Erreurs insertion BigQuery audit_reports : %s", errors)
        raise RuntimeError(f"BigQuery insert_rows_json errors : {errors}")

    logger.info("Rapport %s écrit dans BigQuery %s", report.report_id, table_ref)


def generate_audit_report(tool_context: ToolContext) -> dict:
    """Agrège les ScoredTransaction et génère un AuditReport dans BigQuery.

    Lit les transactions scorées depuis le session state (temp:scored_transactions).

    Returns:
        dict avec report_id, compteurs, et statut BigQuery.
    """
    raw = tool_context.state.get("temp:scored_transactions")
    if not raw:
        return {
            "status": "error",
            "error": "Aucune transaction scorée en state. Le scoring a-t-il été effectué ?",
        }

    try:
        scored_data = json.loads(raw)
        scored: list[ScoredTransaction] = [ScoredTransaction(**d) for d in scored_data]
    except Exception as exc:
        return {"status": "error", "error": f"Erreur désérialisation transactions scorées : {exc}"}

    alert_count = sum(1 for t in scored if t.score == "ALERTE")
    suspect_count = sum(1 for t in scored if t.score == "SUSPECT")
    normal_count = sum(1 for t in scored if t.score == "NORMAL")

    report = AuditReport(
        report_id=str(uuid.uuid4()),
        timestamp=datetime.now(tz=UTC),
        total_transactions=len(scored),
        normal_count=normal_count,
        suspect_count=suspect_count,
        alert_count=alert_count,
        transactions=scored,
    )

    # Sauvegarder le rapport dans state pour les alertes
    tool_context.state["temp:audit_report"] = report.model_dump_json()
    tool_context.state["temp:alert_transactions"] = json.dumps(
        [s.model_dump(mode="json") for s in scored if s.score == "ALERTE"],
        default=str,
    )

    # Écriture BigQuery (si env GCP configuré)
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    dataset_id = os.environ.get("BQ_DATASET_ID", "agent_prod")
    bq_status = "skipped_no_gcp_project"

    if project_id:
        try:
            _write_to_bigquery(report, project_id, dataset_id)
            bq_status = "written"
        except Exception as exc:
            logger.warning("BigQuery indisponible (non bloquant) : %s", exc)
            bq_status = f"error: {exc}"

    alert_items = [
        {
            "tx_id": t.tx_id,
            "amount": float(t.amount),
            "motifs": ";".join(t.motifs) if t.motifs else "",
        }
        for t in scored
        if t.score == "ALERTE"
    ]

    logger.info(
        "Rapport %s : %d NORMAL, %d SUSPECT, %d ALERTE | BQ: %s",
        report.report_id,
        normal_count,
        suspect_count,
        alert_count,
        bq_status,
    )

    return {
        "status": "success",
        "report_id": report.report_id,
        "total_transactions": len(scored),
        "normal_count": normal_count,
        "suspect_count": suspect_count,
        "alert_count": alert_count,
        "alert_transactions": alert_items,
        "bq_table": f"{project_id}.{dataset_id}.audit_reports" if project_id else "N/A",
        "bq_status": bq_status,
    }
