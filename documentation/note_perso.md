# Documentation : Analyse et Correction des Données de Compteurs (Codes OBIS)

## 1. Vue d'ensemble

Ce document a pour but de guider les développeurs dans le traitement des données de compteurs électriques exportées, en particulier celles contenant des codes OBIS. L'analyse des fichiers fournis a révélé des **incohérences critiques**, des **erreurs de duplication** et une **utilisation incorrecte des codes OBIS** par rapport à la norme internationale **IEC 62056-61**.

L'objectif est de fournir une feuille de route claire pour identifier, comprendre et corriger ces anomalies afin de garantir l'intégrité et la fiabilité des données traitées.

## 2. Problèmes Identifiés

L'analyse des données a mis en évidence trois catégories principales de problèmes.

### 2.1. Duplication des Données
Le compteur avec le `CLDN` **LGZ1234567890123** présente des entrées dupliquées pour plusieurs registres. Chaque mesure (`A+`, `A-`, `A+ Q1`, `A- Q1`) apparaît deux fois, ce qui peut fausser les calculs d'agrégation et les bilans énergétiques.

**Action requise :** Mettre en place un processus de déduplication pour les données provenant de ce compteur avant tout traitement.

### 2.2. Utilisation Incorrecte des Codes OBIS
La source de données mélange des codes OBIS standards avec des codes non standards (probablement propriétaires au fabricant) et des codes erronés.

* **Codes non standards** : Les codes `1-0:15.8.0` et `1-0:16.8.0` ne font pas partie de la norme IEC 62056-61 pour l'énergie (kWh). Selon les documentations techniques, ces codes sont souvent utilisés pour des mesures de **demande maximale cumulée** (puissance en kW), et non d'énergie. Leur association avec des libellés comme `A+ IX15m Q1` est donc incorrecte.
* **Libellés trompeurs** : L'annotation `IX15m` suggère une période d'intégration de 15 minutes (profil de charge), mais elle est utilisée de manière incohérente avec les codes OBIS.

### 2.3. Erreurs d'Attribution des Quadrants Réactifs
L'erreur la plus critique concerne l'énergie réactive. Le système attribue des codes OBIS qui ne correspondent pas aux quadrants décrits dans les libellés.

* **Exemple 1** : `Q+ IX15m Q1` est associé au code `1-0:7.8.0`. Or, `7.8.0` correspond à l'énergie réactive du **Quadrant 3 (Q3)**.
* **Exemple 2** : `Q- IX15m Q1` est associé au code `1-0:8.8.0`. Or, `8.8.0` correspond au **Quadrant 4 (Q4)**.
* **Exemple 3** : `Q+ IX15m Q2` est associé au code `1-0:3.8.0`. Or, `3.8.0` correspond au **Quadrant 1 (Q1)**.

## 3. Table de Correspondance et d'Analyse des Codes

Voici une analyse détaillée des codes présents dans le fichier, comparés à la norme.

