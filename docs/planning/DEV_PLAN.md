# Development Plan - Finance Anomaly Agent

## Phase 1 : Ingestion et Tools
- [x] Configuration du parsage CSV.
- [x] Implémentation du système de Scoring asynchrone.
- [x] Tests unitaires sur le set de données Golden.

## Phase 2 : Orchestration Multi-Agent
- [x] Orchestrateur global connectant l'ingestion au rapport final.
- [x] Intégration Slack Tool pour alertes.
- [x] Intégration BigQuery pour traces.

## Phase 3 : Télémétrie et Déploiement
- [x] Validation de Cloud Trace.
- [x] Déploiement sur Vertex AI Agent Engine.
- [ ] Vérification du smoke test en environnement public (Actuellement en statut d'erreur GCP d'authentification).
