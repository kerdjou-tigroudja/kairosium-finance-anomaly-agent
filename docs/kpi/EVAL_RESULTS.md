# KPI & Evaluation Results - Finance Anomaly Agent

Ce document rassemble les résultats des évaluations réalisées sur le Golden Set le **2026-05-05**, extraits de la synthèse globale.

## Synthèse Métriques

| KPI | Objectif / Target | Résultat Mesuré | Méthode | Verdict |
|---|---:|---:|---|---|
| Accuracy | ≥ 85% | 90% | Golden set (250 tx) | ✅ Atteint |
| Precision (Alert) | 100% | 100% | Golden set | ✅ Atteint |
| Latency (p95) | ≤ 3000ms | 455ms | Production tool call | ✅ Atteint |
| Cost / Run | ≤ $0.10 | < $0.05 | ~16k tokens (Flash 2.5) | ✅ Atteint |

## Commentaires

- **Précision** : Le pipeline respecte strictement la consigne 100% de précision sur les alertes générées.
- **Coûts** : Le choix de `gemini-2.5-flash` permet de limiter fortement la facture (< 0.05$ par run de 16k tokens), garantissant une viabilité économique forte pour le projet.