| Libellé dans le Fichier | Code OBIS dans le Fichier | Signification Standard du Code | Statut | Commentaire |
| :--- | :--- | :--- | :--- | :--- |
| `A+ IX15m` | `1-0:1.8.0` | Énergie active importée totale (kWh) | ✅ **Correct** | Le code est standard et bien utilisé. |
| `A- IX15m` | `1-0:2.8.0` | Énergie active exportée totale (kWh) | ✅ **Correct** | Le code est standard et bien utilisé. |
| `A+ IX15m Q1` | `1-0:15.8.0` | Demande maximale cumulée (A+) | ❌ **Erreur** | Incohérence majeure. Le code mesure une puissance (kW), pas une énergie (kWh). |
| `A- IX15m Q1` | `1-0:16.8.0` | Demande maximale cumulée (A-) | ❌ **Erreur** | Incohérence majeure. Le code mesure une puissance (kW), pas une énergie (kWh). |
| `Q+ IX15m` | `1-0:5.8.0` | Énergie réactive Q1 (kvarh) | ✅ **Correct** | Le code correspond bien à l'énergie réactive du Quadrant 1. |
| `Q- IX15m` | `1-0:6.8.0` | Énergie réactive Q2 (kvarh) | ✅ **Correct** | Le code correspond bien à l'énergie réactive du Quadrant 2. |
| `Q+ IX15m Q1` | `1-0:7.8.0` | Énergie réactive Q3 (kvarh) | ❌ **Erreur** | **Mauvais quadrant**. Le libellé indique Q1 mais le code est celui de Q3. |
| `Q- IX15m Q1` | `1-0:8.8.0` | Énergie réactive Q4 (kvarh) | ❌ **Erreur** | **Mauvais quadrant**. Le libellé indique Q1 mais le code est celui de Q4. |
| `Q+ IX15m Q2` | `1-0:3.8.0` | Énergie réactive Q1 (kvarh) | ❌ **Erreur** | **Mauvais quadrant**. Le libellé indique Q2 mais le code est celui de Q1. |
| `Q- IX15m Q2` | `1-0:4.8.0` | Énergie réactive Q4 (kvarh) | ❌ **Erreur** | **Mauvais quadrant**. Le libellé indique Q2 mais le code est celui de Q4. |
| `S+ IX15m` | `1-0:9.8.0` | Énergie apparente importée (kVAh) | ✅ **Correct** | Le code est standard et bien utilisé. |



## 4. Recommandations pour les Développeurs

Pour assurer la fiabilité du traitement des données, les actions suivantes sont recommandées :

1.  **Ne pas se fier aux libellés (colonne `Registre`)** : Les libellés textuels sont trompeurs. Le traitement doit se baser en priorité sur le **code OBIS**, qui est la référence technique.

2.  **Mettre en place une couche de validation et de mapping** :
    * Créer un dictionnaire ou une table de mapping pour traduire les codes OBIS reçus vers leur signification correcte selon la norme IEC 62056-61.
    * Logger des avertissements (`warnings`) pour chaque code non standard ou mal attribué (`15.8.0`, `16.8.0`, `7.8.0` utilisé pour Q1, etc.).
    * Exclure ou marquer les données invalides pour éviter qu'elles ne polluent les analyses.

3.  **Contacter le fournisseur des données** :
    * Signaler les erreurs de configuration de l'export. La correction à la source est la solution la plus pérenne.
    * Demander la documentation technique du compteur pour comprendre la signification exacte des codes propriétaires (`15.8.0`, `16.8.0`).

4.  **Utiliser la table de référence standard** :
    Pour tout nouveau développement, se baser sur la table de référence ci-dessous.

### Référence Rapide des Codes OBIS Standards

| Description | Symbole | Code OBIS (Total) | Code OBIS (Tarif 1) | Code OBIS (Tarif 2) |
| :--- | :--- | :--- | :--- | :--- |
| **Énergie Active Importée** | `A+` | `1.8.0` | `1.8.1` | `1.8.2` |
| **Énergie Active Exportée** | `A-` | `2.8.0` | `2.8.1` | `2.8.2` |
| **Énergie Réactive Q1 (+P, +Q)** | `Q+` / `R1` | `3.8.0` | `3.8.1` | `3.8.2` |
| **Énergie Réactive Q2 (-P, +Q)** | `Q+` / `R2` | `4.8.0` | `4.8.1` | `4.8.2` |
| **Énergie Réactive Q3 (-P, -Q)** | `Q-` / `R3` | `7.8.0` | `7.8.1` | `7.8.2` |
| **Énergie Réactive Q4 (+P, -Q)** | `Q-` / `R4` | `8.8.0` | `8.8.1` | `8.8.2` |
| **Énergie Apparente Importée** | `S+` | `9.8.0` | `9.8.1` | `9.8.2` |
| **Énergie Apparente Exportée** | `S-` | `10.8.0`| `10.8.1`| `10.8.2`|

---