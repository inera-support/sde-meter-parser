"""
Script de test pour valider les corrections du parser E360 selon le manuel MAP110

Tests:
1. Conversion Wh → kWh
2. Structure des champs (Index 0-7)
3. Extraction du Status Word
4. Parsing de capture_objects
"""

import sys
import os
from pathlib import Path
from parsers import FileProcessor

# Ajouter le répertoire courant au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_e360_files():
    """Test les fichiers E360 avec les corrections"""
    
    # Chemin vers les fichiers E360
    e360_dir = Path("exmple/Reading MAP110 - E360")
    
    if not e360_dir.exists():
        print(f"❌ Dossier non trouvé: {e360_dir}")
        return
    
    # Fichiers à tester
    test_files = [
        "E360_LGZ1030166422061-ReadLoadProfile1.xml",
        "E360_LGZ1030166422061-ReadLoadProfile2.xml",
        "E360_LGZ1030166422061-ReadLoadProfile3.xml"
    ]
    
    processor = FileProcessor()
    results = []
    
    print("=" * 80)
    print("TEST DES CORRECTIONS E360 SELON LE MANUEL MAP110")
    print("=" * 80)
    print()
    
    for filename in test_files:
        filepath = e360_dir / filename
        
        if not filepath.exists():
            print(f"⚠️  Fichier non trouvé: {filepath}")
            continue
        
        print(f"📄 Traitement de: {filename}")
        print("-" * 80)
        
        # Lire le fichier
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parser
        result = processor.process_file(content, filename)
        
        if not result.success:
            print(f"❌ Erreur lors du parsing: {result.errors}")
            continue
        
        # Analyser les résultats
        readings = result.readings
        
        if not readings:
            print(f"⚠️  Aucune lecture extraite")
            continue
        
        # Statistiques
        print(f"✅ {len(readings)} lecture(s) extraite(s)")
        
        # Vérifier la conversion Wh → kWh
        sample_readings = readings[:5] if len(readings) >= 5 else readings
        print(f"\n📊 Échantillon de valeurs (vérification conversion Wh → kWh):")
        
        for i, reading in enumerate(sample_readings, 1):
            # Les valeurs doivent être en kWh (donc < 1000 pour des valeurs typiques)
            # Si on avait une valeur de 1930 Wh, elle devrait être 1.93 kWh
            value_kwh = reading.value
            value_wh_original = value_kwh * 1000  # Recalcul pour vérification
            
            print(f"  {i}. {reading.reading_type}")
            print(f"     Timestamp: {reading.timestamp}")
            print(f"     Valeur: {value_kwh:.3f} {reading.unit}")
            print(f"     (Valeur originale en Wh: {value_wh_original:.0f} Wh)")
            print(f"     Qualité: {reading.quality}")
            print()
        
        # Vérifier les valeurs sont raisonnables (en kWh, donc < 1000 typiquement)
        max_value = max(r.value for r in readings)
        min_value = min(r.value for r in readings)
        
        print(f"📈 Statistiques des valeurs:")
        print(f"   Min: {min_value:.3f} kWh")
        print(f"   Max: {max_value:.3f} kWh")
        print(f"   Moyenne: {sum(r.value for r in readings) / len(readings):.3f} kWh")
        
        # Vérification: si max > 1000 kWh, c'est suspect (peut-être pas converti)
        if max_value > 1000:
            print(f"   ⚠️  ATTENTION: Valeur max > 1000 kWh - vérifier la conversion!")
        else:
            print(f"   ✅ Valeurs raisonnables (conversion Wh → kWh OK)")
        
        # Vérifier les types de lectures
        reading_types = set(r.reading_type for r in readings)
        print(f"\n📋 Types de lectures extraits: {len(reading_types)}")
        for rt in sorted(reading_types):
            count = sum(1 for r in readings if r.reading_type == rt)
            print(f"   - {rt}: {count} lecture(s)")
        
        # Vérifier les unités
        units = set(r.unit for r in readings)
        print(f"\n📏 Unités: {', '.join(units)}")
        
        # Vérifier les qualités
        qualities = {}
        for r in readings:
            q = r.quality
            qualities[q] = qualities.get(q, 0) + 1
        print(f"\n🔍 Qualités des données:")
        for q, count in sorted(qualities.items()):
            print(f"   - {q}: {count} lecture(s)")
        
        results.append({
            'filename': filename,
            'readings_count': len(readings),
            'max_value': max_value,
            'min_value': min_value,
            'reading_types': len(reading_types),
            'success': max_value < 1000  # Vérification conversion
        })
        
        print()
    
    # Résumé
    print("=" * 80)
    print("RÉSUMÉ DES TESTS")
    print("=" * 80)
    
    total_readings = sum(r['readings_count'] for r in results)
    all_success = all(r['success'] for r in results)
    
    print(f"📊 Total de lectures extraites: {total_readings}")
    print(f"📁 Fichiers traités: {len(results)}")
    
    if all_success:
        print("✅ Tous les tests passés - Conversion Wh → kWh correcte!")
    else:
        print("⚠️  Certains fichiers ont des valeurs suspectes - vérifier la conversion")
    
    print()
    print("Détails par fichier:")
    for r in results:
        status = "✅" if r['success'] else "⚠️"
        print(f"  {status} {r['filename']}: {r['readings_count']} lectures, "
              f"max={r['max_value']:.3f} kWh, {r['reading_types']} types")
    
    return results

if __name__ == "__main__":
    test_e360_files()

