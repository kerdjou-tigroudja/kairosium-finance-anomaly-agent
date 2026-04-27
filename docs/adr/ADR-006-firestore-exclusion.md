# ADR-006 — Exclusion de Firestore pour la configuration (dont `model_id`)

## Statut

Accepté

## Contexte

Stocker `model_id` et la configuration des agents dans **Firestore** serait un choix valable pour un réglage à chaud, multi-tenant, ou des mises à jour fréquentes.

## Décision

**Firestore n’est pas utilisé** pour cette configuration : la source de vérité est le fichier versionné **`kairosium-finance-anomaly-agent/config/agent_config.json`** (comportement pris en charge par le chargeur de configuration de l’application).

## Raisons

- **Périmètre pilote mono-environnement** : pas de besoin immédiat de cibles runtime multiples.
- **Firestore ajoute** des contraintes **IAM**, du **réseau** (règles, exposition), un **cycle opérationnel** (monitoring, déploiement des données) **disproportionnées** quand le **`model_id`** et les paramètres de config **changent rarement** par rapport au coût d’un simple commit / release.
- Un **JSON versionné** est **plus simple à auditer**, **reproductible** entre environnements et **aligné** avec l’exigence de reproductibilité d’un agent déployé comme artefact.

## Conséquences

- `model_id` n’est **pas** modifiable sans **redéploiement** (ou roll-out de l’artefact contenant `agent_config.json`).

## Évolution

Réintroduire un store dynamique (Firestore ou autre) se justifiera quand le **périmètre multi-environnement** ou la **fréquence de changement** de configuration imposera la configuration à chaud et l’investissement opérationnel associé.
