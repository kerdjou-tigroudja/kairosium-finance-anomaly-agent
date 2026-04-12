"""Tool score_all_transactions — règles déterministes + fallback LLM (DESIGN_SPEC §3.3)."""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, timedelta
from typing import Literal

from google.adk.tools import ToolContext

from config.loader import load_config
from shared.models import ScoredTransaction, Transaction

logger = logging.getLogger(__name__)

Score = Literal["NORMAL", "SUSPECT", "ALERTE"]


def _compute_baseline(transactions: list[Transaction]) -> dict[str, float]:
    """Calcule la moyenne de montant par catégorie sur le batch."""
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for tx in transactions:
        totals[tx.category] += tx.amount
        counts[tx.category] += 1
    return {cat: totals[cat] / counts[cat] for cat in totals}


def _check_montant_hors_baseline(
    tx: Transaction,
    baseline: dict[str, float],
    multiplier: float,
) -> tuple[bool, str]:
    """Règle 1 — ALERTE : montant > baseline_mean × multiplier."""
    mean = baseline.get(tx.category)
    if mean is None or mean == 0:
        return False, ""
    if tx.amount > mean * multiplier:
        return True, (
            f"ALERTE_MONTANT_HORS_BASELINE: {tx.amount:.2f}€ "
            f"> {mean:.2f}€ × {multiplier} (catégorie {tx.category})"
        )
    return False, ""


def _check_doublon_exact(
    tx: Transaction,
    seen_keys: set[str],
) -> tuple[bool, str]:
    """Règle 2 — ALERTE : même supplier_id + même amount + même jour."""
    key = f"{tx.supplier_id}|{tx.amount:.2f}|{tx.timestamp.date()}"
    if key in seen_keys:
        return True, (
            f"ALERTE_DOUBLON_EXACT: supplier={tx.supplier_id}, "
            f"amount={tx.amount:.2f}€, date={tx.timestamp.date()}"
        )
    seen_keys.add(key)
    return False, ""


def _check_fournisseur_inconnu(
    tx: Transaction,
    supplier_registry: list[str],
) -> tuple[bool, str]:
    """Règle 3 — SUSPECT : supplier_id absent du référentiel Firestore."""
    if tx.supplier_id not in supplier_registry:
        return True, f"SUSPECT_FOURNISSEUR_INCONNU: supplier_id={tx.supplier_id!r} absent du référentiel"
    return False, ""


def _check_pattern_temporel(
    tx: Transaction,
    hours_start: int,
    hours_end: int,
) -> tuple[bool, str]:
    """Règle 4 — SUSPECT : transaction entre 02h00–04h00 UTC ou weekend."""
    ts = tx.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    utc_ts = ts.astimezone(UTC)

    hour = utc_ts.hour
    weekday = utc_ts.weekday()  # 5=samedi, 6=dimanche

    if hours_start <= hour < hours_end:
        return True, (
            f"SUSPECT_PATTERN_TEMPOREL: transaction à {utc_ts.strftime('%H:%M')} UTC "
            f"(plage suspecte {hours_start:02d}h00–{hours_end:02d}h00)"
        )
    if weekday in (5, 6):
        day_name = "samedi" if weekday == 5 else "dimanche"
        return True, f"SUSPECT_PATTERN_TEMPOREL: transaction le {day_name} hors politique"
    return False, ""


def _check_fractionnement(
    tx: Transaction,
    all_transactions: list[Transaction],
    window_hours: int,
    threshold: float,
    min_count: int,
) -> tuple[bool, str]:
    """Règle 5 — SUSPECT : N transactions < seuil vers même supplier en ≤ window_hours, somme > seuil."""
    if tx.amount >= threshold:
        return False, ""

    ts = tx.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)

    window_start = ts - timedelta(hours=window_hours)
    window_end = ts + timedelta(hours=window_hours)

    # Toutes les transactions < seuil vers le même fournisseur dans la fenêtre
    related = [
        t for t in all_transactions
        if t.supplier_id == tx.supplier_id
        and t.amount < threshold
        and t.tx_id != tx.tx_id
        and window_start <= (
            t.timestamp if t.timestamp.tzinfo else t.timestamp.replace(tzinfo=UTC)
        ) <= window_end
    ]

    if len(related) >= (min_count - 1):  # -1 car on compte tx elle-même
        total = sum(t.amount for t in related) + tx.amount
        if total > threshold:
            return True, (
                f"SUSPECT_FRACTIONNEMENT: {len(related) + 1} transactions "
                f"< {threshold:.0f}€ vers supplier={tx.supplier_id} "
                f"en {window_hours}h, somme={total:.2f}€ > {threshold:.0f}€"
            )
    return False, ""


