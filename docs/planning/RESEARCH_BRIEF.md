# Research Brief - Finance Anomaly Agent

**Positionnement :** Multi-agent pipeline pour la détection d'anomalies financières sur GCP.

## Problème Métier
Une PME SaaS consacre 2 ETP/semaine à la revue manuelle des flux de paiement, sans parvenir à détecter systématiquement la fraude complexe. L'objectif est d'automatiser le processus d'examen via un pipeline agentique combinant règles déterministes et analyse LLM asynchrone, tout en respectant l'AI Act (supervision humaine sur exception).

## Périmètre
- Ingestion de fichiers CSV de transactions
- Notation (Scoring) des fraudes ou anomalies
- Signalement en temps réel (Slack)
- Audit asynchrone et archivage (BigQuery)

## Facteurs de Succès
- Précision sur les alertes de fraude : 100% (zéro faux positif critique pour bloquer).
- Exactitude globale de la classification > 85%.
- Coût par exécution très faible (< 0.10 $).
