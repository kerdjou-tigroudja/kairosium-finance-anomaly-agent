# ADR-010 — Modèle LLM : `gemini-2.5-flash` (Vertex AI)

## Statut

Accepté

## Contexte

Le pipeline combine **règles déterministes** (scoring) et **génération / orchestration** pilotée par LLM. Le modèle doit être appelable depuis **Vertex AI** dans la région de déploiement choisie (**`europe-west1`**), via l’**intégration native** Vertex (sans passer par un catalogue « Model Garden » comme chemin d’exécution principal de ce cas d’usage).

## Décision

- **Modèle retenu :** **`gemini-2.5-flash`**, adressé via l’**API Vertex AI Gemini** / configuration agent (`config/agent_config.json` et surcharges d’environnement).
- **Contrainte régionale :** au **moment du déploiement**, les modèles de la branche **Gemini 3** n’étaient **pas** disponibles sur **`europe-west1`**, ce qui excluait toute exigence implicite « dernière version absolue » si elle est incompatible avec la localisation imposée.

## Justification

- La charge dominante ici est un **scoring conditionnel de masse** (présentation d’enregistrements, branchement sur outils) plutôt qu’une tâche de raisonnement long-horizon ; **`gemini-2.5-flash`** offre un **débit élevé** et une **latence** adaptée.
- **Coût** : le volume de tokens par run reste modéré par rapport à des scénarios d’appels de contexte massifs ; le modèle choisi a un **profil de coût** très favorable par rapport à des modèles « pro » inutilement surdimensionnés.
- L’**arrêt prochain** de générations intermédiaires (ex. branche 2.0) impose de **suivre la matrice** de fin de vie côté Google, pas d’en rester sur un modèle déprécié.

## Conséquences

- Toute **montée** vers une famille plus récente repasse par une vérification **région + quota + disponibilité** et par une **ligne** dans l’ADR ou la config versionnée.
- Le mettre à jour n’est **pas** une simple substitution de `model_id` : il faut **revalider** coût, latence p95 et stabilité des appels d’outils.
