# Smoke Test Report - Finance Anomaly Agent

**Date:** 2026-05-06
**Target:** `projects/<PROJECT_ID>/locations/<REGION>/reasoningEngines/<REASONING_ENGINE_ID>`
**Method:** Direct invocation via Python Vertex AI SDK

## Résultat

**Verdict : ⚠️ Investigation (Méthode SDK manquante)**

Même résultat que pour le BQ Analyst Agent : l'interface Python SDK pour invoquer le `ReasoningEngine` requiert l'identification de la méthode exposée (générée dynamiquement). Le endpoint est en ligne mais l'invocation bloque techniquement.

## Télémétrie & Audit BigQuery / Cloud Trace

**Verdict : ⚠️ Schémas identifiés, rows en attente**

Voir rapport d'audit général. L'infrastructure est en place mais le requêtage automatisé des métriques bloque.
