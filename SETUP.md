# SETUP.md — Guide de mise en service NovaPay Anomaly Agent

**Projet :** kairosium-finance-anomaly-agent  
**Spec :** DESIGN_SPEC_v2.md  
**Temps estimé :** 15–30 min selon l'environnement GCP

---

## Table des matières

1. [Prérequis](#1-prérequis)
2. [Créer le fichier .env](#2-créer-le-fichier-env)
3. [Créer le dataset et les tables BigQuery](#3-créer-le-dataset-et-les-tables-bigquery)
4. [Vérifier l'alignement code ↔ tables](#4-vérifier-lalignement-code--tables)
5. [Lancer le playground local](#5-lancer-le-playground-local)
6. [Prochaines étapes](#6-prochaines-étapes)

---

## 1. Prérequis

| Outil | Vérification | Installation |
|---|---|---|
| Python ≥ 3.12 | `python --version` | [python.org](https://python.org) |
| uv | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| gcloud CLI | `gcloud --version` | [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install) |
| bq CLI | `bq version` | Inclus dans gcloud SDK |

> **Mode AI Studio seulement :** gcloud n'est pas requis. Seule la clé API AI Studio suffit.

---

## 2. Créer le fichier .env

Copier `.env.example` vers `.env` :

```bash
cp .env.example .env
```

### Mode A — Dev local avec AI Studio (recommandé pour démarrer)

Obtenir une clé gratuite sur [aistudio.google.com/apikey](https://aistudio.google.com/apikey), puis renseigner :

```dotenv
GOOGLE_API_KEY=<votre_clé_API_Google_AI_Studio>
GOOGLE_GENAI_USE_VERTEXAI=False
BQ_DATASET_ID=agent_prod
MODEL_ID=gemini-3-flash-preview
```

> Avec ce mode, `make playground` fonctionne immédiatement.  
> BigQuery et Cloud Monitoring ne sont **pas** disponibles (les tools les simulent en local).

### Mode B — Vertex AI + GCP (production)

#### 2.1 Authentification locale

```bash
gcloud auth application-default login
gcloud config set project VOTRE_PROJECT_ID
```

#### 2.2 Activer les APIs requises

```bash
gcloud services enable \
  bigquery.googleapis.com \
  monitoring.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  storage.googleapis.com
```

#### 2.3 Renseigner `.env`

```dotenv
GOOGLE_CLOUD_PROJECT=mon-projet-gcp      # ex: novapay-prod-123456
GOOGLE_CLOUD_LOCATION=europe-west1
GOOGLE_GENAI_USE_VERTEXAI=True
BQ_DATASET_ID=agent_prod
MODEL_ID=gemini-3-flash-preview
# GOOGLE_APPLICATION_CREDENTIALS=       # laisser vide si gcloud auth est utilisé
```

---

## 3. Créer le dataset et les tables BigQuery

> **Prérequis :** Mode B uniquement. Remplacer `$PROJECT_ID` par votre projet GCP.

```bash
export PROJECT_ID=$(gcloud config get-value project)
export DATASET_ID=agent_prod
export LOCATION=EU   # ou US selon votre préférence
```

### 3.1 Créer le dataset

```bash
bq mk \
  --dataset \
  --location=${LOCATION} \
  --description="NovaPay Anomaly Agent — traces et rapports d'audit" \
  ${PROJECT_ID}:${DATASET_ID}
```

Vérification :

```bash
bq ls --datasets ${PROJECT_ID}
# → agent_prod doit apparaître
```

### 3.2 Table `agent_events` (BigQuery Agent Analytics Plugin)

Le plugin la crée automatiquement au premier lancement. Pour la pré-créer avec partitionnement optimal :

```bash
bq query --use_legacy_sql=false --project_id=${PROJECT_ID} "
CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET_ID}.agent_events\`
(
  timestamp   TIMESTAMP NOT NULL OPTIONS(description='UTC time of event'),
  event_type  STRING    OPTIONS(description='LLM_REQUEST, LLM_RESPONSE, TOOL_STARTING, TOOL_COMPLETED, AGENT_STARTING, etc.'),
  agent       STRING    OPTIONS(description='Nom de l agent ADK (finance_anomaly_orchestrator, ingestion_agent, scoring_agent)'),
  session_id  STRING    OPTIONS(description='Identifiant de session conversation'),
  invocation_id STRING  OPTIONS(description='Identifiant unique de l invocation'),
  user_id     STRING    OPTIONS(description='Identifiant utilisateur'),
  trace_id    STRING    OPTIONS(description='OpenTelemetry trace ID'),
  span_id     STRING    OPTIONS(description='OpenTelemetry span ID'),
  parent_span_id STRING OPTIONS(description='OpenTelemetry parent span ID'),
  content     JSON      OPTIONS(description='Payload de l evenement (polymorphe selon event_type)'),
  content_parts ARRAY<STRUCT<
    text          STRING,
    part_index    INT64,
    part_attributes STRING,
    storage_mode  STRING
  >>             OPTIONS(description='Contenu multimodal ou offloadé vers GCS'),
  attributes  JSON      OPTIONS(description='Métadonnées : model, usage_metadata, session_metadata, custom_tags'),
  latency_ms  JSON      OPTIONS(description='total_ms, time_to_first_token_ms'),
  status      STRING    OPTIONS(description='OK ou ERROR'),
  error_message STRING  OPTIONS(description='Message d erreur si status=ERROR'),
  is_truncated BOOLEAN  OPTIONS(description='True si le contenu a été tronqué')
)
PARTITION BY DATE(timestamp)
CLUSTER BY event_type, agent, user_id;
"
```

### 3.3 Table `audit_reports`

Schéma conforme à DESIGN_SPEC §4 :

```bash
bq query --use_legacy_sql=false --project_id=${PROJECT_ID} "
CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET_ID}.audit_reports\`
(
  report_id          STRING    NOT NULL OPTIONS(description='UUID du rapport'),
  timestamp          TIMESTAMP NOT NULL OPTIONS(description='Horodatage UTC de génération'),
  total_transactions INT64              OPTIONS(description='Nombre total de transactions analysées'),
  normal_count       INT64              OPTIONS(description='Transactions NORMAL'),
  suspect_count      INT64              OPTIONS(description='Transactions SUSPECT'),
  alert_count        INT64              OPTIONS(description='Transactions ALERTE'),
  transactions       ARRAY<STRUCT<
    tx_id    STRING,
    score    STRING,
    motifs   ARRAY<STRING>,
    trace_id STRING
  >>                           OPTIONS(description='Détail par transaction avec motifs explicites (AI Act Art. 13)')
)
PARTITION BY DATE(timestamp)
CLUSTER BY timestamp;
"
```

### 3.4 Table `test_runs`

Résultats CI pytest → BigQuery (DESIGN_SPEC §4) :

```bash
bq query --use_legacy_sql=false --project_id=${PROJECT_ID} "
CREATE TABLE IF NOT EXISTS \`${PROJECT_ID}.${DATASET_ID}.test_runs\`
(
  run_id      STRING    OPTIONS(description='UUID de l exécution'),
  test_id     STRING    OPTIONS(description='Identifiant du test pytest'),
  status      STRING    OPTIONS(description='passed, failed, error, skipped'),
  duration_ms INT64     OPTIONS(description='Durée du test en millisecondes'),
  branch      STRING    OPTIONS(description='Branche git'),
  timestamp   TIMESTAMP OPTIONS(description='Horodatage UTC')
)
PARTITION BY DATE(timestamp);
"
```

### 3.5 Vérifier les 3 tables

```bash
bq ls --tables ${PROJECT_ID}:${DATASET_ID}
# Doit afficher : agent_events   audit_reports   test_runs
```

### 3.6 Rôles IAM requis pour le compte de service

```bash
# Remplacer SERVICE_ACCOUNT par votre SA (ex: agent@mon-projet.iam.gserviceaccount.com)
export SA=votre-sa@${PROJECT_ID}.iam.gserviceaccount.com

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA}" \
  --role="roles/bigquery.jobUser"

bq add-iam-policy-binding \
  --member="serviceAccount:${SA}" \
  --role="roles/bigquery.dataEditor" \
  ${PROJECT_ID}:${DATASET_ID}.audit_reports

bq add-iam-policy-binding \
  --member="serviceAccount:${SA}" \
  --role="roles/bigquery.dataEditor" \
  ${PROJECT_ID}:${DATASET_ID}.agent_events
```

---

## 4. Vérifier l'alignement code ↔ tables

| Table BQ créée | Référence dans le code | Variable d'env |
|---|---|---|
| `agent_events` | `orchestrator/app.py` → `table_id="agent_events"` | — (hardcodé) |
| `audit_reports` | `orchestrator/tools/report.py` → `f"{project_id}.{dataset_id}.audit_reports"` | `BQ_DATASET_ID` |
| `test_runs` | Non implémenté — export JUnit XML manuel (voir §6) | — |

> **Note DESIGN_SPEC vs code :** La spec mentionne une table `agent_traces`. Dans l'implémentation,
> cette table est remplacée par `agent_events` (schéma plus riche de BigQueryAgentAnalyticsPlugin).
> Les scheduled queries de la spec ciblant `agent_traces` doivent être adaptées vers `agent_events`.

### Adapter les scheduled queries (DESIGN_SPEC §6)

Latence p95 par agent (remplace `agent_prod.agent_traces` → `agent_events`) :

```sql
SELECT
  CURRENT_TIMESTAMP() AS measured_at,
  agent,
  APPROX_QUANTILES(CAST(JSON_VALUE(latency_ms, '$.total_ms') AS INT64), 100)[OFFSET(95)]
    AS latency_p95_ms
FROM `${PROJECT_ID}.${DATASET_ID}.agent_events`
WHERE event_type = 'TOOL_COMPLETED'
  AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
GROUP BY agent;
```

---

## 5. Lancer le playground local

```bash
cd kairosium-finance-anomaly-agent

# Charger les variables d'env
source .env   # ou: export $(cat .env | grep -v '^#' | xargs)

# Lancer le playground interactif
make playground
# → adk web .
# → Ouvre http://localhost:8000
```

Message d'invite à tester dans le playground :

```
Analyse les transactions du fichier data/golden_set.csv et génère le rapport d'audit.
```

---

## 6. Prochaines étapes

### 6.1 Évaluation ADK

```bash
cd kairosium-finance-anomaly-agent
make eval   # adk eval orchestrator/ eval/evalset.json
```

### 6.2 Tests + export résultats vers BigQuery

```bash
make test
# → pytest --junitxml=results.xml tests/
# → results.xml contient les résultats JUnit

# Importer results.xml dans BigQuery test_runs (script à créer) :
# uv run python scripts/import_test_results.py results.xml
```

### 6.3 Déploiement

> **BLOQUÉ — approbation humaine explicite requise** (DESIGN_SPEC §7.5, CLAUDE.md).  
> Lire `/adk-deploy-guide` avant de procéder.

```bash
make deploy
# → Affiche un message de blocage et exit 1
```

Quand l'approbation est obtenue, les étapes de déploiement sont :

1. Lire le skill `/adk-deploy-guide`
2. Choisir la cible : Vertex AI Agent Engine (recommandé par DESIGN_SPEC) ou Cloud Run
3. Utiliser `uvx agent-starter-pack enhance . --deployment-target agent_engine`
4. Configurer CI/CD Cloud Build
5. Déployer uniquement après validation du KPI accuracy ≥ 85% sur golden set
