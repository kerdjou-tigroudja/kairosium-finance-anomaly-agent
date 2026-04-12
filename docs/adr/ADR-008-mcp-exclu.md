# ADR-008 — Exclusion MCP (Model Context Protocol) sur ce pilote

## Statut

Accepté

## Contexte

La Grille T2 cite **MCP** comme intégration possible agents ↔ outils externes. Le code du pilote NovaPay s’appuie sur des **tools ADK natifs** (Cloud Storage, BigQuery, Cloud Monitoring) sans serveur MCP ni `McpToolset`.

## Décision

**MCP est exclu** du périmètre de ce cas d’étude : pas de serveur MCP, pas d’`McpToolset` dans l’arbre applicatif du projet.

## Raison

- Périmètre **mono-domaine** et outillage déjà couvert par les clients GCP officiels.
- Réduction de la surface opérationnelle (MCP = session réseau, auth, disponibilité serveur).

## Conséquences

- Toute intégration outil externe non GCP devra repasser par une **révision d’architecture** (nouvel ADR) avant ajout de MCP.
- Les alertes **Slack** reposent sur un **webhook HTTP** dans `trigger_alert`, hors protocole MCP.

## Références

- `KAIROSIUM_GRILLE_v2_3.md` (livrables T2)
- `orchestrator/tools/alert.py`
