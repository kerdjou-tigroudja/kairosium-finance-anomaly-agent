"""Tool ingest_transactions — parse CSV Cloud Storage et normalise les transactions."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from datetime import UTC, datetime

from google.adk.tools import ToolContext

from shared.models import Transaction

logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS = {"tx_id", "amount", "supplier_id", "category", "timestamp", "description"}


def _read_csv_content(gcs_path: str) -> str:
    """Lit le contenu CSV depuis Cloud Storage ou chemin local (fallback tests)."""
    if gcs_path.startswith("gs://"):
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT requis pour lire depuis Cloud Storage"
            )
        from google.cloud import storage  # type: ignore

        # Parse gs://bucket/path
        path_without_scheme = gcs_path[5:]
        bucket_name, blob_path = path_without_scheme.split("/", 1)
        client = storage.Client(project=project_id)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        return blob.download_as_text(encoding="utf-8")
    else:
        # Chemin local — pour tests et développement
        with open(gcs_path, encoding="utf-8") as f:
            return f.read()


def _parse_timestamp(raw: str) -> datetime:
    """Parse un timestamp ISO 8601 ou date simple en datetime UTC."""
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Format timestamp non reconnu : {raw!r}")


def ingest_transactions(gcs_path: str, tool_context: ToolContext) -> dict:
    """Parse et normalise les transactions depuis un fichier CSV Cloud Storage.

    Args:
        gcs_path: Chemin Cloud Storage (gs://bucket/path.csv) ou chemin local.

    Returns:
        dict avec status, count, et clé state où les transactions sont stockées.
    """
    try:
        csv_content = _read_csv_content(gcs_path)
    except Exception as exc:
        logger.error("Erreur lecture CSV depuis %s : %s", gcs_path, exc)
        return {"status": "error", "error": str(exc)}

    reader = csv.DictReader(io.StringIO(csv_content))

    # Validation schéma
    if reader.fieldnames is None:
        return {"status": "error", "error": "Fichier CSV vide ou sans en-têtes"}

    actual_columns = set(reader.fieldnames)
    # Ignorer expected_score (golden set) si présent
    required = _REQUIRED_COLUMNS - {"expected_score"}
    missing = required - actual_columns
    if missing:
        return {
            "status": "error",
            "error": f"Colonnes manquantes dans le CSV : {sorted(missing)}",
        }

    transactions: list[Transaction] = []
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):  # ligne 1 = en-tête
        try:
            tx = Transaction(
                tx_id=row["tx_id"].strip(),
                amount=float(row["amount"]),
                supplier_id=row["supplier_id"].strip(),
                category=row["category"].strip().upper(),
                timestamp=_parse_timestamp(row["timestamp"]),
                description=row["description"].strip(),
            )
            transactions.append(tx)
        except Exception as exc:
            errors.append(f"Ligne {i} : {exc}")
            if len(errors) > 10:
                errors.append("... (trop d'erreurs, arrêt anticipé)")
                break

    if errors:
        logger.warning("%d erreurs de parsing : %s", len(errors), errors[:3])

    if not transactions:
        return {
            "status": "error",
            "error": "Aucune transaction valide parsée",
            "parsing_errors": errors,
        }

    # Sauvegarder dans session state pour le scoring agent
    tool_context.state["temp:transactions"] = json.dumps(
        [tx.model_dump(mode="json") for tx in transactions],
        default=str,
    )

    logger.info(
        "Ingestion OK : %d transactions depuis %s (%d erreurs de parsing)",
        len(transactions),
        gcs_path,
        len(errors),
    )

    return {
        "status": "success",
        "count": len(transactions),
        "transactions_state_key": "temp:transactions",
        "parsing_errors": errors if errors else None,
    }
