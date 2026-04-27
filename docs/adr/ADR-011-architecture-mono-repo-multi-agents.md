# ADR-011 — Mono-repo, multi-agents (orchestrateur ADK) plutôt que microservices HTTP

## Statut

Accepté

## Contexte

Un pipeline d’anomalies « ingestion → score → rapport → alertes » peut être **déployé** soit comme **plusieurs services** (ex. un **Cloud Run** par brique, communication HTTP, auth entre services), soit comme **un seul déploiement agent** contenant des **sous-agents** avec **transferts** internes (pattern ADK).

## Décision

Architecture **mono-repo** : code des **rôles** (ingestion, scoring, orchestration) dans un seul arbre, **déploiement unique** sur **Agent Engine** avec un **orchestrateur** qui appelle des **transfers** vers des agents spécialisés.

## Justification

- **Overhead HTTP** : évite la latence, la sérialisation inter-service et le risque d’enveloppes API redondantes pour chaque enchaînement d’outils.
- **IAM** : moins d’**identités de service** et de politiques de confiance inter-services qu’avec trois ou quatre backends distincts derrière des load balancers.
- **Traçabilité** : le traçage cross-agents et les enregistrements côté runtime ADK restent **circonscrits** à la même unité d’exécution, au lieu d’un **tracing distribué** lourd (propagation d’en-têtes, corrélation multi-processus) pour un enchaînement fréquent et court.
- **Modularité** : la **séparation logique** (fichiers par agent, outils, prompts) est conservée ; le découpage physique en N microservices n’apporte **pas** de bénéfice clair **à ce niveau d’encombrement** du projet.

## Conséquences

- L’**auto-scaling** et l’isolation s’appliquent au **runtime Agent Engine** dans son ensemble, pas finement par brique.
- Un futur **éclatement** en services séparés serait justifié par de la **charge hétérogène** très forte, des **SLA** différents par brique, ou des **contraintes réseau** (périmètres de confiance) — à redocumenter.
