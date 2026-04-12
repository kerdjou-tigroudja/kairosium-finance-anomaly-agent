# Déploiement Vertex AI Agent Engine (europe-west1)

## Méthode utilisée

**ADK CLI** : `adk deploy agent_engine` (pas Cloud Run).

Le répertoire passé au CLI est la **racine du dépôt** (`$(pwd)` du projet), et non `orchestrator/` seul, parce que le code importe `config`, `ingestion_agent`, `scoring_agent` et `shared` au même niveau que `orchestrator/`.

Le template Agent Engine généré par le CLI fait toujours `from .agent import <adk_app_object>`. Pour exposer l’`App` ADK (plugins BigQuery, etc.), on utilise `--adk_app_object app` et un fichier racine **`agent.py`** qui ré-exporte `app` depuis `orchestrator.app`.

## Pourquoi la racine du repo et non `orchestrator/` seul

Le CLI copie **uniquement** le dossier passé en argument. `orchestrator/agent.py` importe `config`, `ingestion_agent`, `scoring_agent`, `shared` : ces paquets sont au même niveau que `orchestrator/`, donc le déploiement doit partir de la **racine du projet** (`$(pwd)`).

Le template généré fait `from .agent import app`. Le fichier racine **`agent.py`** ré-exporte `app` depuis `orchestrator.app` et corrige **`sys.path`** : sans cela, le runtime Agent Engine levait `No module named 'orchestrator'` (voir logs Cloud Logging au premier déploiement).

## CLI `adk` — prérequis (sinon le correctif n’est jamais déployé)

La commande `adk` est fournie par le paquet **`google-adk`** installé dans l’environnement du projet. Si le shell répond **`adk: command not found`**, l’Agent Engine distant reste sur **l’ancienne** version du code (ex. sans `alert_transactions` dans `generate_audit_report`) → l’orchestrateur ne peut pas enchaîner les `trigger_alert` → **pas de points** `anomaly_alert` dans Cloud Monitoring → **pas d’incidents** → **Slack vide** (sous ~2–5 min après un run correct, les notifications apparaissent une fois les politiques branchées).

**Vérifier avant tout déploiement :**

```bash
cd kairosium-finance-anomaly-agent
source .venv/bin/activate   # ou : uv sync && source .venv/bin/activate
which adk                   # doit afficher .../kairosium-finance-anomaly-agent/.venv/bin/adk
adk --version
```

**Si vous n’utilisez pas `activate`**, appelez le CLI via le venv ou **uv** (même effet que `activate`) :

```bash
cd kairosium-finance-anomaly-agent
.venv/bin/adk --version
# ou
uv run adk --version
uv run adk deploy agent_engine "$(pwd)" \
  --project YOUR_GCP_PROJECT_ID \
  --region europe-west1 \
  --display_name "kairosium-finance-anomaly-agent" \
  --adk_app_object app \
  --trace_to_cloud
```

## Commande de déploiement

```bash
cd kairosium-finance-anomaly-agent
source .venv/bin/activate
which adk   # doit répondre avec le chemin .venv/bin/adk

adk deploy agent_engine "$(pwd)" \
  --project YOUR_GCP_PROJECT_ID \
  --region europe-west1 \
  --display_name "kairosium-finance-anomaly-agent" \
  --adk_app_object app \
  --trace_to_cloud
```

(Équivalent avec variable : remplacez `YOUR_GCP_PROJECT_ID` par `"${GOOGLE_CLOUD_PROJECT}"`.)

Après un déploiement réussi, relancer le golden set pour pousser les métriques et les notifications Slack :

```bash
uv run python scripts/verify_agent_engine_remote.py --prepare-gcs
```

Les variables d’environnement (hors `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` surchargées par les flags) sont lues depuis `.env` à la racine si présent.

Fichiers utiles : `requirements.txt` (racine), `.ae_ignore` (exclut `.venv`, `.git`, `.env` du bundle source).

