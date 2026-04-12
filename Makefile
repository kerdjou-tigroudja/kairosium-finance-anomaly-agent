.PHONY: playground test eval lint deploy generate-golden-set

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
