"""
Module de génération et export des fichiers JSON EnergyWorx
"""

import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from collections import defaultdict
import zipfile
import io

class EnergyWorxExporter:
    """Exportateur vers le format EnergyWorx"""
    
    def __init__(self):
        self.reading_type_mapping = {
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0": "A+ IX15m",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.74.0": "A- IX15m", 
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.75.0": "A+ IX15m Q1",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.76.0": "A- IX15m Q1",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.77.0": "Q+ IX15m",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.78.0": "Q- IX15m",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.79.0": "Q+ IX15m Q1",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.80.0": "Q- IX15m Q1",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.81.0": "Q+ IX15m Q2",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.82.0": "Q- IX15m Q2",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.83.0": "S+ IX15m",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.84.0": "S- IX15m",
        }
    
    def export_readings(self, readings: List[Any], cldn: str = "") -> Dict[str, Any]:
        """Exporte les lectures vers le format EnergyWorx"""
        if not readings:
            return self._create_empty_meter_readings(cldn)
        
        # Grouper les lectures par CLDN et type de lecture
        grouped_readings = self._group_readings(readings)
        
        meter_readings = []
        
        for (reading_cldn, reading_type), type_readings in grouped_readings.items():
            if not type_readings:
                continue
            
            # Créer un IntervalBlock pour ce type de lecture
            interval_block = self._create_interval_block(type_readings, reading_type)
            
            if interval_block:
                meter_reading = {
                    "Meter": {
                        "mRID": reading_cldn,
                        "amrSystem": "ManualReading"
                    },
                    "IntervalBlocks": [interval_block]
                }
                meter_readings.append(meter_reading)
        
        # Créer le document EnergyWorx
        energyworx_doc = {
            "header": {
                "messageId": str(uuid.uuid4()),
                "source": "ManualReadingParser",
                "verb": "created",
                "noun": "MeterReadings",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "payload": {
                "MeterReadings": meter_readings
            }
        }
        
        return energyworx_doc
    
    def _group_readings(self, readings: List[Any]) -> Dict[tuple, List[Any]]:
        """Groupe les lectures par CLDN et type de lecture"""
        grouped = defaultdict(list)
        
        for reading in readings:
            key = (reading.cldn, reading.reading_type)
            grouped[key].append(reading)
        
        return dict(grouped)
    
    def _create_interval_block(self, readings: List[Any], reading_type: str) -> Dict[str, Any]:
        """Crée un IntervalBlock pour un type de lecture"""
        if not readings:
            return None
        
        # Trier les lectures par timestamp
        sorted_readings = sorted(readings, key=lambda x: x.timestamp)
        
        # Créer les IntervalReadings
        interval_readings = []
        
        for reading in sorted_readings:
            interval_reading = {
                "timeStamp": reading.timestamp.isoformat(),
                "value": str(int(reading.value)),
                "ReadingQualities": [
                    {"ref": "1.4.9"},  # Valid
                    {"ref": "1.4.16"}  # Manual
                ]
            }
            interval_readings.append(interval_reading)
        
        interval_block = {
            "IntervalReadings": interval_readings,
            "ReadingType": {
                "ref": reading_type
            }
        }
        
        return interval_block
    
    def _create_empty_meter_readings(self, cldn: str) -> Dict[str, Any]:
        """Crée un document EnergyWorx vide"""
        return {
            "header": {
                "messageId": str(uuid.uuid4()),
                "source": "ManualReadingParser",
                "verb": "created",
                "noun": "MeterReadings",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "payload": {
                "MeterReadings": []
            }
        }
    
    def export_to_files(self, processing_results: List[Any]) -> Dict[str, bytes]:
        """Exporte les résultats vers des fichiers JSON"""
        exported_files = {}
        
        for result in processing_results:
            if not result.success or not result.readings:
                continue
            
            # Grouper par CLDN
            readings_by_cldn = defaultdict(list)
            for reading in result.readings:
                readings_by_cldn[reading.cldn].append(reading)
            
            # Créer un fichier par CLDN
            for cldn, cldn_readings in readings_by_cldn.items():
                energyworx_doc = self.export_readings(cldn_readings, cldn)
                
                # Nom du fichier
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
                filename = f"meter-readings-created_{cldn}_{timestamp}_{uuid.uuid4().hex[:8]}.json"
                
                # Sérialisation JSON
                json_content = json.dumps(energyworx_doc, indent=2, ensure_ascii=False)
                exported_files[filename] = json_content.encode('utf-8')
        
        return exported_files
    
    def create_zip_export(self, exported_files: Dict[str, bytes]) -> bytes:
        """Crée un fichier ZIP avec tous les exports"""
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for filename, content in exported_files.items():
                zip_file.writestr(filename, content)
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()

class SummaryTableGenerator:
    """Générateur du tableau de synthèse"""
    
    def __init__(self):
        # Mapping corrigé selon la norme IEC 62056-61 et la documentation
        self.obis_mapping = {
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0": {
                "libelle_original": "A+ IX15m",
                "code_obis": "1-0:1.8.0",
                "description_standard": "Énergie active importée totale (kWh)",
                "statut": "CORRECT",
                "type_energie": "Active",
                "direction": "Importée",
                "quadrant": "",
                "unite": "kWh"
            },
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.74.0": {
                "libelle_original": "A- IX15m",
                "code_obis": "1-0:2.8.0",
                "description_standard": "Énergie active exportée totale (kWh)",
                "statut": "CORRECT",
                "type_energie": "Active",
                "direction": "Exportée",
                "quadrant": "",
                "unite": "kWh"
            },
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.75.0": {
                "libelle_original": "A+ IX15m Q1",
                "code_obis": "1-0:15.8.0",
                "description_standard": "Énergie active totale absolue (A+)",
                "statut": "CORRECT",
                "type_energie": "Active",
                "direction": "Importée",
                "quadrant": "",
                "unite": "kWh",
                "commentaire": ""
            },
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.76.0": {
                "libelle_original": "A- IX15m Q1",
                "code_obis": "1-0:16.8.0",
                "description_standard": "Énergie active totale absolue (A-)",
                "statut": "CORRECT",
                "type_energie": "Active",
                "direction": "Exportée",
                "quadrant": "",
                "unite": "kWh",
                "commentaire": ""
            },
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.77.0": {
                "libelle_original": "Q+ IX15m",
                "code_obis": "1-0:5.8.0",
                "description_standard": "Énergie réactive Q1 (kvarh)",
                "statut": "CORRECT",
                "type_energie": "Réactive",
                "direction": "Q1",
                "quadrant": "Q1 (+P, +Q)",
                "unite": "kvarh"
            },
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.78.0": {
                "libelle_original": "Q- IX15m",
                "code_obis": "1-0:6.8.0",
                "description_standard": "Énergie réactive Q2 (kvarh)",
                "statut": "CORRECT",
                "type_energie": "Réactive",
                "direction": "Q2",
                "quadrant": "Q2 (-P, +Q)",
                "unite": "kvarh"
            },
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.79.0": {
                "libelle_original": "Q+ IX15m Q1",
                "code_obis": "1-0:7.8.0",
                "description_standard": "Énergie réactive Q3 (kvarh)",
                "statut": "AVERTISSEMENT",
                "type_energie": "Réactive",
                "direction": "Q3",
                "quadrant": "Q3 (-P, -Q)",
                "unite": "kvarh",
                "commentaire": "Libellé erroné dans les données - code OBIS correct pour Q3"
            },
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.80.0": {
                "libelle_original": "Q- IX15m Q1",
                "code_obis": "1-0:8.8.0",
                "description_standard": "Énergie réactive Q4 (kvarh)",
                "statut": "AVERTISSEMENT",
                "type_energie": "Réactive",
                "direction": "Q4",
                "quadrant": "Q4 (+P, -Q)",
                "unite": "kvarh",
                "commentaire": "Libellé erroné dans les données - code OBIS correct pour Q4"
            },
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.81.0": {
                "libelle_original": "Q+ IX15m Q2",
                "code_obis": "1-0:3.8.0",
                "description_standard": "Énergie réactive Q1 (kvarh)",
                "statut": "AVERTISSEMENT",
                "type_energie": "Réactive",
                "direction": "Q1",
                "quadrant": "Q1 (+P, +Q)",
                "unite": "kvarh",
                "commentaire": "Libellé erroné dans les données - code OBIS correct pour Q1"
            },
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.82.0": {
                "libelle_original": "Q- IX15m Q2",
                "code_obis": "1-0:4.8.0",
                "description_standard": "Énergie réactive Q2 (kvarh)",
                "statut": "AVERTISSEMENT",
                "type_energie": "Réactive",
                "direction": "Q2",
                "quadrant": "Q2 (-P, +Q)",
                "unite": "kvarh",
                "commentaire": "Libellé erroné dans les données - code OBIS correct pour Q2"
            },
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.83.0": {
                "libelle_original": "S+ IX15m",
                "code_obis": "1-0:9.8.0",
                "description_standard": "Énergie apparente importée (kVAh)",
                "statut": "CORRECT",
                "type_energie": "Apparente",
                "direction": "Importée",
                "quadrant": "",
                "unite": "kVAh"
            },
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.84.0": {
                "libelle_original": "S- IX15m",
                "code_obis": "1-0:10.8.0",
                "description_standard": "Énergie apparente exportée (kVAh)",
                "statut": "CORRECT",
                "type_energie": "Apparente",
                "direction": "Exportée",
                "quadrant": "",
                "unite": "kVAh"
            }
        }
    
    def generate_summary_table(self, processing_results: List[Any]) -> List[Dict[str, Any]]:
        """Génère le tableau de synthèse des compteurs relevés"""
        summary_data = []
        
        for result in processing_results:
            if not result.success or not result.readings:
                continue
            
            # Grouper par CLDN et type de lecture
            readings_by_cldn_and_type = defaultdict(list)
            for reading in result.readings:
                key = (reading.cldn, reading.reading_type)
                readings_by_cldn_and_type[key].append(reading)
            
            # Calculer les statistiques par CLDN
            # Utiliser channels_count depuis FileProcessingResult si disponible, sinon compter les reading_type uniques
            cldn_stats = defaultdict(lambda: {'channels': set(), 'total_readings': 0, 'file_info': {}, 'channels_count': None})
            
            for (cldn, reading_type), readings in readings_by_cldn_and_type.items():
                if not readings:
                    continue
                
                cldn_stats[cldn]['channels'].add(reading_type)
                cldn_stats[cldn]['total_readings'] += len(readings)
                cldn_stats[cldn]['file_info'] = {
                    'filename': result.filename,
                    'file_type': self._detect_file_type_from_filename(result.filename)
                }
                # Stocker le channels_count depuis FileProcessingResult (nombre de codes OBIS uniques depuis capture_objects)
                if result.channels_count is not None:
                    cldn_stats[cldn]['channels_count'] = result.channels_count
            
            # Créer une entrée pour chaque combinaison CLDN/type
            for (cldn, reading_type), readings in readings_by_cldn_and_type.items():
                if not readings:
                    continue
                
                # Calculer les dates min/max
                timestamps = [r.timestamp for r in readings]
                date_min = min(timestamps)
                date_max = max(timestamps)
                
                # Calculer la complétude
                completeness = self._calculate_completeness(readings)
                
                # Obtenir les informations OBIS détaillées
                obis_info = self.obis_mapping.get(reading_type, {
                    "libelle_original": reading_type,
                    "code_obis": "INCONNU",
                    "description_standard": "Type de lecture non reconnu",
                    "statut": "INCONNU",
                    "type_energie": "?",
                    "direction": "?",
                    "quadrant": "",
                    "unite": "?",
                    "commentaire": "Type de lecture non référencé"
                })
                
                # Obtenir les statistiques du CLDN
                stats = cldn_stats[cldn]
                
                # Utiliser channels_count depuis capture_objects si disponible, sinon fallback sur reading_type uniques
                channels_count = stats['channels_count'] if stats['channels_count'] is not None else len(stats['channels'])
                
                summary_entry = {
                    'CLDN': cldn,
                    'Libellé Original': obis_info['libelle_original'],
                    'Code OBIS': obis_info['code_obis'],
                    'Description Standard': obis_info['description_standard'],
                    'Type Énergie': obis_info['type_energie'],
                    'Direction/Quadrant': obis_info['direction'] if not obis_info['quadrant'] else obis_info['quadrant'],
                    'Unité': obis_info['unite'],
                    'Statut Validation': obis_info['statut'],
                    'Commentaire': obis_info.get('commentaire', ''),
                    'Date min': date_min.strftime('%Y-%m-%d %H:%M:%S%z'),
                    'Date max': date_max.strftime('%Y-%m-%d %H:%M:%S%z'),
                    'Complet': completeness['complete'],
                    'Pourcentage': f"{completeness['percentage']:.1f}%",
                    'Nombre de canaux': channels_count,
                    'Mesures temporelles': len(readings),
                    'Type de fichier': stats['file_info']['file_type'],
                    'Fichier source': result.filename
                }
                
                summary_data.append(summary_entry)
        
        return summary_data
    
    def _detect_file_type_from_filename(self, filename: str) -> str:
        """Détecte le type de fichier à partir du nom de fichier"""
        filename_lower = filename.lower()
        
        if filename_lower.endswith('.csv'):
            return 'CSV BlueLink'
        elif filename_lower.endswith(('.xlsx', '.xls')):
            return 'Excel BlueLink'
        elif filename_lower.endswith('.xml'):
            if 'e570' in filename_lower or 'metervalues' in filename_lower:
                return 'XML MAP110 E570'
            elif 'e360' in filename_lower:
                return 'XML MAP110 E360'
            elif 'e450' in filename_lower or 'lgz1030767023632' in filename_lower:
                return 'XML MAP110 E450'
            else:
                return 'XML MAP110'
        elif filename_lower.endswith('.zip'):
            return 'ZIP'
        else:
            return 'Inconnu'
    
    def _calculate_completeness(self, readings: List[Any]) -> Dict[str, Any]:
        """Calcule la complétude des données"""
        if len(readings) < 2:
            return {'complete': False, 'percentage': 0.0}
        
        # Trier par timestamp
        sorted_readings = sorted(readings, key=lambda x: x.timestamp)
        
        # Calculer la durée totale
        start_time = sorted_readings[0].timestamp
        end_time = sorted_readings[-1].timestamp
        total_duration = end_time - start_time
        
        # Calculer le nombre de lectures attendues (intervalle de 15 minutes)
        expected_readings = int(total_duration.total_seconds() / (15 * 60)) + 1
        
        if expected_readings == 0:
            return {'complete': False, 'percentage': 0.0}
        
        # Calculer le pourcentage de complétude
        actual_readings = len(readings)
        percentage = (actual_readings / expected_readings) * 100
        
        # Considérer comme complet si = 100%
        complete = percentage == 100.0
        
        return {
            'complete': complete,
            'percentage': min(percentage, 100.0)
        }
    
    def export_summary_to_csv(self, summary_data: List[Dict[str, Any]]) -> str:
        """Exporte le tableau de synthèse en CSV"""
        if not summary_data:
            return ""
        
        import csv
        import io
        
        output = io.StringIO()
        fieldnames = ['CLDN', 'Libellé Original', 'Code OBIS', 'Description Standard', 'Type Énergie', 
                     'Direction/Quadrant', 'Unité', 'Statut Validation', 'Commentaire', 'Date min', 'Date max', 
                     'Complet', 'Pourcentage', 'Nombre de canaux', 'Mesures temporelles', 'Type de fichier', 'Fichier source']
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in summary_data:
            writer.writerow(row)
        
        return output.getvalue()
    
    def export_summary_to_excel(self, summary_data: List[Dict[str, Any]]) -> bytes:
        """Exporte le tableau de synthèse en Excel"""
        if not summary_data:
            return b""
        
        import pandas as pd
        
        df = pd.DataFrame(summary_data)
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Synthèse des compteurs', index=False)
        
        excel_buffer.seek(0)
        return excel_buffer.getvalue()
