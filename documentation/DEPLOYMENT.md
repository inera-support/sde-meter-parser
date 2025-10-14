# Configuration pour Streamlit Cloud

## Informations du projet
- **Nom** : Parser Relevés Manuels Compteurs
- **Description** : Application de conversion des relevés manuels vers EnergyWorx
- **Repository** : À configurer sur GitHub
- **Branch** : main

## Fichiers requis
- `app.py` : Application Streamlit principale
- `parsers.py` : Modules de parsing
- `validation.py` : Module de validation
- `export.py` : Module d'export
- `requirements.txt` : Dépendances Python
- `README.md` : Documentation

## Commandes de déploiement
```bash
# Installation des dépendances
pip install -r requirements.txt

# Lancement de l'application
streamlit run app.py
```

## Variables d'environnement
Aucune variable d'environnement requise (application autonome)

## Limitations Streamlit Cloud
- Taille maximale des fichiers : 200MB par fichier
- Mémoire : 1GB RAM
- CPU : 1 vCPU
- Stockage : 1GB

## Notes de déploiement
- L'application ne nécessite pas de base de données
- Aucune donnée n'est persistée côté serveur
- Compatible avec tous les navigateurs modernes
- Support des fichiers ZIP jusqu'à 200MB