## Ressource déployée (exemple de session)

Après un déploiement réussi, le CLI affiche une ligne du type :

`projects/1096821601497/locations/europe-west1/reasoningEngines/2422487998781194240`

La même valeur est enregistrée dans `deployment_metadata.json` (champ `remote_agent_engine_id`). Remplacez par votre ID si vous redéployez.

## Prérequis GCP

```bash
gcloud auth application-default login
gcloud config set project "$GOOGLE_CLOUD_PROJECT"
gcloud config set compute/region europe-west1

gcloud services enable \
  aiplatform.googleapis.com \
  monitoring.googleapis.com \
  bigquery.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com
```

## Coûts et suppression après démo

Agent Engine est facturé en **vCPU-heure** et **GiB-heure** lorsque l’instance sert du trafic (voir la grille tarifaire Vertex AI Agent Builder).

La commande `adk agent_engines delete` **n’existe pas** dans le CLI ADK actuel (`adk --help`). Utilisez le **SDK** ou le script du repo :

```bash
uv run python scripts/delete_reasoning_engine.py \
  "projects/PROJECT_ID/locations/europe-west1/reasoningEngines/ENGINE_ID"
```

Équivalent en Python :

```python
import vertexai

vertexai.init(project="PROJECT_ID", location="europe-west1")
client = vertexai.Client(project="PROJECT_ID", location="europe-west1")
client.agent_engines.delete(name="projects/PROJECT_ID/locations/europe-west1/reasoningEngines/ENGINE_ID")
```

Utilisez le **resource name** complet renvoyé après création.

## IAM BigQuery (rapports + analytics)

L’identité d’exécution distante est le **service agent Vertex AI Reasoning Engine** :

`service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com`

Sans rôle sur le dataset `agent_prod`, les insertions échouent (ex. `Permission bigquery.tables.updateData denied` sur `audit_reports`). Accordez au minimum **`roles/bigquery.dataEditor`** sur le dataset (ou tables concernées) à ce compte de service.

Exemple (à adapter si la commande alpha n’est pas disponible) :

```bash
PROJECT_NUMBER="$(gcloud projects describe PROJECT_ID --format='value(projectNumber)')"
gcloud alpha bq datasets add-iam-policy-binding agent_prod \
  --project=PROJECT_ID --location=europe-west1 \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"
```

## Vérifications post-déploiement

1. **Resource name** : sortie du CLI après `✅ Created agent engine: ...` ou `deployment_metadata.json`.
2. **Test query** : `scripts/verify_agent_engine_remote.py` — le client Vertex récupère l’engine avec `client.agent_engines.get(name=...)` puis **`async_stream_query(message=..., user_id=...)`** (l’API distante suit le contrat `AdkApp` ; `query(input=...)` n’est pas la signature utilisée ici).

   Exemple smoke test :

   ```bash
   export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/europe-west1/reasoningEngines/..."
   uv run python scripts/verify_agent_engine_remote.py --message "Réponds par OK."
   ```

   Pipeline complet (CSV sur GCS requis) :

   ```bash
   uv run python scripts/verify_agent_engine_remote.py --prepare-gcs
   ```

3. **BigQuery** : après correction IAM, vérifier `PROJECT.agent_prod.agent_events` et `PROJECT.agent_prod.audit_reports` (requêtes `COUNT(*)` / `ORDER BY timestamp DESC`).

## Alerting Cloud Monitoring → Slack

Les incidents et messages Slack sur `anomaly_alert` supposent que l’**Agent Engine exécute la dernière version du code** (réponse `generate_audit_report` avec `alert_transactions`, puis un `trigger_alert` par ALERTE). Si `adk` n’était pas dans le PATH et qu’aucun **`adk deploy`** n’a abouti, l’engine distant reste obsolète : pas (ou peu) de points Monitoring → **Slack vide**. Corriger d’abord la section **CLI `adk` — prérequis**, redéployer, puis `uv run python scripts/verify_agent_engine_remote.py --prepare-gcs` (délai typique **2–5 minutes** entre les points et les notifications).

