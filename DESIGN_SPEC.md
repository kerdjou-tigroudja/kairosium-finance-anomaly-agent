# DESIGN_SPEC — Kairosium Finance Anomaly Agent

**Repo :** `kairosium-finance-anomaly-agent`
**Cas d'étude :** détection d'anomalies financières NovaPay
**Statut :** implémenté en production (16/16 tests, accuracy 90 %, déployé sur Vertex AI Agent Engine `europe-west1`)
**Document contrat — rétroactif :** décrit le système tel qu'il existe dans le code.

---

## 1 — Contexte métier

NovaPay (PME SaaS, ~150 fournisseurs récurrents, ~1 000 transactions / mois) mobilisait **2 ETP par semaine** pour la revue manuelle des notes de frais et virements fournisseurs. Conséquences mesurées :

- coût opérationnel direct : ~8 k€ / mois sur la fonction Finance,
- fraudes détectées **a posteriori** (montants hors baseline, fractionnements, fournisseurs hors référentiel),
- traçabilité incomplète des décisions de blocage / paiement (audit interne K1 2024).

Le pipeline ADK remplace cette revue manuelle par une analyse **déterministe + LLM asynchrone** : ingestion CSV, scoring sur 5 règles auditables, rapport d'audit BigQuery, alertes temps réel Cloud Monitoring + Slack. Objectif : passer la revue de 2 ETP/semaine à une supervision humaine par exception (transactions ALERTE uniquement — AI Act Art. 14).

---

## 2 — Objectif et périmètre

### Dans le périmètre

- Pipeline multi-agents ADK (1 orchestrateur + 2 sous-agents) déployé sur **Vertex AI Agent Engine**, région `europe-west1`.
- Ingestion CSV depuis Cloud Storage (`gs://`) ou chemin local (Dev UI playground).
- Scoring par 5 règles déterministes (cf. 5) — pas de jugement LLM sur le score.
- Rapport d'audit persisté dans BigQuery (`audit_reports`).
- Alertes Cloud Monitoring (`custom.googleapis.com/agent/anomaly_alert`) + notifications Slack (webhook).
- Observabilité distribuée via `BigQueryAgentAnalyticsPlugin` (table `agent_events`).

### Hors périmètre

- Blocage automatique de paiement (interdit — AI Act Art. 14, supervision humaine requise).
- Apprentissage en ligne / fine-tuning du scoring (les règles sont versionnées dans `config/agent_config.json`).
- Connecteurs ERP / banque temps réel (consommation CSV uniquement, batch).

### Contraintes réglementaires

- **AI Act Art. 13 (transparence)** — chaque ScoredTransaction porte un champ `motifs: list[str]` exposant la / les règle(s) déclenchée(s) : pas de boîte noire.
- **AI Act Art. 14 (supervision humaine)** — `trigger_alert` notifie, ne bloque pas. La doc et le prompt orchestrateur le rappellent explicitement.
- **Authentification ADC** — pas de clé API Google AI Studio en production (cf. 9).

---

## 3 — Architecture

### 3.1 — Agents et rôles

| Agent ADK | Type | Modèle | Tools | Rôle |
|---|---|---|---|---|
| `finance_anomaly_orchestrator` | `Agent` (root) | `gemini-2.5-flash` | `generate_audit_report`, `trigger_alert` | Orchestre les délégations, agrège, déclenche les alertes |
| `ingestion_agent` | `Agent` (sub) | `gemini-2.5-flash` | `ingest_transactions` | Parse CSV, valide schéma, sérialise dans le state |
| `scoring_agent` | `Agent` (sub) | `gemini-2.5-flash` | `score_all_transactions` | Applique les 5 règles déterministes, sérialise dans le state |

