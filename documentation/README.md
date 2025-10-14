# Parser Relevés Manuels Compteurs

Application Streamlit pour convertir les relevés manuels de compteurs électriques vers le format EnergyWorx.

## 📋 Description

Cette application permet de traiter et convertir les fichiers de relevés manuels de compteurs électriques (CSV BlueLink, XML MAP110, Excel) vers le format JSON EnergyWorx pour l'ingestion dans le système MDMS.

## 🚀 Fonctionnalités

- **Support multi-formats** : CSV BlueLink, XML MAP110, Excel BlueLink
- **Traitement par lot** : Upload multiple de fichiers et ZIP
- **Validation qualité** : Contrôle des données, détection des erreurs et trous
- **Tableau de synthèse** : Vue d'ensemble des compteurs relevés avec métriques
- **Export EnergyWorx** : Génération de fichiers JSON compatibles
- **Interface intuitive** : Dashboard Streamlit avec drag & drop

## 📁 Formats supportés

### CSV BlueLink (Compteurs Ensor)
- Format avec séparateur `;`
- Codes OBIS dans l'en-tête
- Timestamps au format `DD/MM/YYYY HH:MM:SS`

### XML MAP110 (Compteurs Landis)
- Fichiers XML générés par MAP110/120/130
- Extraction automatique du CLDN
- Parsing des données de profil

### Excel BlueLink
- Fichiers .xlsx/.xls
- Support multi-feuilles
- Détection automatique des colonnes

## 🛠️ Installation

### Prérequis
- Python 3.8+
- pip

### Installation des dépendances
```bash
pip install -r requirements.txt
```

### Lancement de l'application
```bash
streamlit run app.py
```

L'application sera accessible à l'adresse : `http://localhost:8501`

## 📖 Utilisation

### 1. Upload des fichiers
- Glissez-déposez vos fichiers ou utilisez le sélecteur
- Formats acceptés : CSV, XML, Excel, ZIP
- Support multi-fichiers simultané

### 2. Traitement
- Cliquez sur "Traiter les fichiers"
- L'application analyse et valide les données
- Affichage des résultats et erreurs éventuelles

### 3. Synthèse
- Tableau récapitulatif des compteurs relevés
- Métriques de complétude des données
- Filtres par CLDN et registre
- Export CSV/Excel du tableau

### 4. Contrôle qualité
- Rapport détaillé de validation
- Score de qualité par fichier
- Détection des erreurs et avertissements
- Recommandations d'amélioration

### 5. Export
- Génération des fichiers JSON EnergyWorx
- Téléchargement individuel ou en lot (ZIP)
- Instructions d'ingestion dans EnergyWorx

## 🔧 Configuration

### Paramètres disponibles
- **CLDN forcé** : Valeur par défaut si manquante dans les fichiers
- **Fuseau horaire** : Conversion des timestamps (Europe/Zurich, Europe/Paris, UTC)

### Mapping des ReadingTypes
L'application mappe automatiquement les codes OBIS vers les ReadingTypes EnergyWorx :

| Code OBIS | ReadingType EnergyWorx | Description |
|-----------|------------------------|-------------|
| 1-0:1.8.0 | 0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0 | A+ IX15m |
| 1-0:2.8.0 | 0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.74.0 | A- IX15m |
| 1-0:5.8.0 | 0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.77.0 | Q+ IX15m |
| 1-0:6.8.0 | 0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.78.0 | Q- IX15m |

## 📊 Structure des données

### Format d'entrée (CSV BlueLink exemple)
```csv
12345678
1-0:99.1.0*255(0100630100FF) Profil de charge 1
Cl.8 0-0:1.0.0*255 Attr.2 ; Cl.1 0-0:96.10.1*255 Attr.2 ; Cl.3 1-0:1.8.0*255 Attr.2 (kWh) ; Cl.3 1-0:2.8.0*255 Attr.2 (kWh) ;
26/08/2025 00:15:00 ; 8 (DST) ; 9743,262 ; 7798,254 ;
```

