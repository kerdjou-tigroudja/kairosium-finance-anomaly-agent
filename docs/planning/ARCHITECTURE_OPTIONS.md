# Architecture Options - Finance Anomaly Agent

## Option 1 : Script Python Linéaire + LLM
- **Avantages** : Simple, déploiement Cloud Run natif.
- **Inconvénients** : Difficile à tracer finement étape par étape, peu résilient sur les erreurs d'extraction complexes.

## Option 2 : Pipeline Multi-Agent avec Google ADK (Choisie)
- **Avantages** : Séparation des préoccupations (Agent d'Ingestion vs Agent de Scoring). Observabilité Cloud Trace native via ADK. Parfaite compatibilité avec Vertex AI Reasoning Engine.
- **Inconvénients** : Complexité d'orchestration initiale.

**Décision :** Option 2. Le pipeline orchestré inclura des étapes asynchrones, permettant l'escalade vers un humain via Slack (Human-in-the-Loop conditionnel) et un traçage complet.
