"""Fixtures pytest pour les tests NovaPay."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shared.models import AgentConfig, Transaction

_DATA_DIR = Path(__file__).parent.parent / "data"
_CONFIG_PATH = Path(__file__).parent.parent / "config" / "agent_config.json"


@pytest.fixture(scope="session")
def agent_config() -> AgentConfig:
    """Charge la config depuis agent_config.json (pas de Firestore en test)."""
    with open(_CONFIG_PATH) as f:
        data = json.load(f)
    return AgentConfig(**data)


@pytest.fixture(scope="session")
def golden_set() -> list[dict]:
    """Parse golden_set.csv et retourne la liste de dicts avec expected_score."""
    csv_path = _DATA_DIR / "golden_set.csv"
    if not csv_path.exists():
        pytest.skip("golden_set.csv absent — exécuter data/generate_golden_set.py d'abord")

    rows = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


@pytest.fixture(scope="session")
def golden_transactions(golden_set) -> list[Transaction]:
    """Retourne le golden set sous forme de List[Transaction]."""
    txs = []
    for row in golden_set:
        txs.append(
            Transaction(
                tx_id=row["tx_id"],
                amount=float(row["amount"]),
                supplier_id=row["supplier_id"],
                category=row["category"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                description=row["description"],
            )
        )
    return txs


@pytest.fixture
def mock_gcs(tmp_path):
    """Mock google.cloud.storage pour lire depuis un fichier temporaire."""
    csv_src = _DATA_DIR / "golden_set.csv"
    local_copy = tmp_path / "golden_set.csv"
    local_copy.write_bytes(csv_src.read_bytes())

    with patch("ingestion_agent.tools.ingest._read_csv_content") as mock_read:
        mock_read.return_value = local_copy.read_text(encoding="utf-8")
        yield mock_read


@pytest.fixture
def mock_bq():
    """Mock google.cloud.bigquery.Client pour éviter les écritures réelles en test."""
    with patch("orchestrator.tools.report._write_to_bigquery") as mock_write:
        mock_write.return_value = None
        yield mock_write


@pytest.fixture
def mock_monitoring():
    """Mock google.cloud.monitoring_v3 pour éviter les appels Cloud Monitoring en test."""
    with patch("orchestrator.tools.alert.monitoring_v3") as mock_m:
        mock_client = MagicMock()
        mock_m.MetricServiceClient.return_value = mock_client
        mock_m.TimeSeries.return_value = MagicMock()
        mock_m.TimeInterval.return_value = MagicMock()
        mock_m.Point.return_value = MagicMock()
        yield mock_client


@pytest.fixture
def state_with_golden_transactions(golden_transactions, agent_config):
    """Prépare un state contenant les transactions du golden set sérialisées."""
    state = {
        "temp:transactions": json.dumps(
            [tx.model_dump(mode="json") for tx in golden_transactions],
            default=str,
        )
    }
    return state
