"""
Module de validation et contrôle qualité des données
"""

from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import pandas as pd

class DataValidator:
    """Validateur pour les données de compteurs"""
    
    def __init__(self):
        self.validation_rules = {
            'timestamp_format': self._validate_timestamp_format,
            'value_range': self._validate_value_range,
            'cldn_format': self._validate_cldn_format,
            'obis_validation': self._validate_obis_codes,
            'data_completeness': self._validate_data_completeness,
            'duplicates': self._validate_duplicates,
            'gaps': self._validate_gaps
        }
        
        # Référentiel OBIS selon la norme IEC 62056-61
        self.obis_reference = {
            "1-0:1.8.0": {"description": "Énergie active importée totale", "type": "Active", "direction": "Importée", "unite": "kWh", "standard": True},
            "1-0:2.8.0": {"description": "Énergie active exportée totale", "type": "Active", "direction": "Exportée", "unite": "kWh", "standard": True},
            "1-0:3.8.0": {"description": "Énergie réactive Q1", "type": "Réactive", "direction": "Q1", "unite": "kvarh", "standard": True},
            "1-0:4.8.0": {"description": "Énergie réactive Q2", "type": "Réactive", "direction": "Q2", "unite": "kvarh", "standard": True},
            "1-0:5.8.0": {"description": "Énergie réactive Q1", "type": "Réactive", "direction": "Q1", "unite": "kvarh", "standard": True},
            "1-0:6.8.0": {"description": "Énergie réactive Q2", "type": "Réactive", "direction": "Q2", "unite": "kvarh", "standard": True},
            "1-0:7.8.0": {"description": "Énergie réactive Q3", "type": "Réactive", "direction": "Q3", "unite": "kvarh", "standard": True},
            "1-0:8.8.0": {"description": "Énergie réactive Q4", "type": "Réactive", "direction": "Q4", "unite": "kvarh", "standard": True},
            "1-0:9.8.0": {"description": "Énergie apparente importée", "type": "Apparente", "direction": "Importée", "unite": "kVAh", "standard": True},
            "1-0:10.8.0": {"description": "Énergie apparente exportée", "type": "Apparente", "direction": "Exportée", "unite": "kVAh", "standard": True},
            "1-0:15.8.0": {"description": "Énergie active totale absolue (A+)", "type": "Active", "direction": "Importée", "unite": "kWh", "standard": True},
            "1-0:16.8.0": {"description": "Énergie active totale absolue (A-)", "type": "Active", "direction": "Exportée", "unite": "kWh", "standard": True}
        }
    
    def validate_readings(self, readings: List[Any], cldn: str = "") -> Dict[str, Any]:
        """Valide une liste de lectures"""
        validation_results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'statistics': {},
            'quality_score': 0.0
        }
        
        if not readings:
            validation_results['valid'] = False
            validation_results['errors'].append("Aucune lecture trouvée")
            return validation_results
        
        # Validation des formats
        for reading in readings:
            timestamp_valid = self._validate_timestamp_format(reading.timestamp)
            if not timestamp_valid:
                validation_results['errors'].append(f"Timestamp invalide: {reading.timestamp}")
                validation_results['valid'] = False
            
            value_valid = self._validate_value_range(reading.value)
            if not value_valid:
                validation_results['warnings'].append(f"Valeur suspecte: {reading.value}")
            
            cldn_valid = self._validate_cldn_format(reading.cldn)
            if not cldn_valid:
                validation_results['warnings'].append(f"CLDN suspect: {reading.cldn}")
        
        # Validation des doublons
        duplicates = self._validate_duplicates(readings)
        if duplicates:
            validation_results['warnings'].extend([f"Doublon détecté: {dup}" for dup in duplicates])
        
        # Validation des trous
        gaps = self._validate_gaps(readings)
        if gaps:
            validation_results['warnings'].extend([f"Trou détecté: {gap}" for gap in gaps])
        
        # Validation OBIS
        obis_issues = self._validate_obis_codes(readings)
        if obis_issues['errors']:
            validation_results['errors'].extend(obis_issues['errors'])
            validation_results['valid'] = False
        if obis_issues['warnings']:
            validation_results['warnings'].extend(obis_issues['warnings'])
        
        # Calcul des statistiques
        validation_results['statistics'] = self._calculate_statistics(readings)
        
        # Calcul du score de qualité
        validation_results['quality_score'] = self._calculate_quality_score(validation_results)
        
        return validation_results
    
    def _validate_timestamp_format(self, timestamp: datetime) -> bool:
        """Valide le format du timestamp"""
        if not isinstance(timestamp, datetime):
            return False
        
        # Vérifier que le timestamp n'est pas trop ancien ou futuriste
        now = datetime.now(timezone.utc)
        
        # S'assurer que les deux timestamps sont timezone-aware
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        
        if timestamp < now - timedelta(days=365*10):  # Plus de 10 ans
            return False
        if timestamp > now + timedelta(days=365):  # Plus d'un an dans le futur
            return False
        
        return True
    
    def _validate_value_range(self, value: float) -> bool:
        """Valide la plage des valeurs"""
        if not isinstance(value, (int, float)):
            return False
        
        # Vérifier que la valeur est positive et raisonnable
        if value < 0:
            return False
        if value > 999999999:  # Valeur trop élevée
            return False
        
        return True
    
    def _validate_cldn_format(self, cldn: str) -> bool:
        """Valide le format du CLDN"""
        if not cldn:
            return False
        
        # Format attendu: LGZ suivi de chiffres
        if not cldn.startswith('LGZ'):
            return False
        
        if len(cldn) < 10:
            return False
        
        return True
    
    def _validate_obis_codes(self, readings: List[Any]) -> Dict[str, List[str]]:
        """Valide les codes OBIS selon la norme IEC 62056-61"""
        issues = {'errors': [], 'warnings': []}
        
        # Mapping des reading_types vers les codes OBIS (basé sur export.py)
        reading_type_to_obis = {
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0": "1-0:1.8.0",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.74.0": "1-0:2.8.0",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.75.0": "1-0:15.8.0",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.76.0": "1-0:16.8.0",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.77.0": "1-0:5.8.0",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.78.0": "1-0:6.8.0",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.79.0": "1-0:7.8.0",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.80.0": "1-0:8.8.0",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.81.0": "1-0:3.8.0",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.82.0": "1-0:4.8.0",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.83.0": "1-0:9.8.0",
            "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.84.0": "1-0:10.8.0",
        }
        
        # Erreurs connues selon la documentation (CORRIGÉ)
        # Les codes OBIS sont corrects, les erreurs sont dans les libellés des données
        known_labeling_errors = {
            # Ces codes OBIS sont corrects, mais les libellés dans les données sont erronés
            "1-0:7.8.0": "Libellé erroné dans les données - code OBIS correct pour Q3 (-P, -Q)",
            "1-0:8.8.0": "Libellé erroné dans les données - code OBIS correct pour Q4 (+P, -Q)",
            "1-0:3.8.0": "Libellé erroné dans les données - code OBIS correct pour Q1 (+P, +Q)",
            "1-0:4.8.0": "Libellé erroné dans les données - code OBIS correct pour Q2 (-P, +Q)"
        }
        
        # Vérifier chaque type de lecture unique
        unique_reading_types = set(r.reading_type for r in readings)
        
        for reading_type in unique_reading_types:
            obis_code = reading_type_to_obis.get(reading_type)
            
            if not obis_code:
                issues['warnings'].append(f"Type de lecture non reconnu: {reading_type}")
                continue
            
            # Vérifier si c'est un code OBIS standard
            if obis_code not in self.obis_reference:
                issues['warnings'].append(f"Code OBIS non référencé: {obis_code}")
                continue
            
            # Vérifier les erreurs de libellage connues
            if obis_code in known_labeling_errors:
                issues['warnings'].append(f"Code OBIS {obis_code}: {known_labeling_errors[obis_code]}")
            
            # Vérifier si c'est un code non standard
            obis_info = self.obis_reference[obis_code]
            if not obis_info.get('standard', True):
                issues['warnings'].append(f"Code OBIS non standard détecté: {obis_code} - {obis_info['description']}")
        
        return issues
    
    def _validate_data_completeness(self, readings: List[Any]) -> Dict[str, Any]:
        """Valide la complétude des données"""
        if not readings:
            return {'complete': False, 'missing_periods': []}
        
        # Grouper par type de lecture
        readings_by_type = defaultdict(list)
        for reading in readings:
            readings_by_type[reading.reading_type].append(reading)
        
        completeness = {}
        for reading_type, type_readings in readings_by_type.items():
            if len(type_readings) < 2:
                completeness[reading_type] = {'complete': False, 'reason': 'Pas assez de données'}
                continue
            
            # Trier par timestamp
            sorted_readings = sorted(type_readings, key=lambda x: x.timestamp)
            
            # Vérifier les intervalles
            expected_interval = timedelta(minutes=15)  # Intervalle attendu de 15 minutes
            gaps = []
            
            for i in range(1, len(sorted_readings)):
                time_diff = sorted_readings[i].timestamp - sorted_readings[i-1].timestamp
                if time_diff > expected_interval * 2:  # Tolérance de 2x l'intervalle
                    gaps.append({
                        'start': sorted_readings[i-1].timestamp,
                        'end': sorted_readings[i].timestamp,
                        'duration': time_diff
                    })
            
            completeness[reading_type] = {
                'complete': len(gaps) == 0,
                'gaps': gaps,
                'total_readings': len(type_readings),
                'coverage_percentage': self._calculate_coverage_percentage(sorted_readings)
            }
        
        return completeness
    
    def _validate_duplicates(self, readings: List[Any]) -> List[str]:
        """Détecte les doublons"""
        seen = set()
        duplicates = []
        
        for reading in readings:
            key = (reading.timestamp, reading.reading_type, reading.cldn)
            if key in seen:
                duplicates.append(f"{reading.timestamp} - {reading.reading_type}")
            else:
                seen.add(key)
        
        return duplicates
    
    def _validate_gaps(self, readings: List[Any]) -> List[str]:
        """Détecte les trous dans les données"""
        gaps = []
        
        # Grouper par type de lecture
        readings_by_type = defaultdict(list)
        for reading in readings:
            readings_by_type[reading.reading_type].append(reading)
        
        for reading_type, type_readings in readings_by_type.items():
            if len(type_readings) < 2:
                continue
            
            # Trier par timestamp
            sorted_readings = sorted(type_readings, key=lambda x: x.timestamp)
            
            # Vérifier les intervalles
            expected_interval = timedelta(minutes=15)
            
            for i in range(1, len(sorted_readings)):
                time_diff = sorted_readings[i].timestamp - sorted_readings[i-1].timestamp
                if time_diff > expected_interval * 2:
                    gaps.append(f"{reading_type}: {sorted_readings[i-1].timestamp} -> {sorted_readings[i].timestamp}")
        
        return gaps
    
    def _calculate_statistics(self, readings: List[Any]) -> Dict[str, Any]:
        """Calcule les statistiques des données"""
        if not readings:
            return {}
        
        timestamps = [r.timestamp for r in readings]
        values = [r.value for r in readings]
        
        stats = {
            'total_readings': len(readings),
            'date_range': {
                'start': min(timestamps),
                'end': max(timestamps),
                'duration': max(timestamps) - min(timestamps)
            },
            'value_statistics': {
                'min': min(values),
                'max': max(values),
                'mean': sum(values) / len(values),
                'total': sum(values)
            },
            'reading_types': list(set(r.reading_type for r in readings)),
            'cldns': list(set(r.cldn for r in readings))
        }
        
        return stats
    
    def _calculate_coverage_percentage(self, readings: List[Any]) -> float:
        """Calcule le pourcentage de couverture des données"""
        if len(readings) < 2:
            return 0.0
        
        sorted_readings = sorted(readings, key=lambda x: x.timestamp)
        start_time = sorted_readings[0].timestamp
        end_time = sorted_readings[-1].timestamp
        
        total_duration = end_time - start_time
        expected_readings = int(total_duration.total_seconds() / (15 * 60)) + 1  # 15 minutes d'intervalle
        
        if expected_readings == 0:
            return 0.0
        
        actual_readings = len(readings)
        coverage = (actual_readings / expected_readings) * 100
        
        return min(coverage, 100.0)  # Plafonner à 100%
    
    def _calculate_quality_score(self, validation_results: Dict[str, Any]) -> float:
        """Calcule un score de qualité global"""
        score = 100.0
        
        # Pénalités pour les erreurs
        score -= len(validation_results['errors']) * 20
        
        # Pénalités pour les avertissements
        score -= len(validation_results['warnings']) * 5
        
        # Bonus pour la complétude
        if 'statistics' in validation_results:
            stats = validation_results['statistics']
            if 'total_readings' in stats and stats['total_readings'] > 0:
                # Bonus basé sur le nombre de lectures
                if stats['total_readings'] > 100:
                    score += 10
                elif stats['total_readings'] > 50:
                    score += 5
        
        return max(0.0, min(100.0, score))

