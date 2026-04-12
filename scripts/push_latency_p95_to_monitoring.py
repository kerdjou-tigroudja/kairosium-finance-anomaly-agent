#!/usr/bin/env python3
"""Publie les p95 de latence tool et workflow depuis BigQuery vers Cloud Monitoring.

Les métriques custom `custom.googleapis.com/agent/latency_p95` et
`custom.googleapis.com/agent/workflow_latency_p95` n'existent pas tant qu'aucun
point n'est écrit : ce script les alimente à partir de `agent_events` (schéma
BigQueryAgentAnalyticsPlugin — colonne `latency_ms` JSON avec `total_ms`).

Usage typique : Cloud Scheduler horaire avec les mêmes variables d'environnement
que l'agent (`GOOGLE_CLOUD_PROJECT`, `BQ_DATASET_ID`).
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import time
import uuid

from google.api_core import exceptions as gexc
from google.cloud import bigquery

logger = logging.getLogger(__name__)

METRIC_TOOL = "custom.googleapis.com/agent/latency_p95"
METRIC_WORKFLOW = "custom.googleapis.com/agent/workflow_latency_p95"


def _write_gauge(project_id: str, metric_type: str, labels: dict[str, str], value: float) -> None:
    from google.cloud import monitoring_v3

    if not math.isfinite(value):
        logger.warning("Valeur non finie ignorée pour %s : %s", metric_type, value)
        return

    client = monitoring_v3.MetricServiceClient()
    series = monitoring_v3.TimeSeries()
    series.metric.type = metric_type
    for k, v in labels.items():
        series.metric.labels[k] = v[:64]
    series.resource.type = "global"
    now = time.time()
    sec, ns = int(now), int((now - int(now)) * 10**9)
    interval = monitoring_v3.TimeInterval(
        {"end_time": {"seconds": sec, "nanos": ns}},
    )
    point = monitoring_v3.Point(
        {"interval": interval, "value": {"double_value": float(value)}},
    )
    series.points = [point]
    name = f"projects/{project_id}"
    for attempt in range(3):
        try:
            client.create_time_series(request={"name": name, "time_series": [series]})
            return
        except gexc.InternalServerError:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hours",
        type=int,
        default=1,
        help="Fenêtre glissante en heures pour l'agrégat BQ (défaut: 1)",
    )
    args = parser.parse_args()

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    dataset = os.environ.get("BQ_DATASET_ID", "agent_prod")
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT requis")
        return 2

    table = f"`{project_id}.{dataset}.agent_events`"
    bq = bigquery.Client(project=project_id)
    hours = max(1, min(int(args.hours), 168))

    sql_tool = f"""
    SELECT
      agent AS agent_name,
      APPROX_QUANTILES(
        CAST(JSON_VALUE(latency_ms, '$.total_ms') AS INT64), 100
      )[OFFSET(95)] AS latency_p95
    FROM {table}
    WHERE event_type = 'TOOL_COMPLETED'
      AND JSON_VALUE(latency_ms, '$.total_ms') IS NOT NULL
      AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
      AND agent IS NOT NULL
    GROUP BY agent
    """
    rows = list(bq.query(sql_tool).result())
    run_id = uuid.uuid4().hex[:8]
    for row in rows:
        agent = row.agent_name or "unknown"
        p95 = float(row.latency_p95 or 0)
        _write_gauge(
            project_id,
            METRIC_TOOL,
            {"agent_name": agent, "run_id": run_id},
            p95,
        )
        logger.info("Écrit %s agent_name=%s p95=%.1f ms", METRIC_TOOL, agent, p95)

    sql_workflow = f"""
    WITH sums AS (
      SELECT
        session_id,
        SUM(CAST(JSON_VALUE(latency_ms, '$.total_ms') AS INT64)) AS workflow_ms
      FROM {table}
      WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        AND JSON_VALUE(latency_ms, '$.total_ms') IS NOT NULL
        AND session_id IS NOT NULL
      GROUP BY session_id
    )
    SELECT APPROX_QUANTILES(workflow_ms, 100)[OFFSET(95)] AS workflow_p95
    FROM sums
    """
    wf_rows = list(bq.query(sql_workflow).result())
    if wf_rows and wf_rows[0].workflow_p95 is not None:
        wf = float(wf_rows[0].workflow_p95)
        try:
            _write_gauge(
                project_id,
                METRIC_WORKFLOW,
                {"run_id": run_id, "scope": "session_sum"},
                wf,
            )
            logger.info("Écrit %s p95=%.1f ms", METRIC_WORKFLOW, wf)
        except gexc.GoogleAPICallError as exc:
            logger.warning(
                "Échec non bloquant %s (réessayez plus tard ou vérifiez quotas) : %s",
                METRIC_WORKFLOW,
                exc,
            )
    else:
        logger.warning("Aucune donnée workflow pour la fenêtre — métrique non écrite")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