Les sous-agents sont déclarés dans `root_agent.sub_agents=[ingestion_agent, scoring_agent]`. La délégation se fait via le builtin ADK `transfer_to_agent` (handoff piloté par l'instruction de chaque agent — pas de `SequentialAgent` ni `ParallelAgent`).

### 3.2 — Communication inter-agents

État partagé dans `tool_context.state` (préfixe `temp:` = scope session, jamais persisté sur disque) :

| State key | Producteur | Consommateur | Contenu |
|---|---|---|---|
| `temp:transactions` | `ingest_transactions` | `score_all_transactions` | JSON `list[Transaction]` (pydantic `model_dump`) |
| `temp:scored_transactions` | `score_all_transactions` | `generate_audit_report` | JSON `list[ScoredTransaction]` |
| `temp:audit_report` | `generate_audit_report` | (audit / debug) | JSON `AuditReport` complet |
| `temp:alert_transactions` | `generate_audit_report` | (audit / debug) | JSON liste filtrée score == ALERTE |
| `playground_csv_path` | callback `persist_playground_csv_before_model` | `ingest_transactions` | Chemin absolu `/tmp/adk_playground_*.csv` (Dev UI uniquement) |
| `pipeline_run_id` | callback `vertex_billing_before_model` | labels Vertex billing | UUID4 partagé entre les 3 agents pour un run |

### 3.3 — Flux d'exécution séquentiel

1. **Réception requête** — l'utilisateur fournit un `gcs_path` (ou joint un CSV inline dans le Dev UI). Le callback `persist_playground_csv_before_model` matérialise le CSV inline en `/tmp` et remplit `playground_csv_path`.
2. **Délégation ingestion** — l'orchestrateur appelle `transfer_to_agent('ingestion_agent')` ; `ingest_transactions(gcs_path)` lit le CSV (Cloud Storage ou local), valide les colonnes obligatoires (`tx_id`, `amount`, `supplier_id`, `category`, `timestamp`, `description`), parse en `list[Transaction]`, écrit `temp:transactions`.
3. **Délégation scoring** — `ingestion_agent` appelle `transfer_to_agent('scoring_agent')` ; `score_all_transactions()` lit `temp:transactions`, applique les 5 règles (5), écrit `temp:scored_transactions`. Retourne au scoring agent les compteurs NORMAL / SUSPECT / ALERTE.
4. **Retour orchestrateur** — `scoring_agent` appelle `transfer_to_agent('finance_anomaly_orchestrator')`. L'orchestrateur appelle `generate_audit_report` (sans paramètre) qui agrège, écrit la ligne dans BigQuery `audit_reports`, et **renvoie** la liste `alert_transactions` (déjà filtrée score == ALERTE, motifs joints par `;`).
5. **Émission alertes** — pour **chaque** entrée de `alert_transactions`, l'orchestrateur appelle **une seule fois** `trigger_alert(tx_id, motifs, amount)` qui crée une `TimeSeries` Cloud Monitoring avec un `invocation_id` unique (anti-collision GAUGE) et POST vers Slack si `SLACK_WEBHOOK_URL` est défini. Le pipeline ne re-tente jamais une alerte échouée (logguée dans `agent_events`, non bloquant).

---

## 4 — Schémas BigQuery

Dataset cible : `agent_prod` (configurable via `BQ_DATASET_ID`).

### `audit_reports` (écrit par `generate_audit_report`)

| Colonne | Type | Notes |
|---|---|---|
| `report_id` | STRING | UUID4 généré côté Python |
| `timestamp` | TIMESTAMP | ISO 8601 UTC |
| `total_transactions` | INTEGER | |
| `normal_count` / `suspect_count` / `alert_count` | INTEGER | |
| `transactions` | ARRAY&lt;STRUCT&gt; | `tx_id` STRING, `score` STRING, `motifs` ARRAY&lt;STRING&gt;, `trace_id` STRING |

### `agent_events` (géré automatiquement par `BigQueryAgentAnalyticsPlugin`)

Schéma auto-créé par le plugin (`auto_schema_upgrade=True`, `create_views=True`). Contient un événement par invocation LLM / tool call avec `session_id`, `agent`, `event_type`, `usage_total_tokens`, `trace_id`, `span_id`, payload sérialisé. Source de vérité pour le KPI Cost/run et les latences p95.

Une ligne `event_type='alert_monitoring_error'` est insérée par `_log_alert_failure_to_bigquery` lorsqu'un `trigger_alert` échoue (non bloquant).

### `cost_tracking` (table matérialisée `infra/cost_tracking.sql`)

Vue agrégée à partir de `agent_events`, colonnes : `session_id`, `agent_name`, `run_date` (DATE), `total_tokens`, `estimated_cost_usd` (approximation $0.50 / 1M tokens, alignée Gemini 2.5 Flash), `llm_calls`. Schéma déclaratif dans `infra/bigquery_schema.json`.

### `test_runs` (alimenté par `scripts/import_test_results.py`)

Import JUnit XML après `make test` si `GOOGLE_CLOUD_PROJECT` est défini — non requis par le pipeline runtime, sert au suivi qualité CI.

---

## 5 — Règles de scoring déterministes

Implémentation : `scoring_agent/tools/score.py`. Paramètres versionnés dans `config/agent_config.json` (rechargés par `config/loader.py`, surcharge via env `MODEL_ID` / `BQ_DATASET_ID` uniquement — les seuils restent dans le JSON).

| # | Règle | Verdict | Paramètre | Valeur |
|---|---|---|---|---|
| 1 | Montant > moyenne catégorie × multiplier | **ALERTE** | `baseline_multiplier` | `3.0` |
| 2 | Doublon exact (`supplier_id` + `amount` + même jour) | **ALERTE** | — | — |
| 3 | `supplier_id` absent du référentiel | **SUSPECT** | `supplier_registry` | `SUP_001` … `SUP_050` (50 entrées) |
| 4 | Heure dans la plage suspecte UTC **ou** weekend | **SUSPECT** | `suspect_hours_start` / `suspect_hours_end` | `2` / `4` (02h00–04h00 UTC) |
| 5 | Fractionnement : ≥ N transactions < seuil vers même fournisseur dans la fenêtre, somme > seuil | **SUSPECT** | `fractionnement_min_count` / `validation_threshold` / `fractionnement_window_hours` | `3` / `500.0` € / `48` h |

Précisions implémentation :

- **Baseline** : moyenne arithmétique du montant **par catégorie sur le batch courant** (`_compute_baseline`). Pas de baseline historique persistée (volontaire — DESIGN_SPEC v1, simplicité et reproductibilité du scoring).
- **Score final** : si au moins un motif ALERTE déclenché, score = `ALERTE` et **tous** les motifs (ALERTE + SUSPECT) sont conservés. Sinon, si motif SUSPECT, score = `SUSPECT`. Sinon `NORMAL` avec `motifs=[]`.
- **Trace ID** : chaque `ScoredTransaction` reçoit un `trace_id` UUID4 pour corrélation avec `agent_events`.

---

## 6 — Observabilité

Quatre couches superposées, chacune adressant une question opérationnelle distincte.

| Couche | Outil | Réponse |
|---|---|---|
| Événements agent | `BigQueryAgentAnalyticsPlugin` → `agent_events` (`batch_size=1`, faible latence) | « Quels tools, dans quel ordre, combien de tokens ? » |
| Métrique métier | Cloud Monitoring custom `custom.googleapis.com/agent/anomaly_alert` (GAUGE, labels `tx_id`, `motifs`, `invocation_id`) | « Combien d'alertes émises sur la dernière heure ? » |
| Notification | Slack Incoming Webhook (`SLACK_WEBHOOK_URL`, POST `urllib`) | « Qui doit agir maintenant ? » |
| Tracing distribué | OpenTelemetry `TracerProvider` (`orchestrator/app.py`) — peuple `trace_id` / `span_id` dans `agent_events` | « Où s'est passée cette latence ? » |

**Note tracing :** le `TracerProvider` est initialisé sans exporter (les traces ne sont pas encore poussées vers Cloud Trace). Les `trace_id` / `span_id` sont néanmoins peuplés dans `agent_events`, ce qui suffit aux requêtes de corrélation BigQuery actuelles. L'ajout d'un `CloudTraceSpanExporter` est un évolutif tracé (cf. `docs/adr/`).

**Labels facturation Vertex** : le callback `vertex_billing_before_model` injecte sur chaque `generateContent` les labels `agent_name`, `pipeline_run_id`, `environment` (`dev` / `prod`) — base des agrégats `cost_tracking`. Les labels sont silencieusement ignorés par ADK si le backend n'est pas Vertex (Google AI Studio).

---

## 7 — KPIs

Mesures référencées : run de production sur `data/golden_set.csv` (250 transactions, 23 marquées ALERTE), modèle `gemini-2.5-flash`, région `europe-west1`.

| KPI | Seuil cible | Mesure production | Statut |
|---|---|---|---|
| **Accuracy globale** | ≥ 85 % | **90 %** | OK |
| Precision ALERTE | ≥ 90 % | **100 %** | OK |
| Recall ALERTE | ≥ 90 % | **100 %** | OK |
| Latence p95 tool call | ≤ 3 000 ms | **455 ms** | OK |
| Alertes Cloud Monitoring émises | 23 / 23 | **23 / 23** | OK |
| Alertes Slack délivrées | 23 / 23 | **23 messages** | OK |
| **Cost / run** | **≤ 0,10 USD** | **~0,05 USD (~16 000 tokens)** | **OK** |
| Tests CI | 20 / 20 verts | **20 / 20** | OK |

### 7.5 — Contrainte déploiement

`make deploy` est **délibérément bloqué** (`exit 1` + message d'avertissement) : aucune commande automatisée ne déclenche un déploiement Vertex AI Agent Engine. **Approbation humaine explicite requise** avant exécution manuelle de `adk deploy agent_engine` (cf. `DEPLOY_AGENT_ENGINE.md`). Cette règle vaut tant pour `dev` que `prod` et elle est rappelée dans `CLAUDE.md` du workspace.

---

## 8 — Décisions d'architecture

Renvoi vers `docs/adr/` — chaque décision structurante est tracée :

| ADR | Sujet | Impact |
|---|---|---|
| ADR-005 | CI Cloud Build (suite complète, pas un seul test) | `cloudbuild.yaml` → `pytest tests/ -v` |
| ADR-006 | Firestore exclu, config JSON versionnée | `config/agent_config.json` |
| ADR-007 | Vertex AI Agent Engine vs Cloud Run | déploiement `europe-west1` |
| ADR-008 | MCP exclu, tools GCP natifs | `google.cloud.bigquery`, `monitoring_v3`, `storage` |
| ADR-009 | Google ADK comme framework | `Agent` + `transfer_to_agent` |
| ADR-010 | Modèle `gemini-2.5-flash` (Vertex AI) | `config/agent_config.json` |
| ADR-011 | Mono-repo multi-agents vs microservices | 3 agents dans le même repo, 1 image Agent Engine |

---

## 9 — Sécurité et conformité

- **Authentification** — Vertex AI via **Application Default Credentials** uniquement (`gcloud auth application-default login`, `GOOGLE_GENAI_USE_VERTEXAI=true`). Aucune clé API Google AI Studio n'est lue par le code en production. La présence de `GOOGLE_CLOUD_PROJECT` conditionne l'activation du plugin BigQuery, des appels Cloud Monitoring et des écritures `audit_reports`.
- **Secrets** — `SLACK_WEBHOOK_URL` est une variable d'environnement (ou Secret Manager monté en runtime sur Agent Engine). Jamais commitée. `.env.example` est en placeholder vide.
- **Transparence (AI Act Art. 13)** — `ScoredTransaction.motifs` expose les règles déclenchées en clair (texte FR, format `ALERTE_MONTANT_HORS_BASELINE: …`). `audit_reports.transactions` les persiste, `trigger_alert` les transmet à Slack et aux labels Cloud Monitoring (tronqués à 64 caractères, contrainte Cloud Monitoring labels).
- **Supervision humaine (AI Act Art. 14)** — la doc, l'instruction de l'orchestrateur et le docstring de `trigger_alert` rappellent : « Ne bloque aucun paiement automatiquement ». Le pipeline notifie, ne décide pas.
- **Robustesse plugin BigQuery** — `BigQueryAgentAnalyticsPlugin` est encapsulé en `try/except ImportError` : si la version d'ADK installée ne le fournit pas, l'app démarre sans observabilité BQ (mode dégradé loggué).
- **Robustesse alertes** — `trigger_alert` retourne `status='error'` plutôt que de lever, et l'orchestrateur passe à la transaction suivante (pas de retry → évite les collisions GAUGE Cloud Monitoring < 1 minute).
