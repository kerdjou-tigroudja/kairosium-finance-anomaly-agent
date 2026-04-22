"""Sous-agent d'ingestion — parse et normalise les transactions depuis Cloud Storage."""

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini

from config.loader import load_config
from ingestion_agent.tools.ingest import ingest_transactions
from shared.vertex_billing_labels import vertex_billing_before_model

_config = load_config()

ingestion_agent = Agent(
    name="ingestion_agent",
    model=Gemini(model=_config.get_model_id("ingestion_agent")),
    before_model_callback=vertex_billing_before_model,
    description=(
        "Parse et normalise les transactions depuis Cloud Storage. "
        "Appelle ingest_transactions avec le chemin CSV fourni. "
        "Retourne le nombre de transactions ingérées."
    ),
    instruction=(
        "Tu es l'agent d'ingestion de NovaPay. "
        "Ton unique rôle est de parser le fichier CSV de transactions. "
        "Séquence obligatoire — deux appels, dans cet ordre :\n"
        "1. Appelle ingest_transactions : paramètre gcs_path = la valeur playground ci-dessous "
        "si elle est non vide après substitution, sinon le chemin gs:// ou local utilisateur.\n"
        "   Chemin playground : {playground_csv_path?}\n"
        "2. Dès que ingest_transactions répond (succès ou erreur), "
        "appelle immédiatement transfer_to_agent avec agent_name='scoring_agent'. "
        "Ne produis aucun texte intermédiaire entre ces deux appels. "
        "Ne signale jamais le handoff par du texte — utilise uniquement transfer_to_agent."
    ),
    tools=[ingest_transactions],
)
