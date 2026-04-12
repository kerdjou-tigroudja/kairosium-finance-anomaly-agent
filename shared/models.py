"""Modèles Pydantic partagés entre les 3 agents NovaPay."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Transaction(BaseModel):
    """Transaction financière normalisée (note de frais ou virement fournisseur)."""

    tx_id: str = Field(description="Identifiant unique de la transaction")
    amount: float = Field(description="Montant en EUR")
    supplier_id: str = Field(description="Identifiant du fournisseur ou employé")
    category: str = Field(description="Catégorie de dépense (ex: TRAVEL, IT, OFFICE)")
    timestamp: datetime = Field(description="Horodatage UTC de la transaction")
    description: str = Field(description="Libellé ou description de la transaction")


class ScoredTransaction(BaseModel):
    """Transaction avec score d'anomalie et motifs explicites (AI Act Art. 13)."""

    tx_id: str
    amount: float
    supplier_id: str
    category: str
    timestamp: datetime
    description: str
    score: Literal["NORMAL", "SUSPECT", "ALERTE"] = Field(
        description="Score d'anomalie déterministe"
    )
    motifs: list[str] = Field(
        default_factory=list,
        description="Règles déclenchées (auditables, non boîte noire)",
    )
    trace_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Trace ID pour corrélation BigQuery Agent Analytics",
    )

    @classmethod
    def from_transaction(
        cls,
        tx: Transaction,
        score: Literal["NORMAL", "SUSPECT", "ALERTE"],
        motifs: list[str],
        trace_id: str | None = None,
    ) -> ScoredTransaction:
        return cls(
            tx_id=tx.tx_id,
            amount=tx.amount,
            supplier_id=tx.supplier_id,
            category=tx.category,
            timestamp=tx.timestamp,
            description=tx.description,
            score=score,
            motifs=motifs,
            trace_id=trace_id or str(uuid.uuid4()),
        )


class AuditReport(BaseModel):
    """Rapport d'audit écrit dans BigQuery table audit_reports."""

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_transactions: int
    normal_count: int
    suspect_count: int
    alert_count: int
    transactions: list[ScoredTransaction]


class AgentConfig(BaseModel):
    """Configuration des agents — miroir du document Firestore config/agent_config."""

    model_id: str = Field(
        ...,
        description="Identifiant modèle Model Garden / Vertex — obligatoire (Firestore ou agent_config.json).",
    )
    model_id_overrides: dict = Field(
        default_factory=lambda: {"ingestion_agent": None, "scoring_agent": None}
    )
    dataset_id: str = "agent_prod"
    baseline_multiplier: float = 3.0
    suspect_hours_start: int = 2
    suspect_hours_end: int = 4
    fractionnement_window_hours: int = 48
    validation_threshold: float = 500.0
    fractionnement_min_count: int = 3
    supplier_registry: list[str] = Field(
        default_factory=lambda: [f"SUP_{i:03d}" for i in range(1, 51)]
    )

    def get_model_id(self, agent_name: str | None = None) -> str:
        """Retourne le model_id effectif pour un agent (override ou global)."""
        if agent_name and self.model_id_overrides.get(agent_name):
            return self.model_id_overrides[agent_name]
        return self.model_id
