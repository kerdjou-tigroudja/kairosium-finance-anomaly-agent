"""Import pytest JUnit XML results into BigQuery table test_runs (DESIGN_SPEC §4 / SETUP.md §6.2).

Usage:
    uv run python scripts/import_test_results.py results.xml

Requires:
    GOOGLE_CLOUD_PROJECT env var (skip silently if absent)
    BQ_DATASET_ID env var (default: agent_prod)
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _get_git_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def parse_junit_xml(xml_path: str) -> list[dict]:
    """Parse JUnit XML and return rows matching test_runs schema."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Support both <testsuites> (wrapper) and <testsuite> (direct)
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]

    rows = []
    run_id = str(uuid.uuid4())
    branch = _get_git_branch()
    timestamp = datetime.now(tz=UTC).isoformat()

    for suite in suites:
        for tc in suite.findall("testcase"):
            classname = tc.get("classname", "")
            name = tc.get("name", "")
            test_id = f"{classname}::{name}" if classname else name

            duration_s = float(tc.get("time", 0) or 0)
            duration_ms = int(duration_s * 1000)

            if tc.find("failure") is not None:
                status = "failed"
            elif tc.find("error") is not None:
                status = "error"
            elif tc.find("skipped") is not None:
                status = "skipped"
            else:
                status = "passed"

            rows.append({
                "run_id": run_id,
                "test_id": test_id,
                "status": status,
                "duration_ms": duration_ms,
                "branch": branch,
                "timestamp": timestamp,
            })

    return rows


def write_to_bigquery(rows: list[dict], project_id: str, dataset_id: str) -> None:
    from google.cloud import bigquery  # type: ignore

    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.test_runs"
    errors = client.insert_rows_json(table_ref, rows)
    if errors:
        logger.error("Erreurs insertion BigQuery test_runs : %s", errors)
        raise RuntimeError(f"BigQuery insert_rows_json errors: {errors}")
    logger.info("%d résultats écrits dans %s", len(rows), table_ref)


def main() -> None:
    if len(sys.argv) < 2:
        logger.error("Usage: import_test_results.py <results.xml>")
        sys.exit(1)

    xml_path = sys.argv[1]
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.info("GOOGLE_CLOUD_PROJECT absent — import test_runs ignoré (mode dev)")
        return

    dataset_id = os.environ.get("BQ_DATASET_ID", "agent_prod")

    rows = parse_junit_xml(xml_path)
    if not rows:
        logger.warning("Aucun test trouvé dans %s", xml_path)
        return

    logger.info("%d tests parsés depuis %s (branche: %s)", len(rows), xml_path, rows[0]["branch"])
    write_to_bigquery(rows, project_id, dataset_id)


if __name__ == "__main__":
    main()
