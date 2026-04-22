# Kairosium — Finance Anomaly Agent (ADK)

Pipeline multi-agents NovaPay : ingestion CSV, scoring, rapport d’audit, alertes.

## KPIs mesurés (T2)

Données issues du golden set et des runs instrumentés (dev Étape 4bis vs **production** Agent Engine).

| Métrique | Cible T2 | Dev (4bis) | Production | Verdict |
|:--|:--|:--|:--|:--|
| **Accuracy** | ≥ 85 % | 90 % | 90 % | ✅ |
| **Precision ALERTE** | — | 100 % | 100 % | ✅ |
| **Recall ALERTE** | — | 100 % | 100 % | ✅ |
| **Latence p95 tool call** | ≤ 3 000 ms | 637 ms | 455 ms | ✅ |
| **Alertes Cloud Monitoring** | 20 / 20 | 20 / 20 | 23 / 23 | ✅ |
| **Alertes Slack** | — | N/A | 23 messages | ✅ |
| **Tokens / run** | — | N/A | ~16 000 (~0,05 USD) | ✅ |
| **Modèle** | gemini-2.5-flash | gemini-2.0-flash | gemini-2.5-flash | ✅ |

**Note :** Precision / Recall sont mesurés sur le golden set aligné avec les règles déterministes du scorer (**250** transactions, **23** ALERTE). Le golden set initial présentait un désalignement avec les règles — corrigé avant signature de la baseline.

## Modèle LLM

- **Production :** `gemini-2.5-flash` (Vertex AI Gemini API), configuré via `config/agent_config.json` et surcharge possible par la variable d’environnement `MODEL_ID`.
- **Migration :** passage **`gemini-2.0-flash` → `gemini-2.5-flash`** aligné sur l’arrêt annoncé de **Gemini 2.0 Flash** (**1er juin 2026**). Ne pas réintroduire `gemini-2.0-flash` dans la config de production après cette date.
- **Authentification :** **Vertex AI avec ADC** (`gcloud auth application-default login`, `GOOGLE_GENAI_USE_VERTEXAI=true`) — **pas** de clé API Google AI Studio en mode production.

## Déploiement production

- **Méthode :** **Vertex AI Agent Engine**, région **`europe-west1`** (décision **ADR-007**).
- **Guide détaillé :** [`DEPLOY_AGENT_ENGINE.md`](DEPLOY_AGENT_ENGINE.md) (CLI `adk`, IAM BigQuery, vérification distante).

**Commande de déploiement (exemple) :**

```bash
cd kairosium-finance-anomaly-agent
uv run adk deploy agent_engine "$(pwd)" \
  --project "${GOOGLE_CLOUD_PROJECT}" \
  --region europe-west1 \
  --display_name "kairosium-finance-anomaly-agent" \
  --adk_app_object app \
  --trace_to_cloud
```

(Remplacez `--project` / `--display_name` selon votre environnement.)

**Suppression d’un Reasoning Engine :**

```bash
uv run python scripts/delete_reasoning_engine.py \
  "projects/PROJECT_ID/locations/europe-west1/reasoningEngines/ENGINE_ID"
```

## Cost tracking

**Architecture observée en production :** labels Vertex AI (`GenerateContentConfig.labels`, via `shared/vertex_billing_labels.py`) → agrégation consommation depuis **`agent_events`** (plugin BigQuery Agent Analytics) → table matérialisée **`cost_tracking`** via la requête [`infra/cost_tracking.sql`](infra/cost_tracking.sql). **Fallback :** la vue **`v_llm_response`** n’était pas disponible telle quelle en prod ; le chemin retenu s’appuie sur les événements / agrégations documentés dans le SQL (voir commentaires `agent_events` dans le même fichier).

**Mesure (golden set run) :** ~**16 000** tokens, **< 0,05 USD** (ordre de grandeur cohérent avec l’estimation documentée dans `cost_tracking.sql`).

**Exemple de requête (adapter `PROJECT` / dataset) :**

```sql
SELECT *
FROM `PROJECT.agent_prod.cost_tracking`
ORDER BY window_start DESC
LIMIT 10;
```

Si la table a été créée avec le script versionné `infra/cost_tracking.sql`, les colonnes incluent notamment **`run_date`** (agrégat par jour) et il n’y a pas de colonne `window_start` : utiliser par exemple `ORDER BY run_date DESC`.

## Alertes Slack

Notifications **Slack** via **webhook HTTP** directement dans l’outil **`trigger_alert`** (`orchestrator/tools/alert.py`, variable `SLACK_WEBHOOK_URL`) — **pas** d’intégration Slack nativement pilotée par Cloud Monitoring pour ce flux (les politiques Monitoring restent sur les métriques `anomaly_alert` / latences).

## Décisions d’architecture (ADRs)

| ADR | Sujet | Fichier |
|:--|:--|:--|
| **ADR-005** | CI Cloud Build (différable / trigger) | [`docs/adr/ADR-005.md`](docs/adr/ADR-005.md) |
| **ADR-006** | Firestore exclu pour ce pilote (config fichier) | [`docs/adr/ADR-006-firestore-exclusion.md`](docs/adr/ADR-006-firestore-exclusion.md) |
| **ADR-007** | Agent Engine (`europe-west1`) vs Cloud Run Grille T2 | [`docs/adr/ADR-007-agent-engine-vs-cloud-run.md`](docs/adr/ADR-007-agent-engine-vs-cloud-run.md) |
| **ADR-008** | MCP exclu (tools GCP natifs uniquement) | [`docs/adr/ADR-008-mcp-exclu.md`](docs/adr/ADR-008-mcp-exclu.md) |

## CI (Cloud Build)

Fichier [`cloudbuild.yaml`](cloudbuild.yaml) : exécution du golden set (`pytest tests/test_agent.py::test_accuracy_golden_set`). Configuration CI définie (**ADR-005**). Pour activer la CI bloquante sur le projet GCP, utiliser la commande `gcloud builds triggers create` (voir livrables).