Définitions déclaratives : `infra/monitoring_alert.yaml` (3 politiques : `anomaly_alert`, latence tool p95, latence workflow p95).

### Canal Slack (webhook) — console GCP

Si `gcloud alpha monitoring channels list` ne montre aucun canal (ex. après suppression d’un canal de test), **créez le canal dans la console** :

1. **Google Cloud Console** → **Monitoring** → **Alerting** → **Notification channels** (ou *Edit notification channels* selon l’UI).
2. **Webhooks** → **Add new** (ou **Add**).
3. Collez l’**URL Incoming Webhook** Slack (canal cible, ex. `#anomaly-alerts`), nommez le canal (ex. `Kairosium Slack Alerts`), enregistrez.
4. Dans la liste des canaux, ouvrez le détail et copiez l’**ID** ou le **nom de ressource** complet, du type  
   `projects/YOUR_GCP_PROJECT_ID/notificationChannels/12345678901234567890`.

**Alternative CLI** (si vous préférez tout en ligne de commande) :

```bash
gcloud alpha monitoring channels create \
  --project="${GOOGLE_CLOUD_PROJECT}" \
  --type=webhook_tokenauth \
  --display-name="Kairosium Slack Alerts" \
  --channel-labels=url="<URL_WEBHOOK_SLACK_INCOMING>"
```

### Ordre d’exécution (canal → dépendances → politiques)

À lancer depuis la racine `kairosium-finance-anomaly-agent/` :

```bash
# 1. Après création du webhook dans la console, exporter le canal :
export MONITORING_SLACK_CHANNEL="projects/YOUR_GCP_PROJECT_ID/notificationChannels/<ID_RÉEL>"

# 2. PyYAML (requis par apply_monitoring_policies_from_yaml.py), déjà dans pyproject.toml :
uv pip install pyyaml
# équivalent : uv sync  (installe toutes les deps du projet, dont pyyaml)
# pour pytest / ruff en local : uv sync --extra dev

# 3. Créer les 3 politiques d’alerte :
uv run python scripts/apply_monitoring_policies_from_yaml.py infra/monitoring_alert.yaml
```

Contrôle : `gcloud alpha monitoring channels list --project="${GOOGLE_CLOUD_PROJECT}"` doit lister au moins le webhook Slack ;  
`gcloud alpha monitoring policies list --project="${GOOGLE_CLOUD_PROJECT}" --filter='displayName:"Kairosium"'` liste les politiques créées.

### Métriques de latence (hors `trigger_alert`)

`trigger_alert` n’écrit que `custom.googleapis.com/agent/anomaly_alert`. Les p95 tool / workflow sont publiées par :

```bash
uv run python scripts/push_latency_p95_to_monitoring.py
```

À planifier en **Cloud Scheduler** (ex. horaire) avec le même compte de service / droits BigQuery + Monitoring. Alternative documentée dans la DESIGN_SPEC : scheduled query BigQuery + export (ex. Cloud Function qui appelle `create_time_series`), équivalent au script ci-dessus.

### Test pipeline golden set (Agent Engine)

```bash
export GOOGLE_CLOUD_PROJECT=YOUR_GCP_PROJECT_ID
export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/europe-west1/reasoningEngines/..."
uv run python scripts/verify_agent_engine_remote.py --prepare-gcs
```

Les appels `trigger_alert` dépendent du chemin LLM ; le golden set prévoit **20** transactions ALERTE — en exécution réelle le compteur peut varier légèrement (ex. 23) tant que l’orchestrateur enchaîne les alertes. Les notifications Slack sont émises par **Cloud Monitoring** lorsque la politique 1 se déclenche sur la métrique (pas directement depuis Slack).