### Format de sortie (JSON EnergyWorx)
```json
{
  "header": {
    "messageId": "uuid",
    "source": "ManualReadingParser",
    "verb": "created",
    "noun": "MeterReadings",
    "timestamp": "2025-08-27T00:14:23Z"
  },
  "payload": {
    "MeterReadings": [
      {
        "Meter": {
          "mRID": "LGZ1234567890123",
          "amrSystem": "ManualReading"
        },
        "IntervalBlocks": [
          {
            "IntervalReadings": [
              {
                "timeStamp": "2025-08-26T00:00:00.0000000+02:00",
                "value": "1453",
                "ReadingQualities": [
                  {"ref": "1.4.9"},
                  {"ref": "1.4.16"}
                ]
              }
            ],
            "ReadingType": {
              "ref": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0"
            }
          }
        ]
      }
    ]
  }
}
```

## 🔍 Validation et contrôle qualité

### Vérifications automatiques
- **Format des timestamps** : Validation des dates et heures
- **Plage des valeurs** : Vérification des valeurs numériques
- **Format CLDN** : Validation du format LGZ...
- **Doublons** : Détection des lectures en double
- **Trous de données** : Identification des intervalles manquants
- **Complétude** : Calcul du pourcentage de couverture

### Score de qualité
- **100%** : Données parfaites
- **70-99%** : Données de bonne qualité
- **<70%** : Données nécessitant une vérification

## 🚨 Gestion des erreurs

### Types d'erreurs détectées
- Format de fichier invalide
- Encodage incorrect
- Timestamps malformés
- Valeurs non numériques
- CLDN manquant ou invalide
- Codes OBIS non reconnus

### Types d'avertissements
- Valeurs suspectes
- Trous dans les données
- Doublons détectés
- Complétude faible

## 📈 Métriques et statistiques

### Tableau de synthèse
- **CLDN** : Identifiant du compteur
- **Registre** : Type de lecture (A+, A-, Q+, Q-, etc.)
- **Date min/max** : Plage temporelle des données
- **Complet** : Indicateur de complétude
- **Pourcentage** : Taux de couverture des données
- **Nombre de lectures** : Total des points de mesure

### Statistiques globales
- Nombre total de fichiers traités
- Nombre de lectures extraites
- Taux de succès/échec
- Score de qualité moyen

## 🔧 Développement

### Structure du projet
```
05_SDE_XML/
├── app.py              # Application Streamlit principale
├── parsers.py          # Parsers pour chaque format
├── validation.py       # Module de validation
├── export.py           # Export vers EnergyWorx
├── requirements.txt    # Dépendances Python
└── README.md          # Documentation
```

### Modules principaux

#### `parsers.py`
- `BlueLinkCSVParser` : Parser CSV BlueLink
- `MAP110XMLParser` : Parser XML MAP110
- `BlueLinkExcelParser` : Parser Excel BlueLink
- `FileProcessor` : Processeur principal

#### `validation.py`
- `DataValidator` : Validateur de données
- `QualityReportGenerator` : Générateur de rapports

#### `export.py`
- `EnergyWorxExporter` : Exportateur EnergyWorx
- `SummaryTableGenerator` : Générateur de tableaux

## 🚀 Déploiement

### Streamlit Cloud
1. Créer un repository GitHub
2. Connecter à Streamlit Cloud
3. Configurer les paramètres de déploiement
4. Déployer automatiquement

### Déploiement local
```bash
# Installation
pip install -r requirements.txt

# Lancement
streamlit run app.py
```

## 📝 Notes techniques

### Limitations
- Taille maximale des fichiers : Dépend de Streamlit Cloud
- Formats supportés : CSV, XML, Excel uniquement
- Fuseaux horaires : Europe/Zurich, Europe/Paris, UTC

### Performances
- Traitement par lot optimisé
- Gestion mémoire efficace
- Indicateurs de progression

### Sécurité
- Aucune donnée persistante côté serveur
- Pas de connexion aux systèmes externes
- Code open source et auditable

## 🤝 Contribution

### Améliorations possibles
- Support de nouveaux formats de fichiers
- Amélioration des algorithmes de validation
- Interface utilisateur enrichie
- Tests automatisés

### Support
Pour toute question ou problème :
- Créer une issue sur GitHub
- Contacter l'équipe de développement

## 📄 Licence

Ce projet est développé pour INERA SA dans le cadre du projet SDE (Système de Données Énergétiques).

---

**Version** : 1.0.0  
**Dernière mise à jour** : Janvier 2025  
**Auteur** : Équipe INERA SA