class QualityReportGenerator:
    """Générateur de rapports de qualité"""
    
    def __init__(self):
        self.validator = DataValidator()
    
    def generate_report(self, processing_results: List[Any]) -> Dict[str, Any]:
        """Génère un rapport de qualité global"""
        report = {
            'summary': {
                'total_files': len(processing_results),
                'successful_files': 0,
                'failed_files': 0,
                'total_readings': 0,
                'total_errors': 0,
                'total_warnings': 0
            },
            'files': [],
            'global_statistics': {},
            'recommendations': []
        }
        
        all_readings = []
        
        for result in processing_results:
            file_report = {
                'filename': result.filename,
                'success': result.success,
                'readings_count': len(result.readings),
                'errors': result.errors,
                'warnings': result.warnings,
                'validation': None
            }
            
            if result.success and result.readings:
                # Validation des lectures
                validation = self.validator.validate_readings(result.readings)
                file_report['validation'] = validation
                all_readings.extend(result.readings)
            
            report['files'].append(file_report)
            
            # Mise à jour du résumé
            if result.success:
                report['summary']['successful_files'] += 1
            else:
                report['summary']['failed_files'] += 1
            
            report['summary']['total_readings'] += len(result.readings)
            report['summary']['total_errors'] += len(result.errors)
            report['summary']['total_warnings'] += len(result.warnings)
        
        # Statistiques globales
        if all_readings:
            report['global_statistics'] = self.validator._calculate_statistics(all_readings)
        
        # Génération des recommandations
        report['recommendations'] = self._generate_recommendations(report)
        
        return report
    
    def _generate_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """Génère des recommandations basées sur l'analyse"""
        recommendations = []
        
        summary = report['summary']
        
        if summary['failed_files'] > 0:
            recommendations.append(f"{summary['failed_files']} fichier(s) ont échoué. Vérifiez les formats et la qualité des données.")
        
        if summary['total_errors'] > 0:
            recommendations.append(f"{summary['total_errors']} erreur(s) détectée(s). Corrigez les données avant l'ingestion.")
        
        if summary['total_warnings'] > 0:
            recommendations.append(f"{summary['total_warnings']} avertissement(s) détecté(s). Vérifiez la qualité des données.")
        
        if summary['total_readings'] == 0:
            recommendations.append("Aucune lecture valide trouvée. Vérifiez les fichiers d'entrée.")
        
        # Recommandations spécifiques par fichier
        for file_report in report['files']:
            if file_report['validation']:
                validation = file_report['validation']
                if validation['quality_score'] < 70:
                    recommendations.append(f"Qualité faible pour {file_report['filename']}: {validation['quality_score']:.1f}%")
        
        return recommendations
