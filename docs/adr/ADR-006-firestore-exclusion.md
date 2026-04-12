# ADR-006 — Exclusion Firestore pour le stockage de `model_id` (pilote)

## Statut

Accepté

## Contexte

Firestore était prévu dans la Constitution (section 7.2) pour stocker `model_id` et permettre une configuration dynamique des agents.

## Décision

Pour ce pilote, **Firestore est exclu** : la configuration effective repose sur le fallback **`kairosium-finance-anomaly-agent/config/agent_config.json`** (comportement déjà prévu dans le chargeur de configuration).

## Raison

- Périmètre pilote **mono-environnement** : pas de besoin immédiat de réglage runtime multi-cibles.
- **Firestore représente un surcoût opérationnel** (IAM, règles, monitoring, cycles de déploiement des documents) **non justifié** à ce stade par le volume ou la fréquence de changement de `model_id`.

## Conséquences

- **`model_id` n’est pas modifiable sans redéploiement** (ou rebuild / rollout de l’artefact qui embarque `agent_config.json`), puisqu’il n’y a pas de source distante de vérité en production pour ce pilote.
- Les équipes doivent traiter `agent_config.json` comme la **source de vérité** pour le pilote et documenter tout changement de modèle dans le pipeline de release.

## Évolution

**Migration vers Firestore prévue en T3**, lorsque le périmètre multi-environnement ou la fréquence de changement de modèle justifiera la configuration à chaud et l’investissement opérationnel associé.
