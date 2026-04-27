# ADR-007 — API production : Vertex AI Agent Engine plutôt que Cloud Run

## Statut

Accepté (déploiement du pilote en production)

## Contexte

Deux modèles courants pour exposer une charge « agent + outils » sur GCP : un **service HTTP** (ex. **Cloud Run**) entièrement maîtrisé par l’équipe, et l’**hébergement managé** proposé par l’**Agent Engine** d’ADK (API Vertex, bundle applicatif, sessions).

## Décision

- **Méthode retenue :** **Vertex AI Agent Engine**, région **`europe-west1`**.
- **Motifs :** c’est l’**hébergement natif** pour le flux `adk deploy` / bundle d’app ; il fournit des **sessions managées**, l’**intégration des traces** côté cloud et la stack attendue par le runtime ADK **sans** implémenter soi-même l’orchestration HTTP, la gestion d’identité des appels Vertex et le cycle de vie du conteneur.
- **Cloud Run** n’est **pas** utilisé comme **façade HTTP** de ce dépôt dans ce pilote, car **aucun besoin** d’**API REST custom**, de middleware propriétaire ni de **microservice** intermédiaire. Une future façade Cloud Run reste **optionnelle** si un contrat d’intégration impose explicitement ce pattern (BFF, réseau privé, forme d’URL fixe, etc.).

## Conséquences

- La documentation opérationnelle et le **README** décrivent **Agent Engine** comme vérité de déploiement.
- Les intégrations côté client s’appuient sur le **client Vertex** (ex. requêtes asynchrones vers l’engine), pas sur une URL Cloud Run déclarée par ce repository.

## Références

- `kairosium-finance-anomaly-agent/DEPLOY_AGENT_ENGINE.md`
