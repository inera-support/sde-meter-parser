#!/usr/bin/env python3
"""
Script de lancement pour le parser de relevés manuels
"""

import subprocess
import sys
import os

def check_dependencies():
    """Vérifie que les dépendances sont installées"""
    try:
        import streamlit
        import pandas
        import openpyxl
        import lxml
        print("Toutes les dependances sont installees")
        return True
    except ImportError as e:
        print(f"Dependance manquante: {e}")
        print("Installez les dependances avec: pip install -r requirements.txt")
        return False

def main():
    """Fonction principale"""
    print("Lancement du Parser Releves Manuels Compteurs")
    print("=" * 50)
    
    # Vérifier les dépendances
    if not check_dependencies():
        return 1
    
    # Vérifier que app.py existe
    if not os.path.exists('app.py'):
        print("Fichier app.py non trouve")
        print("Assurez-vous d'etre dans le bon repertoire")
        return 1
    
    print("Lancement de l'application Streamlit...")
    print("L'application sera accessible a: http://localhost:8501")
    print("Appuyez sur Ctrl+C pour arreter l'application")
    print("=" * 50)
    
    try:
        # Lancer Streamlit
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"], check=True)
    except KeyboardInterrupt:
        print("Application arretee par l'utilisateur")
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors du lancement: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
