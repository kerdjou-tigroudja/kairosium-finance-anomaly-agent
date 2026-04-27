# ADR-009 — Framework Google ADK (Agent Development Kit)

## Statut

Accepté

## Contexte

Concevoir un **pipeline multi-étapes** (ingestion, scoring, génération de rapports, alertes) en s’appuyant sur le LLM et des outils cloud implique de choisir : bibliothèques ad hoc, orchestration maison, ou un **framework agent** intégré à l’écosystème cible.

## Décision

Le projet repose sur **Google ADK** comme framework d’orchestration des agents, des **transfers** entre agents et l’enregistrement d’**outils** (tools) typés.

## Justification

- **Intégration GCP « plug & play »** : chemins de déploiement documentés vers **Vertex AI Agent Engine**, conventions de structuration d’app (`--adk_app_object`) et de bundle.
- **Observabilité** : prise en charge de **Cloud Trace** et, via le **plugin BigQuery Agent Analytics**, export structuré des événements vers BigQuery pour l’analyse des runs et le suivi de coût.
- Cohérence avec **Vertex AI** (sessions, authentification unifiée côté runtime) plutôt qu’une couche d’abstraction non maintenue par le fournisseur.

## Conséquences

- Les évolutions (nouveaux sous-agents, outils) suivent le modèle **ADK** (agents, outils, orchestrateur) plutôt qu’une file HTTP maison.
- Le verrou technologique principal côté framework est l’alignement sur les **releases ADK** et l’**API publique** documentée.
