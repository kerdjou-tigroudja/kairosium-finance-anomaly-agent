# ADR-008 — Exclusion du MCP (Model Context Protocol) sur ce pilote

## Statut

Accepté

## Contexte

**MCP** sert typiquement à brancher un agent sur des **outils hébergés ailleurs** (serveur MCP, schéma d’auth et de transport dédiés), en complément ou à la place d’outils intégrés à l’application.

## Décision

**MCP n’est pas utilisé** : pas de serveur MCP, pas d’`McpToolset` dans l’arbre applicatif de ce projet.

## Raisons

- L’agent n’interagit qu’avec des **services natifs GCP** : **Cloud Storage**, **BigQuery**, **Cloud Monitoring** (et alertes **Slack** via **webhook HTTP** dans l’outil applicatif) — le tout couvert par les **outils / clients ADK** habituels.
- Aucun **SaaS** ou **base de données externe** au périmètre ne **requiert** aujourd’hui le protocole MCP pour l’exposition d’outils côté serveur.
- Éviter MCP **réduit** la surface opérationnelle (authentification supplémentaire, disponibilité d’un autre point de terminaison réseau, supervision).

## Conséquences

- Toute intégration d’**outils externes** non couverte par le périmètre actuel repose sur une **révision d’architecture** (nouvel ADR) avant d’envisager MCP.
- Le flux **Slack** reste un appel **HTTP** depuis `trigger_alert`, en dehors de MCP (voir `orchestrator/tools/alert.py`).
