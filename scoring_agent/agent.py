"""Sous-agent de scoring — applique les règles de détection d'anomalies financières."""

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini

from config.loader import load_config
from scoring_agent.tools.score import score_all_transactions
from shared.vertex_billing_labels import vertex_billing_before_model

_config = load_config()

scoring_agent = Agent(
    name="scoring_agent",
    model=Gemini(model=_config.get_model_id("scoring_agent")),
    before_model_callback=vertex_billing_before_model,
    description=(
        "Score toutes les transactions selon les règles déterministes de détection d'anomalies. "
        "Applique les règles : montant hors baseline, doublon exact, fournisseur inconnu, "
        "pattern temporel, fractionnement. Écrit les scores dans le session state via "
        "score_all_transactions puis rend la main à l'orchestrateur."
    ),
    instruction=(
        "Tu es l'agent de scoring de NovaPay. "
        "Les transactions à scorer sont déjà dans le session state (ingestion effectuée). "
        "Séquence obligatoire — deux appels, dans cet ordre :\n"
        "1. Appelle score_all_transactions sans paramètres.\n"
        "2. Dès que score_all_transactions répond (succès ou erreur), "
        "appelle immédiatement transfer_to_agent avec agent_name='finance_anomaly_orchestrator'. "
        "Ne produis aucun texte intermédiaire entre ces deux appels. "
        "Après avoir exécuté score_all_transactions, tu DOIS appeler transfer_to_agent('finance_anomaly_orchestrator'). "
        "Ne confirme PAS le résultat par du texte. N'écris PAS de message. "
        "La seule action autorisée après score_all_transactions est transfer_to_agent."
    ),
    tools=[score_all_transactions],
)
