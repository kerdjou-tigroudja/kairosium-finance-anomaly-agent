"""Générateur de golden set — 250 transactions synthétiques NovaPay (DESIGN_SPEC §5)."""

from __future__ import annotations

import csv
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Reproductibilité garantie
SEED = 42
random.seed(SEED)

OUTPUT_PATH = Path(__file__).parent / "golden_set.csv"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "agent_config.json"

# Paramètres NovaPay
CATEGORIES = ["TRAVEL", "IT", "OFFICE", "CATERING", "TRAINING", "CONSULTING", "EQUIPMENT"]
CATEGORY_BASELINES = {
    "TRAVEL": 450.0,
    "IT": 1200.0,
    "OFFICE": 150.0,
    "CATERING": 80.0,
    "TRAINING": 600.0,
    "CONSULTING": 2000.0,
    "EQUIPMENT": 800.0,
}

with open(CONFIG_PATH) as f:
    _cfg = json.load(f)

SUPPLIER_REGISTRY: list[str] = _cfg["supplier_registry"]
BASELINE_MULTIPLIER: float = _cfg["baseline_multiplier"]
SUSPECT_HOURS_START: int = _cfg["suspect_hours_start"]
SUSPECT_HOURS_END: int = _cfg["suspect_hours_end"]
VALIDATION_THRESHOLD: float = _cfg["validation_threshold"]


def _normal_hour() -> int:
    """Heure bureau : 8h–18h, lundi–vendredi."""
    return random.randint(8, 17)


def _normal_weekday(base_date: datetime) -> datetime:
    """Assure un jour ouvré (lundi–vendredi)."""
    while base_date.weekday() >= 5:
        base_date += timedelta(days=1)
    return base_date


def _random_base_date(offset_days_range: tuple[int, int] = (0, 90)) -> datetime:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    delta = random.randint(*offset_days_range)
    return base + timedelta(days=delta)


def _make_normal(tx_id: str) -> dict:
    category = random.choice(CATEGORIES)
    baseline = CATEGORY_BASELINES[category]
    # Montant dans la baseline (entre 50% et 200% de la baseline — jamais au-delà de ×3)
    amount = round(baseline * random.uniform(0.5, 1.9), 2)
    ts = _normal_weekday(_random_base_date())
    ts = ts.replace(hour=_normal_hour(), minute=random.randint(0, 59), second=0)
    return {
        "tx_id": tx_id,
        "amount": amount,
        "supplier_id": random.choice(SUPPLIER_REGISTRY),
        "category": category,
        "timestamp": ts.isoformat(),
        "description": f"Dépense {category.lower()} NovaPay",
        "expected_score": "NORMAL",
    }


def _make_doublon_pair(base_tx_id: str, pair_tx_id: str) -> list[dict]:
    """Deux transactions identiques (même supplier, montant, date) → ALERTE doublon exact."""
    category = random.choice(CATEGORIES)
    baseline = CATEGORY_BASELINES[category]
    amount = round(baseline * random.uniform(0.5, 1.5), 2)
    supplier = random.choice(SUPPLIER_REGISTRY)
    ts = _normal_weekday(_random_base_date())
    ts = ts.replace(hour=_normal_hour(), minute=10, second=0)
    # Même jour, heure légèrement différente (mais même date → doublon exact)
    ts2 = ts.replace(hour=ts.hour + 1 if ts.hour < 17 else ts.hour)

    base = {
        "tx_id": base_tx_id,
        "amount": amount,
        "supplier_id": supplier,
        "category": category,
        "timestamp": ts.isoformat(),
        "description": f"Facture {supplier} {category.lower()}",
        "expected_score": "NORMAL",  # première occurrence = normale
    }
    duplicate = {
        "tx_id": pair_tx_id,
        "amount": amount,
        "supplier_id": supplier,
        "category": category,
        "timestamp": ts2.isoformat(),
        "description": f"Facture {supplier} {category.lower()}",
        "expected_score": "ALERTE",  # doublon → alerte
    }
    return [base, duplicate]


def _make_montant_hors_baseline(tx_id: str) -> dict:
    """Montant > baseline ×3 → ALERTE."""
    category = random.choice(CATEGORIES)
    baseline = CATEGORY_BASELINES[category]
    amount = round(baseline * (BASELINE_MULTIPLIER + random.uniform(0.5, 2.0)), 2)
    ts = _normal_weekday(_random_base_date())
    ts = ts.replace(hour=_normal_hour(), minute=random.randint(0, 59), second=0)
    return {
        "tx_id": tx_id,
        "amount": amount,
        "supplier_id": random.choice(SUPPLIER_REGISTRY),
        "category": category,
        "timestamp": ts.isoformat(),
        "description": f"Dépense exceptionnelle {category.lower()}",
        "expected_score": "ALERTE",
    }


