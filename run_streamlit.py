#!/usr/bin/env python3
"""
Script de lancement amélioré pour Streamlit
"""

import subprocess
import sys
import os
import webbrowser
import time
import threading

def open_browser():
    """Ouvre le navigateur après un délai"""
    time.sleep(2)  # Attendre que Streamlit démarre
    webbrowser.open('http://localhost:8501')

def main():
    """Lance l'application Streamlit"""
    print("🚀 Lancement du Parser Relevés Manuels Compteurs")
    print("=" * 50)
    
    # Vérifier que app.py existe
    if not os.path.exists('app.py'):
        print("ERREUR: Fichier app.py non trouvé")
        print("💡 Assurez-vous d'être dans le bon répertoire")
        return 1
    
    print("🌐 Lancement de l'application Streamlit...")
    print("📱 L'application sera accessible à: http://localhost:8501")
    print("🔄 Ouverture automatique du navigateur...")
    print("🛑 Appuyez sur Ctrl+C pour arrêter")
    print("=" * 50)
    
    try:
        # Lancer l'ouverture du navigateur en arrière-plan
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()
        
        # Lancer Streamlit avec des paramètres pour réduire les URLs affichées
        cmd = [
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.headless", "true",
            "--server.runOnSave", "true",
            "--browser.gatherUsageStats", "false"
        ]
        
        subprocess.run(cmd, check=True)
        
    except KeyboardInterrupt:
        print("\n🛑 Application arrêtée par l'utilisateur")
    except subprocess.CalledProcessError as e:
        print(f"ERREUR lors du lancement: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
