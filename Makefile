.PHONY: playground test eval lint deploy generate-golden-set test-integration

## Lance le playground interactif ADK (nécessite credentials GCP ou GOOGLE_API_KEY)
playground:
	uv run adk web .

## Exécute les tests pytest avec export JUnit XML et import BigQuery (si GOOGLE_CLOUD_PROJECT défini)
test:
	uv run pytest --junitxml=results.xml tests/ -v
	@if [ -n "$$GOOGLE_CLOUD_PROJECT" ]; then \
		uv run python scripts/import_test_results.py results.xml; \
	fi

## Lance l'évaluation ADK sur le evalset
eval:
	uv run adk eval orchestrator/ eval/evalset.json

## Vérifie la qualité du code avec ruff
lint:
	uv run ruff check .

SMOKE_TEST_PROMPT ?= Analyse les 3 dernières transactions du dataset de test et identifie les anomalies.

## Lance le test d'intégration A2A contre l'Agent Engine déployé
test-integration:
	@echo "=== Test intégration A2A — $(shell basename $(CURDIR)) ==="
	uv run python scripts/verify_agent_engine_remote.py \
		--message "$(SMOKE_TEST_PROMPT)" \
		--user-id "test-integration-$(shell date +%s)" \
		2>&1 | tee /tmp/integration_stream.json
	@python3 -c "\
import sys, json; \
lines = open('/tmp/integration_stream.json').readlines(); \
events = [json.loads(l) for l in lines if l.strip().startswith('{')]; \
errors = [e for e in events if isinstance(e, dict) and e.get('error')]; \
print(f'Événements : {len(events)} | Erreurs : {len(errors)}'); \
sys.exit(1) if errors else None" || \
		(echo "ERREUR — inspecter /tmp/integration_stream.json" && exit 1)
	@echo "=== Test intégration OK ==="

## Génère le golden set de 250 transactions synthétiques
generate-golden-set:
	uv run python data/generate_golden_set.py

## DEPLOY BLOQUÉ — approbation humaine explicite requise (DESIGN_SPEC §7.5, CLAUDE.md)
deploy:
	@echo "============================================================"
	@echo "DEPLOY BLOQUÉ — approbation humaine requise avant déploiement"
	@echo "Lire /adk-deploy-guide et obtenir l'approbation explicite."
	@echo "============================================================"
	@exit 1
