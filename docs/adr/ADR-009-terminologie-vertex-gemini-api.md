# ADR-009 — Terminologie Vertex AI Gemini API

**Statut :** Accepté

## Contexte

Dans le repository, le terme "Vertex AI Model Garden" était utilisé à tort pour désigner l'appel runtime au modèle `gemini-2.5-flash`. Model Garden est le catalogue de modèles de Google Cloud, et non le service d'inférence (runtime). L'appel runtime passe par "Vertex AI Gemini API" (ou simplement "Vertex AI"). L'utilisation de termes imprécis contredit le principe "Preuve > Assertion" et la rigueur technique attendue.

## Décision

1. Remplacer toutes les mentions erronées de "Model Garden" désignant un appel runtime par "Vertex AI Gemini API" ou "Vertex AI".
2. Conserver "Model Garden" uniquement lorsqu'il s'agit explicitement du catalogue de modèles (en précisant "catalogue Vertex AI Model Garden").
3. Appliquer cette correction aux chaînes documentaires (docstrings) et à la documentation (README.md, etc.) sans altérer le code fonctionnel.

## Conséquences

- Clarté technique rétablie concernant l'architecture d'inférence.
- Alignement avec la terminologie officielle Google Cloud.
- Aucune régression fonctionnelle (les appels API restent inchangés).
