# ADR-007 — API production : Vertex AI Agent Engine plutôt que Cloud Run

## Statut

Accepté (déploiement réel du pilote)

## Contexte

La Grille de services T2 mentionne historiquement une exposition **Cloud Run**. Le pipeline NovaPay est déployé avec **`adk deploy agent_engine`** sur **Vertex AI Agent Engine** (région **`europe-west1`**), ce qui expose l’agent via l’API managée Agent Engine / Reasoning Engine, et non via un service Cloud Run versionné dans ce dépôt.

## Décision

- **Méthode retenue :** Vertex AI **Agent Engine**, région **`europe-west1`**.
- **Motif :** alignement avec le flux officiel ADK pour ce cas d’usage (bundle source, `--adk_app_object app`, traces Cloud, sessions managées).
- **Cloud Run :** non utilisé comme façade HTTP dans ce pilote ; une future façade Cloud Run reste optionnelle si un contrat client impose explicitement ce pattern.

## Conséquences

- La documentation opérationnelle et le **README** décrivent **Agent Engine** comme vérité de déploiement.
- Les intégrations client type ERP fictif passent par le **client Vertex** (ex. `async_stream_query`), pas par une URL Cloud Run du repo.

## Références

- `kairosium-finance-anomaly-agent/DEPLOY_AGENT_ENGINE.md`
- `DESIGN_SPEC_v2_3.md` §2 (hébergement / API)
