"""Tests pytest — pipeline NovaPay : scoring déterministe + accuracy golden set (DESIGN_SPEC §6)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from scoring_agent.tools.score import (
    _check_doublon_exact,
    _check_fournisseur_inconnu,
    _check_fractionnement,
    _check_montant_hors_baseline,
    _check_pattern_temporel,
    score_all_transactions,
)
from shared.models import ScoredTransaction, Transaction

_DATA_DIR = Path(__file__).parent.parent / "data"


# ---------------------------------------------------------------------------
# Tests unitaires des règles de scoring (DESIGN_SPEC §3.3)
# ---------------------------------------------------------------------------


class TestScoreMontantHorsBaseline:
    def test_alerte_quand_montant_depasse_seuil(self):
        tx = Transaction(
            tx_id="TX_001", amount=15000.0, supplier_id="SUP_001",
            category="TRAVEL", timestamp=datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
            description="Note de frais",
        )
        baseline = {"TRAVEL": 450.0}
        triggered, motif = _check_montant_hors_baseline(tx, baseline, 3.0)
        assert triggered is True
        assert "ALERTE_MONTANT_HORS_BASELINE" in motif
        assert "15000.00" in motif

    def test_normal_quand_montant_dans_baseline(self):
        tx = Transaction(
            tx_id="TX_002", amount=600.0, supplier_id="SUP_001",
            category="TRAVEL", timestamp=datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
            description="Billet train",
        )
        baseline = {"TRAVEL": 450.0}
        triggered, _ = _check_montant_hors_baseline(tx, baseline, 3.0)
        assert triggered is False

    def test_pas_dalerte_si_categorie_inconnue(self):
        tx = Transaction(
            tx_id="TX_003", amount=50000.0, supplier_id="SUP_001",
            category="UNKNOWN", timestamp=datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
            description="Catégorie inconnue",
        )
        baseline = {}
        triggered, _ = _check_montant_hors_baseline(tx, baseline, 3.0)
        assert triggered is False


class TestScoreDoublonExact:
    def test_doublon_detecte(self):
        ts = datetime(2026, 1, 10, 9, 0, tzinfo=UTC)
        tx = Transaction(
            tx_id="TX_D02", amount=500.0, supplier_id="SUP_001",
            category="IT", timestamp=ts, description="Facture",
        )
        seen = {"SUP_001|500.00|2026-01-10"}  # première occurrence déjà vue
        triggered, motif = _check_doublon_exact(tx, seen)
        assert triggered is True
        assert "ALERTE_DOUBLON_EXACT" in motif

    def test_premiere_occurrence_non_doublon(self):
        ts = datetime(2026, 1, 10, 9, 0, tzinfo=UTC)
        tx = Transaction(
            tx_id="TX_D01", amount=500.0, supplier_id="SUP_001",
            category="IT", timestamp=ts, description="Facture",
        )
        seen: set = set()
        triggered, _ = _check_doublon_exact(tx, seen)
        assert triggered is False
        assert len(seen) == 1  # clé ajoutée


class TestScoreFournisseurInconnu:
    def test_suspect_si_absent_du_referentiel(self):
        tx = Transaction(
            tx_id="TX_F01", amount=300.0, supplier_id="SUP_UNKNOWN_999",
            category="CONSULTING", timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
            description="Fournisseur inconnu",
        )
        registry = ["SUP_001", "SUP_002"]
        triggered, motif = _check_fournisseur_inconnu(tx, registry)
        assert triggered is True
        assert "SUSPECT_FOURNISSEUR_INCONNU" in motif

    def test_normal_si_present(self):
        tx = Transaction(
            tx_id="TX_F02", amount=300.0, supplier_id="SUP_001",
            category="CONSULTING", timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
            description="Fournisseur connu",
        )
        triggered, _ = _check_fournisseur_inconnu(tx, ["SUP_001", "SUP_002"])
        assert triggered is False


class TestScorePatternTemporel:
    def test_suspect_heure_nuit(self):
        tx = Transaction(
            tx_id="TX_T01", amount=200.0, supplier_id="SUP_001",
            category="OFFICE",
            timestamp=datetime(2026, 1, 7, 3, 12, tzinfo=UTC),  # 03h12 UTC
            description="Transaction nuit",
        )
        triggered, motif = _check_pattern_temporel(tx, 2, 4)
        assert triggered is True
        assert "SUSPECT_PATTERN_TEMPOREL" in motif

    def test_suspect_weekend_dimanche(self):
        # 2026-01-04 est un dimanche
        tx = Transaction(
            tx_id="TX_T02", amount=200.0, supplier_id="SUP_001",
            category="OFFICE",
            timestamp=datetime(2026, 1, 4, 10, 0, tzinfo=UTC),
            description="Transaction dimanche",
        )
        triggered, motif = _check_pattern_temporel(tx, 2, 4)
        assert triggered is True
        assert "dimanche" in motif.lower() or "SUSPECT" in motif

    def test_normal_heure_bureau_lundi(self):
        # 2026-01-05 est un lundi
        tx = Transaction(
            tx_id="TX_T03", amount=200.0, supplier_id="SUP_001",
            category="OFFICE",
            timestamp=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
            description="Transaction normale",
        )
        triggered, _ = _check_pattern_temporel(tx, 2, 4)
        assert triggered is False


class TestScoreFractionnement:
    def _make_tx(self, tx_id: str, amount: float, supplier: str, hour: int) -> Transaction:
        return Transaction(
            tx_id=tx_id, amount=amount, supplier_id=supplier,
            category="CONSULTING",
            timestamp=datetime(2026, 1, 5, hour, 0, tzinfo=UTC),
            description="Paiement partiel",
        )

    def test_suspect_fractionnement_detecte(self):
        supplier = "SUP_010"
        # 5 transactions de 490€ vers le même fournisseur en 24h, somme = 2450€ > 500€
        txs = [self._make_tx(f"TX_FR0{i}", 490.0, supplier, i * 2) for i in range(5)]
        # Tester la 3ème transaction
        triggered, motif = _check_fractionnement(txs[2], txs, 48, 500.0, 3)
        assert triggered is True
        assert "SUSPECT_FRACTIONNEMENT" in motif

    def test_pas_de_fractionnement_si_moins_de_3(self):
        supplier = "SUP_010"
        txs = [self._make_tx(f"TX_FR0{i}", 490.0, supplier, i * 10) for i in range(2)]
        triggered, _ = _check_fractionnement(txs[1], txs, 48, 500.0, 3)
        assert triggered is False


# ---------------------------------------------------------------------------
# Test accuracy sur golden set (DESIGN_SPEC KPI : ≥ 85%)
# ---------------------------------------------------------------------------


def test_accuracy_golden_set(golden_set, state_with_golden_transactions, mock_bq):
    """Test E2E scoring sur le golden set — accuracy cible ≥ 85% (DESIGN_SPEC §6)."""
    mock_ctx = MagicMock()
    mock_ctx.state = dict(state_with_golden_transactions)

    result = score_all_transactions(mock_ctx)
    assert result["status"] == "success", f"Scoring échoué : {result}"

    # Désérialiser les résultats
    scored_raw = mock_ctx.state.get("temp:scored_transactions")
    assert scored_raw, "Aucune transaction scorée en state"
    scored = [ScoredTransaction(**d) for d in json.loads(scored_raw)]

    # Construire le mapping tx_id → expected_score
    expected_map = {row["tx_id"]: row["expected_score"] for row in golden_set}

    # Calculer l'accuracy
    correct = 0
    total = len(scored)
    errors = []

    for s in scored:
        expected = expected_map.get(s.tx_id)
        if expected is None:
            continue
        if s.score == expected:
            correct += 1
        else:
            errors.append(
                f"tx_id={s.tx_id}: prédit={s.score}, attendu={expected}, motifs={s.motifs}"
            )

    accuracy = correct / total if total > 0 else 0.0

    # Afficher les erreurs pour diagnostic
    if errors:
        error_sample = "\n  ".join(errors[:10])
        print(f"\n{len(errors)} erreurs de classification (sample) :\n  {error_sample}")

    assert total >= 200, f"Moins de 200 transactions scorées : {total}"
    assert accuracy >= 0.85, (
        f"Accuracy {accuracy:.1%} < 85% sur {total} transactions "
        f"({correct} corrects, {len(errors)} erreurs)"
    )

    print(f"\nAccuracy golden set : {accuracy:.1%} ({correct}/{total})")
    print(
        f"NORMAL={result['normal_count']}, "
        f"SUSPECT={result['suspect_count']}, "
        f"ALERTE={result['alert_count']}"
    )


# ---------------------------------------------------------------------------
# Test ingestion
# ---------------------------------------------------------------------------


def test_ingest_transactions_local(tmp_path, agent_config):
    """Vérifie que ingest_transactions parse correctement un CSV local."""
    from ingestion_agent.tools.ingest import ingest_transactions

    # Créer un CSV minimal
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(
        "tx_id,amount,supplier_id,category,timestamp,description\n"
        "TX_001,500.00,SUP_001,IT,2026-01-05T10:00:00+00:00,Test transaction\n"
        "TX_002,invalid_amount,SUP_002,TRAVEL,2026-01-05T11:00:00+00:00,Test 2\n"
    )

    mock_ctx = MagicMock()
    mock_ctx.state = {}

    result = ingest_transactions(str(csv_path), mock_ctx)

    assert result["status"] == "success"
    assert result["count"] == 1  # TX_002 a un montant invalide
    assert "temp:transactions" in mock_ctx.state
    txs = json.loads(mock_ctx.state["temp:transactions"])
    assert txs[0]["tx_id"] == "TX_001"
    assert txs[0]["amount"] == 500.0


def test_ingest_manque_colonnes(tmp_path):
    """Vérifie la détection de colonnes manquantes."""
    from ingestion_agent.tools.ingest import ingest_transactions

    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("tx_id,amount\nTX_001,100.0\n")

    mock_ctx = MagicMock()
    mock_ctx.state = {}

    result = ingest_transactions(str(csv_path), mock_ctx)
    assert result["status"] == "error"
    assert "manquantes" in result["error"]


# ---------------------------------------------------------------------------
# Test génération rapport
# ---------------------------------------------------------------------------


def test_generate_audit_report(state_with_golden_transactions, mock_bq):
    """Vérifie la génération du rapport après scoring."""
    from orchestrator.tools.report import generate_audit_report

    mock_ctx = MagicMock()
    mock_ctx.state = dict(state_with_golden_transactions)

    # D'abord scorer
    score_result = score_all_transactions(mock_ctx)
    assert score_result["status"] == "success"

    # Puis générer le rapport
    report_result = generate_audit_report(mock_ctx)
    assert report_result["status"] == "success"
    assert "report_id" in report_result
    assert report_result["total_transactions"] == 250
    assert (
        report_result["normal_count"]
        + report_result["suspect_count"]
        + report_result["alert_count"]
        == 250
    )
    alerts = report_result.get("alert_transactions") or []
    assert len(alerts) == report_result["alert_count"]
    for row in alerts:
        assert "tx_id" in row and "amount" in row and "motifs" in row