def _make_fournisseur_inconnu(tx_id: str) -> dict:
    """supplier_id absent du référentiel → SUSPECT."""
    category = random.choice(CATEGORIES)
    baseline = CATEGORY_BASELINES[category]
    amount = round(baseline * random.uniform(0.5, 1.5), 2)
    ts = _normal_weekday(_random_base_date())
    ts = ts.replace(hour=_normal_hour(), minute=random.randint(0, 59), second=0)
    unknown_supplier = f"SUP_UNKNOWN_{random.randint(100, 999)}"
    return {
        "tx_id": tx_id,
        "amount": amount,
        "supplier_id": unknown_supplier,
        "category": category,
        "timestamp": ts.isoformat(),
        "description": f"Paiement fournisseur inconnu {unknown_supplier}",
        "expected_score": "SUSPECT",
    }


def _make_pattern_temporel(tx_id: str) -> dict:
    """Transaction 03h00 UTC ou dimanche → SUSPECT."""
    category = random.choice(CATEGORIES)
    baseline = CATEGORY_BASELINES[category]
    amount = round(baseline * random.uniform(0.5, 1.5), 2)
    base_date = _random_base_date()
    # Alterner nuit et weekend
    if random.random() < 0.5:
        # Heure suspecte (entre suspect_hours_start et suspect_hours_end)
        ts = _normal_weekday(base_date)
        ts = ts.replace(
            hour=random.randint(SUSPECT_HOURS_START, SUSPECT_HOURS_END - 1),
            minute=random.randint(0, 59),
            second=0,
        )
    else:
        # Dimanche
        while base_date.weekday() != 6:
            base_date += timedelta(days=1)
        ts = base_date.replace(hour=_normal_hour(), minute=random.randint(0, 59), second=0)
    return {
        "tx_id": tx_id,
        "amount": amount,
        "supplier_id": random.choice(SUPPLIER_REGISTRY),
        "category": category,
        "timestamp": ts.isoformat(),
        "description": "Transaction hors horaires habituels",
        "expected_score": "SUSPECT",
    }


def _make_fractionnement_group(tx_ids: list[str]) -> list[dict]:
    """5 transactions < seuil vers même fournisseur en 24h, somme > seuil → SUSPECT."""
    category = random.choice(CATEGORIES)
    supplier = random.choice(SUPPLIER_REGISTRY)
    # Montant individuel < VALIDATION_THRESHOLD, mais somme > VALIDATION_THRESHOLD
    n = len(tx_ids)
    per_tx = round((VALIDATION_THRESHOLD / n) * random.uniform(0.85, 0.95), 2)
    base_ts = _normal_weekday(_random_base_date())
    base_ts = base_ts.replace(hour=9, minute=0, second=0)

    rows = []
    for i, tx_id in enumerate(tx_ids):
        ts = base_ts + timedelta(hours=i * 4)  # espacées de 4h → dans la fenêtre 48h
        rows.append({
            "tx_id": tx_id,
            "amount": per_tx,
            "supplier_id": supplier,
            "category": category,
            "timestamp": ts.isoformat(),
            "description": f"Règlement partiel {supplier} tranche {i + 1}/{n}",
            "expected_score": "SUSPECT",
        })
    return rows


def generate() -> list[dict]:
    rows: list[dict] = []
    tx_counter = 1

    def next_id() -> str:
        nonlocal tx_counter
        tx_id = f"TX_{tx_counter:05d}"
        tx_counter += 1
        return tx_id

    # 1. Doublons exacts (20 transactions = 10 paires → 10 normales + 10 alertes)
    # Les 10 premières occurrences sont NORMAL (comptées dans les 200 normales)
    # Les 10 doublons sont ALERTE
    for _ in range(10):
        pair = _make_doublon_pair(next_id(), next_id())
        rows.extend(pair)

    # 2. Montants hors baseline (10 transactions ALERTE)
    for _ in range(10):
        rows.append(_make_montant_hors_baseline(next_id()))

    # 3. Fournisseurs inconnus (10 transactions SUSPECT)
    for _ in range(10):
        rows.append(_make_fournisseur_inconnu(next_id()))

    # 4. Patterns temporels (10 transactions SUSPECT)
    for _ in range(10):
        rows.append(_make_pattern_temporel(next_id()))

    # 5. Fractionnements (10 transactions SUSPECT = 2 groupes de 5)
    for _ in range(2):
        group_ids = [next_id() for _ in range(5)]
        rows.extend(_make_fractionnement_group(group_ids))

    # 6. Transactions normales (compléter jusqu'à 250)
    target = 250
    while len(rows) < target:
        rows.append(_make_normal(next_id()))

    # Mélanger pour éviter les patterns positionnels
    random.shuffle(rows)
    return rows


def main() -> None:
    rows = generate()

    # Vérification distribution
    scores = [r["expected_score"] for r in rows]
    n_total = len(rows)
    n_normal = scores.count("NORMAL")
    n_suspect = scores.count("SUSPECT")
    n_alerte = scores.count("ALERTE")

    fieldnames = ["tx_id", "amount", "supplier_id", "category", "timestamp", "description", "expected_score"]
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Golden set généré : {OUTPUT_PATH}")
    print(f"Total : {n_total} transactions")
    print(f"  NORMAL  : {n_normal} ({n_normal / n_total * 100:.1f}%)")
    print(f"  SUSPECT : {n_suspect} ({n_suspect / n_total * 100:.1f}%)")
    print(f"  ALERTE  : {n_alerte} ({n_alerte / n_total * 100:.1f}%)")


if __name__ == "__main__":
    main()
