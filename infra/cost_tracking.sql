-- =============================================================================
-- Couche 2 — Agrégat coût estimé (scheduled query recommandée)
-- =============================================================================
-- Prérequis : BigQueryAgentAnalyticsPlugin avec create_views=true (vue v_llm_response).
-- Sinon, remplacez la FROM par la requête commentée sur agent_events plus bas.
--
-- Tarifs indicatifs Gemini 2.5 Flash (thinking OFF, ≤200K context) :
--   input ~$0.15 / 1M tokens, output ~$2.50 / 1M tokens.
-- L’usage réel est dans content.usage (prompt / completion / total) ; ici on
-- agrège usage_total_tokens (vue) ou $.usage.total (table brute).
--
-- Approximation documentée : estimated_cost_usd = total_tokens * 0.50 / 1e6.
-- C’est un ordre de grandeur (ratio input/output inconnu) — ajuster le
-- multiplicateur si vous modélisez séparément prompt vs completion.
--
-- Remplacez `agent_prod` par votre dataset (ex. même valeur que BQ_DATASET_ID).

CREATE OR REPLACE TABLE `agent_prod.cost_tracking` AS
SELECT
  session_id,
  agent AS agent_name,
  DATE(timestamp) AS run_date,
  SUM(COALESCE(usage_total_tokens, 0)) AS total_tokens,
  ROUND(SUM(COALESCE(usage_total_tokens, 0)) * 0.50 / 1000000, 4) AS estimated_cost_usd,
  COUNT(*) AS llm_calls
FROM `agent_prod.v_llm_response`
WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY session_id, agent, run_date;

-- Fallback si la vue n’existe pas encore (tokens dans le JSON ``content``) :
-- SELECT
--   session_id,
--   agent AS agent_name,
--   DATE(timestamp) AS run_date,
--   SUM(COALESCE(CAST(JSON_VALUE(content, '$.usage.total') AS INT64), 0)) AS total_tokens,
--   ROUND(SUM(COALESCE(CAST(JSON_VALUE(content, '$.usage.total') AS INT64), 0)) * 0.50 / 1000000, 4) AS estimated_cost_usd,
--   COUNT(*) AS llm_calls
-- FROM `agent_prod.agent_events`
-- WHERE event_type = 'LLM_RESPONSE'
--   AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
-- GROUP BY session_id, agent, run_date;


/*
=============================================================================
Couche 3 — Exemple : coûts Vertex AI depuis l’export facturation BigQuery
=============================================================================
Activer une fois : Console GCP → Facturation → Export facturation → BigQuery
(detailed usage cost). Remplacez la table par celle de votre export.

-- Copier dans l’éditeur BQ et exécuter (séparément de la scheduled query ci-dessus) :

SELECT
  invoice.month,
  labels.value AS pipeline_run_id,
  SUM(cost) AS total_cost_usd
FROM `billing_export.gcp_billing_export_v1_XXXXXX` AS t,
  UNNEST(labels) AS labels
WHERE service.description = 'Vertex AI'
  AND labels.key = 'pipeline_run_id'
GROUP BY invoice.month, labels.value
ORDER BY total_cost_usd DESC;
*/
