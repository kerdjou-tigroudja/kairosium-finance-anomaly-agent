"""Orchestrateur principal — point d'entrée unique du pipeline multi-agents NovaPay."""

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini

from config.loader import load_config
from ingestion_agent.agent import ingestion_agent
from orchestrator.tools.alert import trigger_alert
from orchestrator.tools.report import generate_audit_report
from scoring_agent.agent import scoring_agent
from shared.vertex_billing_labels import vertex_billing_before_model

_config = load_config()

root_agent = Agent(
    name="finance_anomaly_orchestrator",
    model=Gemini(model=_config.get_model_id()),
    before_model_callback=vertex_billing_before_model,
    description=(
        "Orchestre la détection d'anomalies financières NovaPay. "
        "Pipeline : ingestion CSV → scoring déterministe → rapport d'audit → alertes Cloud Monitoring."
    ),
    instruction="""Tu es l'orchestrateur de détection d'anomalies financières de NovaPay.

Workflow obligatoire à suivre dans cet ordre :

1. **Ingestion** : Délègue à ingestion_agent en lui fournissant le gcs_path du CSV.
   Attends la confirmation du nombre de transactions ingérées.

2. **Scoring** : Délègue à scoring_agent.
   Attends les compteurs NORMAL/SUSPECT/ALERTE.

3. **Rapport** : Appelle generate_audit_report (sans paramètres — les données sont en state).
   Note le report_id et le champ **alert_transactions** de la réponse (liste complète des ALERTE).

4. **Alertes** : Utilise **uniquement** la liste `alert_transactions` renvoyée par generate_audit_report.
   Pour **chaque** élément de cette liste, dans l'ordre, appelle **une fois** trigger_alert(tx_id, motifs, amount)
   avec les valeurs exactes du dictionnaire (motifs déjà au format attendu).
   Le nombre d'appels à trigger_alert doit **exactement** égaler `alert_count` — n'en saute aucun,
   n'invente aucun tx_id, ne te contente pas d'un « exemple ».
   Si trigger_alert retourne status='error', note l'échec et passe à la transaction suivante —
   NE JAMAIS rappeler trigger_alert pour la même transaction (risque de collision Cloud Monitoring).

5. **Résumé** : Retourne un résumé structuré **après** tous les trigger_alert :
   - report_id
   - total transactions
   - compteurs NORMAL / SUSPECT / ALERTE
   - liste des tx_id ALERTE (doit correspondre à alert_transactions)

Ne bloque aucun paiement automatiquement — les alertes requièrent une intervention humaine.
""",
    tools=[generate_audit_report, trigger_alert],
    sub_agents=[ingestion_agent, scoring_agent],
)