def score_all_transactions(tool_context: ToolContext) -> dict:
    """Score toutes les transactions depuis le session state selon les règles DESIGN_SPEC §3.3.

    Règles par ordre de priorité :
    1. ALERTE — Montant hors baseline ×3
    2. ALERTE — Doublon exact
    3. SUSPECT — Fournisseur inconnu
    4. SUSPECT — Pattern temporel (02h–04h UTC ou weekend)
    5. SUSPECT — Fractionnement (N < seuil vers même fournisseur en 48h)

    Returns:
        dict avec status et compteurs par catégorie de score.
    """
    raw = tool_context.state.get("temp:transactions")
    if not raw:
        return {
            "status": "error",
            "error": "Aucune transaction en state (temp:transactions). L'ingestion a-t-elle été effectuée ?",
        }

    try:
        tx_data = json.loads(raw)
        transactions = [Transaction(**d) for d in tx_data]
    except Exception as exc:
        return {"status": "error", "error": f"Erreur désérialisation transactions : {exc}"}

    config = load_config()
    baseline = _compute_baseline(transactions)
    seen_doublon_keys: set[str] = set()
    scored: list[ScoredTransaction] = []

    alert_count = suspect_count = normal_count = 0

    for tx in transactions:
        alerte_motifs: list[str] = []
        suspect_motifs: list[str] = []

        # Priorité 1 — doublon exact (traité avant montant pour cohérence du seen_keys)
        is_doublon, motif_doublon = _check_doublon_exact(tx, seen_doublon_keys)
        if is_doublon:
            alerte_motifs.append(motif_doublon)

        # Priorité 1 — montant hors baseline
        is_hors_baseline, motif_hb = _check_montant_hors_baseline(
            tx, baseline, config.baseline_multiplier
        )
        if is_hors_baseline:
            alerte_motifs.append(motif_hb)

        # Priorité 2 — fournisseur inconnu
        is_inconnu, motif_inconnu = _check_fournisseur_inconnu(tx, config.supplier_registry)
        if is_inconnu:
            suspect_motifs.append(motif_inconnu)

        # Priorité 2 — pattern temporel
        is_temporel, motif_temporel = _check_pattern_temporel(
            tx, config.suspect_hours_start, config.suspect_hours_end
        )
        if is_temporel:
            suspect_motifs.append(motif_temporel)

        # Priorité 3 — fractionnement
        is_frac, motif_frac = _check_fractionnement(
            tx,
            transactions,
            config.fractionnement_window_hours,
            config.validation_threshold,
            config.fractionnement_min_count,
        )
        if is_frac:
            suspect_motifs.append(motif_frac)

        # Détermination du score final
        if alerte_motifs:
            final_score: Score = "ALERTE"
            all_motifs = alerte_motifs + suspect_motifs
            alert_count += 1
        elif suspect_motifs:
            final_score = "SUSPECT"
            all_motifs = suspect_motifs
            suspect_count += 1
        else:
            final_score = "NORMAL"
            all_motifs = []
            normal_count += 1

        scored.append(
            ScoredTransaction.from_transaction(
                tx=tx,
                score=final_score,
                motifs=all_motifs,
                trace_id=str(uuid.uuid4()),
            )
        )

    # Sauvegarder dans state pour l'orchestrateur
    tool_context.state["temp:scored_transactions"] = json.dumps(
        [s.model_dump(mode="json") for s in scored],
        default=str,
    )

    logger.info(
        "Scoring OK : %d NORMAL, %d SUSPECT, %d ALERTE sur %d transactions",
        normal_count,
        suspect_count,
        alert_count,
        len(transactions),
    )

    return {
        "status": "success",
        "total": len(transactions),
        "normal_count": normal_count,
        "suspect_count": suspect_count,
        "alert_count": alert_count,
        "scored_state_key": "temp:scored_transactions",
    }
