"""
Parsers pour les différents formats de fichiers de relevés manuels
- CSV BlueLink (compteurs Ensor)
- XML MAP110 (compteurs Landis)
- Excel BlueLink
"""

import pandas as pd
import xml.etree.ElementTree as ET
import json
import zipfile
import io
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
import re
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MeterReading:
    """Classe pour représenter une lecture de compteur"""
    def __init__(self, timestamp: datetime, value: float, reading_type: str, 
                 unit: str, quality: str = "1.4.9", cldn: str = ""):
        self.timestamp = timestamp
        self.value = value
        self.reading_type = reading_type
        self.unit = unit
        self.quality = quality
        self.cldn = cldn

class FileProcessingResult:
    """Résultat du traitement d'un fichier"""
    def __init__(self, filename: str, success: bool, readings: List[MeterReading] = None, 
                 errors: List[str] = None, warnings: List[str] = None, channels_count: int = None):
        self.filename = filename
        self.success = success
        self.readings = readings or []
        self.errors = errors or []
        self.warnings = warnings or []
        self.channels_count = channels_count  # Nombre de codes OBIS uniques depuis capture_objects

class BlueLinkCSVParser:
    """Parser pour les fichiers CSV BlueLink"""
    
    OBIS_MAPPING = {
        "1-0:1.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0",  # A+ IX15m
        "1-0:2.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.74.0",  # A- IX15m
        "1-0:15.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.75.0", # A+ IX15m Q1
        "1-0:16.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.76.0", # A- IX15m Q1
        "1-0:5.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.77.0",  # Q+ IX15m
        "1-0:6.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.78.0",  # Q- IX15m
        "1-0:7.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.79.0",  # Q+ IX15m Q1
        "1-0:8.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.80.0",  # Q- IX15m Q1
        "1-0:3.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.81.0",  # Q+ IX15m Q2
        "1-0:4.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.82.0",  # Q- IX15m Q2
        "1-0:9.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.83.0",  # S+ IX15m
        "1-0:10.8.0": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.84.0", # S- IX15m
    }
    
    def parse(self, content: str, filename: str) -> FileProcessingResult:
        """Parse un fichier CSV BlueLink"""
        errors = []
        warnings = []
        readings = []
        
        try:
            # Gestion de l'encodage UTF-8 BOM
            content = self._handle_utf8_bom(content)
            
            lines = content.strip().split('\n')
            if len(lines) < 3:
                errors.append("Fichier CSV trop court")
                return FileProcessingResult(filename, False, errors=errors)
            
            # Extraction du CLDN (première ligne)
            cldn = lines[0].strip()
            if not cldn:
                errors.append("CLDN manquant")
                return FileProcessingResult(filename, False, errors=errors)
            
            # Extraction des en-têtes OBIS (troisième ligne)
            header_line = lines[2] if len(lines) > 2 else lines[1]
            obis_codes = self._extract_obis_codes(header_line)
            
            if not obis_codes:
                errors.append("Codes OBIS non trouvés dans l'en-tête")
                return FileProcessingResult(filename, False, errors=errors)
            
            # Traitement des données (lignes 4+)
            for i, line in enumerate(lines[3:], start=4):
                try:
                    line_readings = self._parse_data_line(line, obis_codes, cldn, i)
                    readings.extend(line_readings)
                except Exception as e:
                    errors.append(f"Ligne {i}: {str(e)}")
            
            if not readings:
                warnings.append("Aucune lecture valide trouvée")
            
        except Exception as e:
            errors.append(f"Erreur lors du parsing: {str(e)}")
            return FileProcessingResult(filename, False, errors=errors)
        
        return FileProcessingResult(filename, len(errors) == 0, readings, errors, warnings)
    
    def _handle_utf8_bom(self, content: str) -> str:
        """Gère l'encodage UTF-8 BOM dans le contenu"""
        # Supprimer le BOM UTF-8 si présent
        if content.startswith('\ufeff'):
            content = content[1:]
            logger.info("BOM UTF-8 détecté et supprimé")
        
        # Gérer les caractères d'encodage problématiques
        try:
            # Essayer d'encoder/décoder pour nettoyer
            content = content.encode('utf-8', errors='ignore').decode('utf-8')
        except UnicodeError:
            logger.warning("Problème d'encodage détecté, tentative de correction")
            # Fallback: remplacer les caractères problématiques
            content = content.encode('ascii', errors='replace').decode('ascii')
        
        return content
    
    def _extract_obis_codes(self, header_line: str) -> List[str]:
        """Extrait les codes OBIS de la ligne d'en-tête"""
        # Pattern pour trouver les codes OBIS comme "1-0:1.8.0"
        pattern = r'(\d+-\d+:\d+\.\d+\.\d+)'
        matches = re.findall(pattern, header_line)
        return matches
    
    def _parse_data_line(self, line: str, obis_codes: List[str], cldn: str, line_num: int) -> List[MeterReading]:
        """Parse une ligne de données"""
        readings = []
        
        # Séparation par point-virgule
        parts = [part.strip() for part in line.split(';')]
        
        if len(parts) < 2:
            raise ValueError("Ligne mal formatée")
        
        # Premier élément: timestamp
        timestamp_str = parts[0]
        try:
            # Format: "26/08/2025 00:15:00"
            timestamp = datetime.strptime(timestamp_str, "%d/%m/%Y %H:%M:%S")
            # Conversion en UTC (supposant Europe/Zurich)
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError(f"Format de date invalide: {timestamp_str}")
        
        # Les valeurs suivantes correspondent aux codes OBIS
        for i, obis_code in enumerate(obis_codes):
            if i + 1 < len(parts):
                value_str = parts[i + 1].replace(',', '.')
                try:
                    value = float(value_str)
                    reading_type = self.OBIS_MAPPING.get(obis_code, "")
                    if reading_type:
                        reading = MeterReading(
                            timestamp=timestamp,
                            value=value,
                            reading_type=reading_type,
                            unit="kWh" if "1.8.0" in obis_code else "kvarh" if "5.8.0" in obis_code or "6.8.0" in obis_code else "kVAh",
                            cldn=cldn
                        )
                        readings.append(reading)
                except ValueError:
                    continue  # Ignorer les valeurs non numériques
        
        return readings

class MAP110XMLParser:
    """Parser pour les fichiers XML MAP110"""
    
    # Mapping des codes OBIS MAP110 vers EnergyWorx (corrigé selon la structure réelle)
    OBIS_MAPPING = {
        # Énergie active totale
        "0100010800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0",  # A+ Total (1-0:1.8.0)
        "0100020800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.74.0",  # A- Total (1-0:2.8.0)
        
        # Énergie active par tarif
        "0100010801FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.75.0",  # A+ Tarif 1 (1-0:1.8.1)
        "0100010802FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.75.0",  # A+ Tarif 2 (1-0:1.8.2)
        "0100020801FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.76.0",  # A- Tarif 1 (1-0:2.8.1)
        "0100020802FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.76.0",  # A- Tarif 2 (1-0:2.8.2)
        
        # Énergie réactive totale
        "0100050800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.77.0",  # Q+ Total (1-0:5.8.0)
        "0100060800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.78.0",  # Q- Total (1-0:6.8.0)
        
        # Énergie réactive par tarif
        "0100050801FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.79.0",  # Q+ Tarif 1 (1-0:5.8.1)
        "0100050802FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.79.0",  # Q+ Tarif 2 (1-0:5.8.2)
        "0100060801FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.80.0",  # Q- Tarif 1 (1-0:6.8.1)
        "0100060802FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.80.0",  # Q- Tarif 2 (1-0:6.8.2)
        
        # Énergie réactive par quadrant
        "0100070800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.81.0",  # Q3 Total (1-0:7.8.0)
        "0100080800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.82.0",  # Q4 Total (1-0:8.8.0)
        
        # Énergie réactive Q3/Q4 par tarif (E360)
        "0100070801FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.81.0",  # Q3 Tarif 1 (1-0:7.8.1)
        "0100070802FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.81.0",  # Q3 Tarif 2 (1-0:7.8.2)
        "0100080801FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.82.0",  # Q4 Tarif 1 (1-0:8.8.1)
        "0100080802FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.82.0",  # Q4 Tarif 2 (1-0:8.8.2)
        
        # Profil de charge (LoadProfile)
        "0100630100FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0",  # Profil de charge A+ Load1
        "0100630200FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0",  # Profil de charge A+ Load2
        "0100630300FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0",  # Profil de charge A+ Load3
        "0100638000FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0",  # Profil de qualité de l'alimentation
        
        # Qualité d'alimentation (Load4) - Mesures non-énergétiques
        # Tensions moyennes (UInt16, scaler -1 = 0.1V)
        "0100201800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.90.0",  # Tension moyenne U1 (1-0:32.24.0)
        "0100341800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.91.0",  # Tension moyenne U2 (1-0:52.24.0)
        "0100481800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.92.0",  # Tension moyenne U3 (1-0:72.24.0)
        # Fréquence et courants moyens (UInt16, scaler à déterminer)
        "01000E1800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.93.0",  # Fréquence moyenne ou autre mesure (1-0:14.24.0)
        "01001F1800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.94.0",  # Courant moyen I1 (1-0:31.24.0)
        "0100331800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.95.0",  # Courant moyen I2 (1-0:51.24.0)
        "0100471800FF": "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.96.0",  # Courant moyen I3 (1-0:71.24.0)
    }
    
    # Dictionnaire de décodage des codes OBIS en format lisible
    OBIS_DECODER = {
        "0100010800FF": {
            "standard": "1-0:1.8.0",
            "description": "Énergie active importée totale",
            "unite": "kWh",
            "type": "Active",
            "direction": "Importée"
        },
        "0100020800FF": {
            "standard": "1-0:2.8.0", 
            "description": "Énergie active exportée totale",
            "unite": "kWh",
            "type": "Active",
            "direction": "Exportée"
        },
        "0100050800FF": {
            "standard": "1-0:5.8.0",
            "description": "Énergie réactive Q1 totale",
            "unite": "kvarh", 
            "type": "Réactive",
            "direction": "Q1"
        },
        "0100060800FF": {
            "standard": "1-0:6.8.0",
            "description": "Énergie réactive Q2 totale", 
            "unite": "kvarh",
            "type": "Réactive",
            "direction": "Q2"
        },
        "0100010801FF": {
            "standard": "1-0:1.8.1",
            "description": "Énergie active importée Tarif 1",
            "unite": "kWh",
            "type": "Active", 
            "direction": "Importée"
        },
        "0100010802FF": {
            "standard": "1-0:1.8.2",
            "description": "Énergie active importée Tarif 2",
            "unite": "kWh",
            "type": "Active",
            "direction": "Importée"
        },
        "0100020801FF": {
            "standard": "1-0:2.8.1", 
            "description": "Énergie active exportée Tarif 1",
            "unite": "kWh",
            "type": "Active",
            "direction": "Exportée"
        },
        "0100020802FF": {
            "standard": "1-0:2.8.2",
            "description": "Énergie active exportée Tarif 2", 
            "unite": "kWh",
            "type": "Active",
            "direction": "Exportée"
        },
        "0100050801FF": {
            "standard": "1-0:5.8.1",
            "description": "Énergie réactive Q1 Tarif 1",
            "unite": "kvarh",
            "type": "Réactive",
            "direction": "Q1"
        },
        "0100050802FF": {
            "standard": "1-0:5.8.2", 
            "description": "Énergie réactive Q1 Tarif 2",
            "unite": "kvarh",
            "type": "Réactive",
            "direction": "Q1"
        },
        "0100060801FF": {
            "standard": "1-0:6.8.1",
            "description": "Énergie réactive Q2 Tarif 1",
            "unite": "kvarh",
            "type": "Réactive", 
            "direction": "Q2"
        },
        "0100060802FF": {
            "standard": "1-0:6.8.2",
            "description": "Énergie réactive Q2 Tarif 2",
            "unite": "kvarh",
            "type": "Réactive",
            "direction": "Q2"
        },
        "0100070800FF": {
            "standard": "1-0:7.8.0",
            "description": "Énergie réactive Q3 totale",
            "unite": "kvarh",
            "type": "Réactive",
            "direction": "Q3"
        },
        "0100080800FF": {
            "standard": "1-0:8.8.0", 
            "description": "Énergie réactive Q4 totale",
            "unite": "kvarh",
            "type": "Réactive",
            "direction": "Q4"
        },
        "0100070801FF": {
            "standard": "1-0:7.8.1",
            "description": "Énergie réactive Q3 Tarif 1",
            "unite": "kvarh",
            "type": "Réactive",
            "direction": "Q3"
        },
        "0100070802FF": {
            "standard": "1-0:7.8.2",
            "description": "Énergie réactive Q3 Tarif 2",
            "unite": "kvarh",
            "type": "Réactive",
            "direction": "Q3"
        },
        "0100080801FF": {
            "standard": "1-0:8.8.1",
            "description": "Énergie réactive Q4 Tarif 1",
            "unite": "kvarh",
            "type": "Réactive",
            "direction": "Q4"
        },
        "0100080802FF": {
            "standard": "1-0:8.8.2",
            "description": "Énergie réactive Q4 Tarif 2",
            "unite": "kvarh",
            "type": "Réactive",
            "direction": "Q4"
        },
        "0100630100FF": {
            "standard": "1-0:63.1.0",
            "description": "Profil de charge A+ Load1 (15 minutes)",
            "unite": "kWh",
            "type": "Active",
            "direction": "Importée"
        },
        "0100630200FF": {
            "standard": "1-0:63.2.0",
            "description": "Profil de charge A+ Load2 (15 minutes)",
            "unite": "kWh",
            "type": "Active",
            "direction": "Importée"
        },
        "0100630300FF": {
            "standard": "1-0:63.3.0",
            "description": "Profil de charge A+ Load3 (15 minutes)",
            "unite": "kWh",
            "type": "Active",
            "direction": "Importée"
        },
        "0100638000FF": {
            "standard": "1-0:63.128.0",
            "description": "Profil de qualité de l'alimentation",
            "unite": "kWh",
            "type": "Active",
            "direction": "Importée"
        },
        # Qualité d'alimentation (Load4)
        "0100201800FF": {
            "standard": "1-0:32.24.0",
            "description": "Tension moyenne phase 1",
            "unite": "V",
            "type": "Qualité",
            "direction": "U1"
        },
        "0100341800FF": {
            "standard": "1-0:52.24.0",
            "description": "Tension moyenne phase 2",
            "unite": "V",
            "type": "Qualité",
            "direction": "U2"
        },
        "0100481800FF": {
            "standard": "1-0:72.24.0",
            "description": "Tension moyenne phase 3",
            "unite": "V",
            "type": "Qualité",
            "direction": "U3"
        },
        "01000E1800FF": {
            "standard": "1-0:14.24.0",
            "description": "Fréquence moyenne",
            "unite": "Hz",
            "type": "Qualité",
            "direction": "Fréquence"
        },
        "01001F1800FF": {
            "standard": "1-0:31.24.0",
            "description": "Courant moyen phase 1",
            "unite": "A",
            "type": "Qualité",
            "direction": "I1"
        },
        "0100331800FF": {
            "standard": "1-0:51.24.0",
            "description": "Courant moyen phase 2",
            "unite": "A",
            "type": "Qualité",
            "direction": "I2"
        },
        "0100471800FF": {
            "standard": "1-0:71.24.0",
            "description": "Courant moyen phase 3",
            "unite": "A",
            "type": "Qualité",
            "direction": "I3"
        }
    }

    def _get_reading_type_from_logical_name(self, logical_name: str) -> Optional[str]:
        """Retourne le ReadingType EnergyWorx à partir du logical_name.
        - D'abord via le mapping statique
        - Puis via règle générique pour profils de charge 010063XX00FF (LoadX)
        """
        if not logical_name:
            return None
        # Mapping direct si connu
        mapped = self.OBIS_MAPPING.get(logical_name)
        if mapped:
            return mapped
        # Règle générique: tout 010063XX00FF est un profil de charge A+ IX15m
        # Exemple: 0100630100FF (Load1), 0100630200FF (Load2), 0100630E00FF (Load14)
        if re.fullmatch(r"010063[0-9A-Fa-f]{2}00FF", logical_name):
            return "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0"
        return None
    
    def parse(self, content: str, filename: str) -> FileProcessingResult:
        """Parse un fichier XML MAP110
        
        AMÉLIORATION: Les fichiers E360/E450 contiennent souvent PLUSIEURS types de données:
        - BillingValues (registres totaux ponctuels)
        - ProfileBuffer (profils de charge temporels)
        
        Cette méthode extrait TOUS les types disponibles pour maximiser la couverture.
        """
        errors = []
        warnings = []
        readings = []
        
        try:
            root = ET.fromstring(content)
            
            # Extraction du CLDN
            cldn = self._extract_cldn(root)
            if not cldn:
                errors.append("CLDN manquant dans le fichier XML")
                return FileProcessingResult(filename, False, errors=errors)
            
            # Extraction du timestamp de création/modification
            file_timestamp = self._extract_file_timestamp(root)
            
            # Détection du type de fichier
            file_type = self._detect_file_type(root)
            logger.info(f"Type de fichier détecté: {file_type}")
            
            # NOUVEAU: Extraire TOUS les types de données disponibles
            # Les fichiers E360/E450 peuvent contenir plusieurs types simultanément
            
            # 1. Toujours essayer d'extraire les BillingValues (registres totaux)
            billing_data = self._extract_billing_values(root)
            if billing_data:
                billing_readings = self._create_readings_from_billing(billing_data, cldn, file_timestamp)
                readings.extend(billing_readings)
                logger.info(f"Extrait {len(billing_readings)} lecture(s) de type BillingValues (registres)")
            
            # 2. Extraire les profils selon le type détecté
            channels_count = None
            if file_type == "ProfileBuffer":
                profile_buffer_data, channels_count = self._extract_profile_buffer_data(root)
                if profile_buffer_data:
                    buffer_readings = self._create_readings_from_profile_buffer(profile_buffer_data, cldn, file_timestamp)
                    readings.extend(buffer_readings)
                    logger.info(f"Extrait {len(buffer_readings)} lecture(s) de type ProfileBuffer (profils temporels)")
            elif file_type == "LoadProfile":
                profile_data = self._extract_profile_data(root)
                if profile_data:
                    profile_readings = self._create_readings_from_profile(profile_data, cldn, file_timestamp)
                    readings.extend(profile_readings)
                    logger.info(f"Extrait {len(profile_readings)} lecture(s) de type LoadProfile")
            elif file_type == "BillingValues":
                # BillingValues uniquement (déjà extrait ci-dessus)
                pass
            else:
                warnings.append(f"Type de fichier non standard: {file_type}")
            
            if not readings:
                warnings.append("Aucune lecture valide trouvée")
            
        except ET.ParseError as e:
            errors.append(f"Erreur de parsing XML: {str(e)}")
            return FileProcessingResult(filename, False, errors=errors)
        except Exception as e:
            errors.append(f"Erreur lors du parsing: {str(e)}")
            return FileProcessingResult(filename, False, errors=errors)
        
        return FileProcessingResult(filename, len(errors) == 0, readings, errors, warnings, channels_count)
    
    def _extract_cldn(self, root: ET.Element) -> Optional[str]:
        """Extrait le CLDN du fichier XML"""
        # Recherche dans MAPInfos (priorité)
        map_infos = root.find('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}MAPInfos')
        if map_infos is not None:
            ddid = map_infos.find('{http://tempuri.org/DeviceDescriptionDataSet.xsd}DDID')
            if ddid is not None and ddid.text:
                return ddid.text.strip()
        
        # Recherche dans DDs
        dds = root.find('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}DDs')
        if dds is not None:
            ddid = dds.get('DDID')
            if ddid:
                return ddid.strip()
        
        return None
    
    def _extract_file_timestamp(self, root: ET.Element) -> datetime:
        """Extrait le timestamp de création/modification du fichier"""
        # Recherche du timestamp de modification (priorité)
        map_infos = root.find('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}MAPInfos')
        if map_infos is not None:
            mod_time = map_infos.find('{http://tempuri.org/DeviceDescriptionDataSet.xsd}ModificationDateTime')
            if mod_time is not None and mod_time.text:
                try:
                    # Format: 2025-08-27T12:32:26.7030356+02:00
                    timestamp_str = mod_time.text.strip()
                    # Supprimer les microsecondes si présentes
                    if '.' in timestamp_str and '+' in timestamp_str:
                        timestamp_str = timestamp_str.split('.')[0] + timestamp_str[timestamp_str.find('+'):]
                    elif '.' in timestamp_str and 'Z' in timestamp_str:
                        timestamp_str = timestamp_str.split('.')[0] + 'Z'
                    
                    return datetime.fromisoformat(timestamp_str).astimezone(timezone.utc)
                except ValueError:
                    pass
            
            # Fallback sur le timestamp de création
            creation_time = map_infos.find('{http://tempuri.org/DeviceDescriptionDataSet.xsd}CreationDateTime')
            if creation_time is not None and creation_time.text:
                try:
                    timestamp_str = creation_time.text.strip()
                    if '.' in timestamp_str and '+' in timestamp_str:
                        timestamp_str = timestamp_str.split('.')[0] + timestamp_str[timestamp_str.find('+'):]
                    elif '.' in timestamp_str and 'Z' in timestamp_str:
                        timestamp_str = timestamp_str.split('.')[0] + 'Z'
                    
                    return datetime.fromisoformat(timestamp_str).astimezone(timezone.utc)
                except ValueError:
                    pass
        
        # Fallback sur l'heure actuelle
        return datetime.now(timezone.utc)
    
    def _detect_file_type(self, root: ET.Element) -> str:
        """Détecte le type de fichier XML MAP110"""
        dds = root.find('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}DDs')
        if dds is not None:
            subset = dds.get('DDSubset')
            if subset:
                return subset
        return "Unknown"
    
    def _extract_billing_values(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Extrait les valeurs de facturation (BillingValues) du XML MAP110
        
        AMÉLIORATION: Cherche à la fois .CurrentValue (E570) et .value (E360)
        """
        billing_data = []
        
        # Recherche des objets avec des valeurs de facturation
        objects = root.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Objects')
        
        for obj in objects:
            logical_name = obj.get('ObjectLogicalName')
            object_name = obj.get('ObjectName', '')
            class_id = obj.get('ClassID', '')
            
            # Ne traiter que les objets avec un code OBIS mappé
            if not logical_name or logical_name not in self.OBIS_MAPPING:
                continue
            
            # Les registres d'énergie sont de ClassID = 3
            if class_id != '3':
                continue
            
            # Chercher l'attribut value (priorité 1: .value pour E360, priorité 2: .CurrentValue pour E570)
            value_attr = obj.find('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Attributes[@AttributeName="' + object_name + '.value"]')
            
            if value_attr is None:
                # Fallback sur CurrentValue pour E570
                value_attr = obj.find('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Attributes[@AttributeName="' + object_name + '.CurrentValue"]')
            
            if value_attr is not None:
                # Chercher le champ avec la valeur (peut être .value.0 ou .CurrentValue.0)
                attr_name = value_attr.get('AttributeName', '')
                field = value_attr.find('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Fields[@FieldName="' + attr_name + '.0"]')
                
                if field is not None:
                    field_value = field.get('FieldValue')
                    field_type = field.get('FieldType', '')
                    
                    if field_value and field_value != "0" and field_value != "0000000000000000":
                        try:
                            # Conversion selon le type de champ
                            if field_type in ['UInt32', 'UInt16', 'UInt8', 'Int32', 'Int16', 'Int8']:
                                # Valeur numérique directe
                                decimal_value = int(field_value)
                            elif field_type == 'OctetString' and len(field_value) > 8:
                                # Valeur hexadécimale longue
                                decimal_value = int(field_value, 16)
                            else:
                                # Essayer de convertir en entier
                                decimal_value = int(field_value)
                            
                            billing_data.append({
                                'logical_name': logical_name,
                                'value': decimal_value,
                                'field_type': field_type,
                                'raw_value': field_value
                            })
                            logger.debug(f"Extrait BillingValue pour {object_name} (OBIS: {logical_name}): {decimal_value}")
                            
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Impossible de convertir la valeur {field_value} pour {logical_name}: {e}")
                            continue
        
        return billing_data
    
    def _create_readings_from_billing(self, billing_data: List[Dict[str, Any]], cldn: str, timestamp: datetime) -> List[MeterReading]:
        """Crée des lectures à partir des données de facturation"""
        readings = []
        
        for data_point in billing_data:
            logical_name = data_point['logical_name']
            value = data_point['value']
            
            reading_type = self._get_reading_type_from_logical_name(logical_name)
            if not reading_type:
                continue
            
            # Détermination de l'unité basée sur le décodage OBIS
            decoder_info = self.OBIS_DECODER.get(logical_name)
            unit = decoder_info["unite"] if decoder_info else "kWh"
            
            reading = MeterReading(
                timestamp=timestamp,
                value=value,
                reading_type=reading_type,
                unit=unit,
                cldn=cldn
            )
            readings.append(reading)
        
        return readings
    
    def _create_readings_from_profile(self, profile_data: List[Dict[str, Any]], cldn: str, timestamp: datetime) -> List[MeterReading]:
        """Crée des lectures à partir des données de profil"""
        readings = []
        
        for data_point in profile_data:
            logical_name = data_point['logical_name']
            value = data_point['value']
            point_timestamp = data_point.get('timestamp', timestamp)
            
            reading_type = self._get_reading_type_from_logical_name(logical_name)
            if not reading_type:
                continue
            
            # Détermination de l'unité basée sur le décodage OBIS
            decoder_info = self.OBIS_DECODER.get(logical_name)
            unit = decoder_info["unite"] if decoder_info else "kWh"
            
            reading = MeterReading(
                timestamp=point_timestamp,
                value=value,
                reading_type=reading_type,
                unit=unit,
                cldn=cldn
            )
            readings.append(reading)
        
        return readings
    
    def _extract_profile_data(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Extrait les données de profil de charge (LoadProfile) du XML MAP110"""
        profile_data = []
        
        # Recherche des objets avec des données de profil de charge
        objects = root.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Objects')
        
        for obj in objects:
            logical_name = obj.get('ObjectLogicalName')
            if logical_name and logical_name in self.OBIS_MAPPING:
                # Recherche des attributs avec des valeurs de données de profil
                attributes = obj.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Attributes')
                
                for attr in attributes:
                    # Chercher des attributs de données (pas seulement les métadonnées)
                    attr_name = attr.get('AttributeName', '')
                    if 'value' in attr_name.lower() or 'data' in attr_name.lower() or 'profile' in attr_name.lower():
                        fields = attr.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Fields')
                        
                        for field in fields:
                            field_value = field.get('FieldValue')
                            field_type = field.get('FieldType', '')
                            
                            # Traiter les valeurs hexadécimales ou numériques
                            if field_value and field_value != "0000000000000000":
                                try:
                                    # Conversion selon le type de champ
                                    if field_type == 'DoubleLongUnsigned' or field_type == 'LongUnsigned':
                                        # Valeur hexadécimale à convertir
                                        decimal_value = int(field_value, 16)
                                    elif field_type in ['Int8', 'Int16', 'Int32', 'UInt32', 'UInt16', 'UInt8']:
                                        # Valeur numérique directe
                                        decimal_value = int(field_value)
                                    else:
                                        # Essayer de convertir en entier
                                        decimal_value = int(field_value)
                                    
                                    # Créer un point de données
                                    data_point = {
                                        'logical_name': logical_name,
                                        'value': decimal_value,
                                        'field_type': field_type,
                                        'timestamp': datetime.now(timezone.utc)  # Timestamp par défaut
                                    }
                                    profile_data.append(data_point)
                                    
                                except (ValueError, TypeError) as e:
                                    logger.warning(f"Impossible de convertir la valeur {field_value}: {e}")
                                    continue
        
        return profile_data
    
    def _parse_capture_objects(self, obj: ET.Element, object_name: str) -> Dict[int, str]:
        """
        Parse capture_objects pour déterminer la structure dynamique du buffer
        
        Selon le manuel MAP110, capture_objects définit la structure de chaque ligne :
        Index 0 = Timestamp (Clock)
        Index 1 = Status Word (EDIS)
        Index 2-7 = Valeurs d'énergie (OBIS codes)
        
        Returns:
            Dict mapping index -> logical_name (OBIS code)
        """
        capture_map = {}
        
        # Recherche de l'attribut capture_objects
        capture_objects_attr = obj.find('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Attributes[@AttributeName="' + object_name + '.capture_objects"]')
        
        if capture_objects_attr is None:
            # Fallback : structure par défaut selon le manuel MAP110
            logger.info(f"capture_objects non trouvé pour {object_name}, utilisation de la structure par défaut")
            return {
                0: "0000010000FF",  # Clock (Timestamp)
                1: "0000600A01FF",  # EDIS Status Word
                2: "0100010800FF",  # A+ Total
                3: "0100020800FF",  # A- Total
                4: "0100050800FF",  # Q1 Total
                5: "0100060800FF",  # Q2 Total
                6: "0100070800FF",  # Q3 Total
                7: "0100080800FF",  # Q4 Total
            }
        
        # Parser les champs capture_objects
        # Structure: capture_objects.0 (Array) -> capture_objects.0.N (Struct) -> capture_objects.0.N.logical_name (OctetString)
        namespace = '{http://tempuri.org/DeviceDescriptionDataSet.xsd}'
        
        # Chercher tous les champs logical_name dans capture_objects
        # Format: DD.Profile_LoadX.capture_objects.0.N.logical_name
        # Note: ElementTree ne supporte pas les sélecteurs XPath avec contains(), donc on cherche tous les Fields et on filtre
        all_fields = capture_objects_attr.findall(f'.//{namespace}Fields')
        logical_name_fields = [f for f in all_fields if 'logical_name' in f.get('FieldName', '')]
        
        # Extraire l'index N depuis le nom de champ et trier par cet index numérique
        # Format: DD.Profile_LoadX.capture_objects.0.N.logical_name -> index = N
        indexed_fields = []
        for field in logical_name_fields:
            field_name = field.get('FieldName', '')
            field_type = field.get('FieldType', '')
            logical_name = field.get('FieldValue', '')
            
            if field_type == 'OctetString' and logical_name:
                # Extraire l'index N depuis le nom de champ
                # Ex: DD.Profile_Load2.capture_objects.0.2.logical_name -> index = 2
                try:
                    parts = field_name.split('.')
                    # L'avant-dernier élément devrait être l'index N
                    field_index = int(parts[-2]) if len(parts) >= 2 else index
                    indexed_fields.append((field_index, logical_name))
                except (ValueError, IndexError):
                    # Si on ne peut pas extraire l'index, utiliser l'ordre séquentiel
                    indexed_fields.append((index, logical_name))
                    index += 1
        
        # Trier par index numérique
        indexed_fields.sort(key=lambda x: x[0])
        
        # Construire le mapping
        for field_index, logical_name in indexed_fields:
            capture_map[field_index] = logical_name
            logger.debug(f"  Index {field_index} -> {logical_name}")
        
        if capture_map:
            logger.info(f"Structure capture_objects parsée pour {object_name}: {len(capture_map)} objets")
        else:
            logger.warning(f"Impossible de parser capture_objects pour {object_name}, utilisation de la structure par défaut")
            return {
                0: "0000010000FF",  # Clock
                1: "0000600A01FF",  # Status Word
                2: "0100010800FF",  # A+ Total
                3: "0100020800FF",  # A- Total
                4: "0100050800FF",  # Q1 Total
                5: "0100060800FF",  # Q2 Total
                6: "0100070800FF",  # Q3 Total
                7: "0100080800FF",  # Q4 Total
            }
        
        return capture_map
    
    def _interpret_status_word(self, status_value: int) -> Dict[str, Any]:
        """
        Interprète le Status Word (EDIS) selon le manuel MAP110
        
        Selon le manuel MAP110 (chapitre 7.1.3, pages 1758-1759):
        - Bit 0: Fin d'intervalle
        - Bit 1: Données invalides
        - Bit 2: Coupure de courant
        - Bit 3: Horloge ajustée
        - Bit 4: État été/hiver (1 = été, 0 = hiver)
        
        Args:
            status_value: Valeur UInt8 du status word
        
        Returns:
            Dict avec les flags interprétés
        """
        flags = {
            'raw_value': status_value,
            'end_of_interval': bool(status_value & 0x01),      # Bit 0: Fin d'intervalle
            'invalid_data': bool(status_value & 0x02),        # Bit 1: Données invalides
            'power_failure': bool(status_value & 0x04),        # Bit 2: Coupure de courant
            'clock_adjusted': bool(status_value & 0x08),      # Bit 3: Horloge ajustée
            'summer_time': bool(status_value & 0x10),         # Bit 4: État été/hiver (1=été, 0=hiver)
        }
        
        return flags
    
    def _extract_profile_buffer_data(self, root: ET.Element) -> tuple[List[Dict[str, Any]], int]:
        """Extrait les données de profil de charge (ProfileBuffer) du XML MAP110
        
        Version corrigée selon le manuel MAP110:
        - Structure correcte: Index 0=Timestamp, 1=Status, 2-7=Valeurs énergie
        - Conversion Wh → kWh
        - Extraction du Status Word pour qualité des données
        - Parsing dynamique de capture_objects
        
        Returns:
            Tuple (profile_buffer_data, max_channels_count)
            - profile_buffer_data: Liste des données extraites
            - max_channels_count: Nombre maximum de codes OBIS uniques trouvés dans capture_objects
        """
        profile_buffer_data = []
        max_channels_count = 0
        
        # Recherche des objets Profile_Load avec des données de buffer
        objects = root.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Objects')
        logger.info(f"Trouvé {len(objects)} objet(s) dans le fichier XML")
        
        for obj in objects:
            logical_name = obj.get('ObjectLogicalName')
            object_name = obj.get('ObjectName', '')
            
            if not logical_name:
                continue
            
            # Log tous les codes OBIS détectés (même ceux non mappés)
            reading_type = self._get_reading_type_from_logical_name(logical_name)
            if reading_type:
                logger.info(f"Objet {object_name} (OBIS: {logical_name}) -> ReadingType mappé")
            else:
                logger.warning(f"Objet {object_name} (OBIS: {logical_name}) -> Pas de mapping ReadingType")
            
            # Recherche de l'attribut buffer
            buffer_attr = obj.find('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Attributes[@AttributeName="' + object_name + '.buffer"]')
            
            if buffer_attr is not None:
                # Parser capture_objects pour déterminer la structure
                capture_map = self._parse_capture_objects(obj, object_name)
                
                # Compter le nombre de codes OBIS uniques (exclure Timestamp et Status Word)
                # Les indices 0 et 1 sont toujours Timestamp et Status Word
                value_codes = {code for idx, code in capture_map.items() if idx >= 2}
                channels_count = len(value_codes)
                if channels_count > max_channels_count:
                    max_channels_count = channels_count
                logger.info(f"Nombre de canaux détectés dans capture_objects pour {object_name}: {channels_count}")
                logger.debug(f"  Indices dans capture_map: {sorted(capture_map.keys())}")
                logger.debug(f"  Codes OBIS valeurs (indices >= 2): {sorted(value_codes)}")
                
                # Vérifier si c'est une structure Selector1.Response (fichiers E450)
                selector_response_fields = buffer_attr.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Fields[@FieldName="' + object_name + '.buffer.Selector1.Response"]')
                
                if selector_response_fields:
                    # Structure E450 avec Selector1.Response
                    logger.info(f"Détection structure E450 pour {object_name}")
                    profile_buffer_data.extend(self._extract_e450_profile_data(buffer_attr, logical_name, object_name))
                else:
                    # Structure E360/E570 avec structures directes
                    logger.info(f"Détection structure E360/E570 pour {object_name}")
                    
                    # Optimisation: construire un index des Fields par ParentFieldName une seule fois
                    all_fields = buffer_attr.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Fields')
                    fields_by_parent = defaultdict(list)
                    
                    for field in all_fields:
                        parent = field.get('ParentFieldName', '')
                        if parent:
                            fields_by_parent[parent].append({
                                'name': field.get('FieldName', ''),
                                'value': field.get('FieldValue'),
                                'type': field.get('FieldType', '')
                            })
                    
                    # Recherche des structures de type Struct qui représentent des enregistrements de profil
                    buffer_fields = buffer_attr.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Fields[@FieldType="Struct"]')
                    logger.info(f"Trouvé {len(buffer_fields)} structure(s) de données pour {object_name}")
                    
                    records_extracted = 0
                    for struct_field in buffer_fields:
                        struct_field_name = struct_field.get('FieldName', '')
                        
                        # Utiliser l'index pour récupérer les champs enfants
                        child_fields = fields_by_parent.get(struct_field_name, [])
                        
                        if not child_fields:
                            continue
                        
                        # Structure correcte selon le manuel MAP110:
                        # Index 0 = Timestamp (OctetString)
                        # Index 1 = Status Word (UInt8)
                        # Index 2-7 = Valeurs d'énergie (UInt32)
                        timestamp_field = None
                        status_value = None
                        value_fields = []
                        
                        for field in child_fields:
                            field_name = field['name']
                            field_value = field['value']
                            field_type = field['type']
                            
                            # Extraire l'index du nom de champ (ex: buffer.0.3.2 -> index 2)
                            try:
                                field_index = int(field_name.split('.')[-1])
                            except (ValueError, IndexError):
                                continue
                            
                            # Index 0 = Timestamp
                            if field_index == 0 and field_type == 'OctetString':
                                timestamp_field = field_value
                            
                            # Index 1 = Status Word
                            elif field_index == 1 and field_type == 'UInt8':
                                try:
                                    status_value = int(field_value)
                                except (ValueError, TypeError):
                                    pass
                            
                            # Index 2+ = Valeurs (UInt32, UInt16, etc.) - Structure dynamique selon capture_objects
                            # Le nombre de champs varie selon le profil :
                            # - Load1 : indices 2-7 (6 canaux d'énergie)
                            # - Load2 : indices 2-13 (12 canaux d'énergie Rated)
                            # - Load4 : indices 2-8 (7 canaux : tensions UInt16, fréquence, courants)
                            elif field_index >= 2 and field_type in ('UInt32', 'UInt16', 'Int32', 'Int16'):
                                if field_value is not None:
                                    try:
                                        value_int = int(field_value)
                                        # Mapper l'index au code OBIS via capture_map
                                        obis_code = capture_map.get(field_index)
                                        if obis_code:
                                            # Vérifier si le code OBIS est mappé à un reading_type
                                            # Si non mappé, on l'extrait quand même mais avec un warning
                                            value_fields.append({
                                                'value': value_int,
                                                'field_index': field_index,
                                                'obis_code': obis_code,
                                                'field_type': field_type
                                            })
                                        else:
                                            logger.debug(f"Index {field_index} non présent dans capture_map pour {object_name}")
                                    except (ValueError, TypeError):
                                        logger.warning(f"Valeur invalide pour {field_name}: {field_value}")
                                        continue
                        
                        # Si on a un timestamp et des valeurs, créer des points de données
                        if timestamp_field and value_fields:
                            try:
                                # Décoder le timestamp hexadécimal
                                timestamp = self._decode_profile_timestamp(timestamp_field)
                                
                                # Interpréter le status word si présent
                                status_flags = None
                                if status_value is not None:
                                    status_flags = self._interpret_status_word(status_value)
                                    # Vérifier si les données sont invalides
                                    if status_flags.get('invalid_data', False):
                                        logger.warning(f"Données invalides détectées (Status: {status_value}) pour timestamp {timestamp}")
                                
                                # Créer un point de données pour chaque valeur
                                for value_info in value_fields:
                                    profile_buffer_data.append({
                                        'logical_name': value_info['obis_code'],  # Utiliser le code OBIS du capture_objects
                                        'value': value_info['value'],  # Valeur brute (sera convertie selon l'unité)
                                        'timestamp': timestamp,
                                        'field_index': value_info['field_index'],
                                        'field_type': value_info['field_type'],  # UInt16, UInt32, etc.
                                        'raw_timestamp': timestamp_field,
                                        'status': status_flags
                                    })
                                
                                records_extracted += 1
                                    
                            except Exception as e:
                                logger.warning(f"Impossible de décoder le timestamp {timestamp_field}: {e}")
                                continue
                    
                    logger.info(f"Extrait {records_extracted} enregistrement(s) avec timestamps pour {object_name}")
        
        logger.info(f"Total de {len(profile_buffer_data)} point(s) de données extraits")
        logger.info(f"Nombre maximum de canaux détectés: {max_channels_count}")
        return profile_buffer_data, max_channels_count
    
    def _extract_e450_profile_data(self, buffer_attr: ET.Element, logical_name: str, object_name: str) -> List[Dict[str, Any]]:
        """Extrait les données de profil de charge des fichiers E450 (structure Selector1.Response)
        
        Version optimisée:
        - Construit un index des Fields pour éviter les recherches répétées
        - Logging détaillé
        """
        e450_data = []
        
        # Optimisation: construire un index des Fields par ParentFieldName une seule fois
        all_fields = buffer_attr.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Fields')
        fields_by_parent = defaultdict(list)
        
        for field in all_fields:
            parent = field.get('ParentFieldName', '')
            if parent:
                fields_by_parent[parent].append({
                    'name': field.get('FieldName', ''),
                    'value': field.get('FieldValue'),
                    'type': field.get('FieldType', '')
                })
        
        # Recherche des structures Response dans Selector1.Response
        response_fields = buffer_attr.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Fields[@FieldName="' + object_name + '.buffer.Selector1.Response"]')
        
        if not response_fields:
            logger.warning(f"Aucune structure Selector1.Response trouvée pour {object_name}")
            return e450_data
        
        # Recherche des sous-structures Response.X
        sub_response_fields = buffer_attr.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Fields[@FieldType="Struct"]')
        
        records_extracted = 0
        for sub_field in sub_response_fields:
            field_name = sub_field.get('FieldName', '')
            parent_field = sub_field.get('ParentFieldName', '')
            
            # Vérifier si c'est une structure Response.X
            if parent_field == object_name + '.buffer.Selector1.Response' and 'Response.' in field_name:
                # Utiliser l'index pour récupérer les champs enfants
                child_fields = fields_by_parent.get(field_name, [])
                
                if not child_fields:
                    continue
                
                timestamp_field = None
                value_fields = []
                
                for field in child_fields:
                    field_name_inner = field['name']
                    field_value = field['value']
                    field_type = field['type']
                    
                    # Le champ .0 contient le timestamp
                    if field_name_inner.endswith('.0') and field_type == 'OctetString':
                        timestamp_field = field_value
                    # Les champs .2 à .13 contiennent les valeurs (profils étendus)
                    elif field_name_inner.endswith(('.2', '.3', '.4', '.5', '.6', '.7', '.8', '.9', '.10', '.11', '.12', '.13')) and field_type in ('UInt32', 'UInt16'):
                        if field_value and field_value != "0":
                            try:
                                value_fields.append({
                                    'value': int(field_value),
                                    'field_index': field_name_inner.split('.')[-1]
                                })
                            except (ValueError, TypeError):
                                logger.warning(f"Valeur invalide pour {field_name_inner}: {field_value}")
                                continue
                
                # Si on a un timestamp et des valeurs, créer des points de données
                if timestamp_field and value_fields:
                    try:
                        # Décoder le timestamp hexadécimal
                        timestamp = self._decode_profile_timestamp(timestamp_field)
                        
                        # Créer un point de données pour chaque valeur non-nulle
                        for value_info in value_fields:
                            e450_data.append({
                                'logical_name': logical_name,
                                'value': value_info['value'],
                                'timestamp': timestamp,
                                'field_index': value_info['field_index'],
                                'raw_timestamp': timestamp_field
                            })
                        
                        records_extracted += 1
                            
                    except Exception as e:
                        logger.warning(f"Impossible de décoder le timestamp {timestamp_field}: {e}")
                        continue
        
        logger.info(f"Extrait {records_extracted} enregistrement(s) E450 pour {object_name}")
        return e450_data
    
    def _decode_profile_timestamp(self, hex_timestamp: str) -> datetime:
        """
        Décode un timestamp hexadécimal de profil de charge selon le format DLMS standard (12 octets)
        
        Structure DLMS confirmée (selon spécifications et manuel MAP110):
        - Octets 0-1: Année (UInt16)
        - Octet 2: Mois (UInt8)
        - Octet 3: Jour (UInt8)
        - Octet 4: Jour de semaine (0xFF = non spécifié)
        - Octet 5: Heure (UInt8)
        - Octet 6: Minute (UInt8)
        - Octet 7: Seconde (UInt8)
        - Octet 8: Centièmes de seconde (UInt8)
        - Octets 9-10: Deviation UTC (Int16 signé, en minutes)
        - Octet 11: Status byte (bit flags, bit 4 = DST)
        
        Exemple: 07E7070A01111E0000FF8880
        -> 2023-07-10 17:30:00.00 locale, deviation -120 min = UTC-02:00
        -> UTC: 2023-07-10 19:30:00
        """
        try:
            # Vérifier la longueur minimale (12 octets = 24 caractères hex)
            if len(hex_timestamp) < 24:
                raise ValueError(f"Timestamp hexadécimal trop court: {len(hex_timestamp)} caractères (attendu: 24)")
            
            # Extraire les composants selon la structure DLMS
            year_hex = hex_timestamp[0:4]      # Octets 0-1: Année
            month_hex = hex_timestamp[4:6]    # Octet 2: Mois
            day_hex = hex_timestamp[6:8]      # Octet 3: Jour
            weekday_hex = hex_timestamp[8:10] # Octet 4: Jour de semaine (ignoré si 0xFF)
            hour_hex = hex_timestamp[10:12]   # Octet 5: Heure
            minute_hex = hex_timestamp[12:14] # Octet 6: Minute
            second_hex = hex_timestamp[14:16]  # Octet 7: Seconde
            centiseconds_hex = hex_timestamp[16:18]  # Octet 8: Centièmes de seconde
            deviation_hex = hex_timestamp[18:22]    # Octets 9-10: Deviation UTC (Int16 signé)
            status_hex = hex_timestamp[22:24]       # Octet 11: Status byte
            
            # Conversion hexadécimale
            year = int(year_hex, 16)
            month = int(month_hex, 16)
            day = int(day_hex, 16)
            hour = int(hour_hex, 16)
            minute = int(minute_hex, 16)
            second = int(second_hex, 16)
            centiseconds = int(centiseconds_hex, 16)
            
            # Décoder la deviation UTC (Int16 signé, en minutes)
            deviation_raw = int(deviation_hex, 16)
            # Conversion Int16 signé : si > 32767, c'est négatif (complément à 2)
            if deviation_raw > 32767:
                deviation_minutes = deviation_raw - 65536
            else:
                deviation_minutes = deviation_raw
            
            # Décoder le status byte
            status_byte = int(status_hex, 16)
            dst_active = bool(status_byte & 0x10)  # Bit 4: DST (1 = été, 0 = hiver)
            
            # Créer le datetime avec l'heure locale du compteur
            # Les centièmes de seconde sont ignorés (datetime ne les supporte pas directement)
            timestamp_local = datetime(year, month, day, hour, minute, second)
            
            # Convertir en UTC en appliquant la deviation
            # La deviation est en minutes, négative signifie UTC derrière l'heure locale
            # Exemple: deviation = -120 minutes = UTC-02:00
            # Pour convertir l'heure locale en UTC, on soustrait la deviation (négative = on avance)
            from datetime import timedelta
            timestamp_utc = timestamp_local - timedelta(minutes=deviation_minutes)
            timestamp_utc = timestamp_utc.replace(tzinfo=timezone.utc)
            
            # Log pour debug (peut être désactivé en production)
            logger.debug(f"Timestamp décodé: {timestamp_local} (deviation: {deviation_minutes} min = UTC{deviation_minutes//60:+d}:{abs(deviation_minutes%60):02d}, DST: {dst_active}, status: 0x{status_hex}) -> UTC: {timestamp_utc}")
            
            return timestamp_utc
            
        except Exception as e:
            logger.warning(f"Erreur lors du décodage du timestamp {hex_timestamp}: {e}")
            # Fallback sur l'heure actuelle
            return datetime.now(timezone.utc)
    
    def _create_readings_from_profile_buffer(self, profile_buffer_data: List[Dict[str, Any]], cldn: str, file_timestamp: datetime) -> List[MeterReading]:
        """
        Crée des lectures à partir des données de profil de charge
        
        CORRECTION IMPORTANTE selon le manuel MAP110:
        - Les valeurs sont en Wh (Watt-heure), pas kWh
        - Conversion Wh → kWh (diviser par 1000)
        - Scaler = 0 signifie pas de mise à l'échelle (valeurs directes en Wh)
        - Les valeurs sont CUMULATIVES (absolues), pas incrémentales
          Selon le manuel MAP110, le groupe D=8 correspond à "Energy register (cumulative)"
        
        AMÉLIORATION: Support des différents types de champs (UInt16 pour tensions, etc.)
        """
        readings = []
        
        for data_point in profile_buffer_data:
            logical_name = data_point['logical_name']
            raw_value = data_point['value']
            field_type = data_point.get('field_type', 'UInt32')
            timestamp = data_point['timestamp']
            status_flags = data_point.get('status')
            
            # Vérifier si les données sont invalides selon le status word
            if status_flags and status_flags.get('invalid_data', False):
                logger.warning(f"Donnée invalide ignorée (Status: {status_flags.get('raw_value')}) pour {logical_name} à {timestamp}")
                continue
            
            reading_type = self._get_reading_type_from_logical_name(logical_name)
            if not reading_type:
                # Si le code OBIS n'est pas mappé, on ne crée pas de lecture
                # Mais on log pour information
                logger.debug(f"Code OBIS non mappé ignoré: {logical_name}")
                continue
            
            # Déterminer l'unité et la conversion selon le type de mesure
            decoder_info = self.OBIS_DECODER.get(logical_name)
            if decoder_info:
                unit = decoder_info["unite"]
                # Pour les mesures d'énergie (kWh, kvarh), conversion Wh → kWh
                if unit in ("kWh", "kvarh"):
                    value = raw_value / 1000.0
                # Pour les tensions (V), les valeurs sont en UInt16 avec scaler -1 = 0.1V
                elif unit == "V" and field_type == "UInt16":
                    # Scaler -1 signifie que la valeur est en 0.1V, donc diviser par 10
                    value = raw_value / 10.0
                # Pour les courants (A), vérifier si UInt16 avec scaler (généralement scaler -2 = 0.01A)
                elif unit == "A" and field_type == "UInt16":
                    # Par défaut, supposer scaler -2 (0.01A) pour les courants
                    # Si la valeur est > 10000, c'est probablement en 0.1A (scaler -1)
                    if raw_value > 10000:
                        value = raw_value / 10.0  # Scaler -1
                    else:
                        value = raw_value / 100.0  # Scaler -2 (par défaut)
                # Pour la fréquence (Hz), peut être UInt16 ou UInt32
                # Si UInt32 avec valeur < 1000, probablement scaler -1 (0.1Hz)
                # Si UInt16, probablement scaler -2 (0.01Hz)
                elif unit == "Hz":
                    if field_type == "UInt32" and raw_value < 1000:
                        # Scaler -1 signifie que la valeur est en 0.1Hz, donc diviser par 10
                        value = raw_value / 10.0
                    elif field_type == "UInt16":
                        # Scaler -2 signifie que la valeur est en 0.01Hz, donc diviser par 100
                        value = raw_value / 100.0
                    else:
                        # Par défaut, supposer scaler -1
                        value = raw_value / 10.0
                # Pour les autres types, utiliser la valeur telle quelle
                else:
                    value = float(raw_value)
            else:
                # Par défaut, supposer que c'est de l'énergie en Wh
                unit = "kWh"
                value = raw_value / 1000.0
            
            # Déterminer la qualité selon le status word
            quality = "1.4.9"  # Par défaut: bonne qualité
            if status_flags:
                if status_flags.get('power_failure', False):
                    quality = "1.4.8"  # Qualité dégradée (coupure de courant)
                elif status_flags.get('clock_adjusted', False):
                    quality = "1.4.10"  # Horloge ajustée
            
            reading = MeterReading(
                timestamp=timestamp,
                value=value,  # Valeur convertie selon le type
                reading_type=reading_type,
                unit=unit,
                quality=quality,
                cldn=cldn
            )
            readings.append(reading)
        
        return readings
    
    def decode_obis_code(self, obis_code: str) -> Dict[str, str]:
        """Décode un code OBIS en format lisible"""
        decoder_info = self.OBIS_DECODER.get(obis_code)
        if decoder_info:
            return {
                "code_hex": obis_code,
                "code_standard": decoder_info["standard"],
                "description": decoder_info["description"],
                "unite": decoder_info["unite"],
                "type": decoder_info["type"],
                "direction": decoder_info["direction"]
            }
        else:
            return {
                "code_hex": obis_code,
                "code_standard": "INCONNU",
                "description": "Code OBIS non reconnu",
                "unite": "?",
                "type": "?",
                "direction": "?"
            }
    

class BlueLinkExcelParser:
    """Parser pour les fichiers Excel BlueLink"""
    
    def parse(self, content: bytes, filename: str) -> FileProcessingResult:
        """Parse un fichier Excel BlueLink"""
        errors = []
        warnings = []
        readings = []
        
        try:
            # Lecture du fichier Excel
            excel_file = pd.ExcelFile(io.BytesIO(content))
            
            # Traitement de chaque feuille
            for sheet_name in excel_file.sheet_names:
                try:
                    df = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name)
                    sheet_readings = self._parse_excel_sheet(df, sheet_name, filename)
                    readings.extend(sheet_readings)
                except Exception as e:
                    errors.append(f"Erreur dans la feuille {sheet_name}: {str(e)}")
            
            if not readings:
                warnings.append("Aucune lecture valide trouvée")
            
        except Exception as e:
            errors.append(f"Erreur lors du parsing Excel: {str(e)}")
            return FileProcessingResult(filename, False, errors=errors)
        
        return FileProcessingResult(filename, len(errors) == 0, readings, errors, warnings)
    
    def _parse_excel_sheet(self, df: pd.DataFrame, sheet_name: str, filename: str) -> List[MeterReading]:
        """Parse une feuille Excel"""
        readings = []
        
        # Recherche des colonnes de date et de valeurs
        date_cols = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
        value_cols = [col for col in df.columns if any(obis in col for obis in ['1.8.0', '2.8.0', '5.8.0', '6.8.0'])]
        
        if not date_cols or not value_cols:
            return readings
        
        # Extraction du CLDN (première valeur non-nulle de la première colonne)
        cldn = str(df.iloc[0, 0]) if not pd.isna(df.iloc[0, 0]) else ""
        
        for _, row in df.iterrows():
            try:
                # Extraction de la date
                date_value = None
                for date_col in date_cols:
                    if not pd.isna(row[date_col]):
                        date_value = pd.to_datetime(row[date_col])
                        break
                
                if date_value is None:
                    continue
                
                # Conversion en UTC
                if date_value.tzinfo is None:
                    date_value = date_value.replace(tzinfo=timezone.utc)
                else:
                    date_value = date_value.astimezone(timezone.utc)
                
                # Extraction des valeurs
                for value_col in value_cols:
                    if not pd.isna(row[value_col]):
                        value = float(row[value_col])
                        
                        # Mapping OBIS basé sur le nom de la colonne
                        reading_type = self._get_reading_type_from_column(value_col)
                        unit = "kWh" if "1.8.0" in value_col or "2.8.0" in value_col else "kvarh"
                        
                        reading = MeterReading(
                            timestamp=date_value,
                            value=value,
                            reading_type=reading_type,
                            unit=unit,
                            cldn=cldn
                        )
                        readings.append(reading)
            
            except Exception:
                continue
        
        return readings
    
    def _get_reading_type_from_column(self, column_name: str) -> str:
        """Détermine le type de lecture à partir du nom de colonne"""
        if "1.8.0" in column_name:
            return "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.73.0"  # A+ IX15m
        elif "2.8.0" in column_name:
            return "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.74.0"  # A- IX15m
        elif "5.8.0" in column_name:
            return "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.77.0"  # Q+ IX15m
        elif "6.8.0" in column_name:
            return "0.0.4.1.15.1.12.0.0.0.0.2.0.0.0.0.78.0"  # Q- IX15m
        else:
            return ""

class FileProcessor:
    """Processeur principal pour tous les types de fichiers"""
    
    def __init__(self):
        self.csv_parser = BlueLinkCSVParser()
        self.xml_parser = MAP110XMLParser()
        self.excel_parser = BlueLinkExcelParser()
    
    def process_file(self, file_content, filename: str) -> FileProcessingResult:
        """Traite un fichier selon son type"""
        file_ext = filename.lower().split('.')[-1]
        
        try:
            # Décoder le contenu si nécessaire
            if isinstance(file_content, bytes):
                content = self._decode_with_fallback(file_content)
            else:
                content = file_content
            
            if file_ext == 'csv':
                return self.csv_parser.parse(content, filename)
            elif file_ext in ['xml']:
                return self.xml_parser.parse(content, filename)
            elif file_ext in ['xlsx', 'xls']:
                # Pour Excel, on peut passer le contenu tel quel
                if isinstance(file_content, bytes):
                    return self.excel_parser.parse(file_content, filename)
                else:
                    # Si c'est une string, on doit la convertir en bytes
                    return self.excel_parser.parse(content.encode('utf-8'), filename)
            else:
                return FileProcessingResult(filename, False, errors=[f"Format de fichier non supporté: {file_ext}"])
        
        except UnicodeDecodeError as e:
            return FileProcessingResult(filename, False, errors=[f"Erreur d'encodage du fichier: {str(e)}"])
        except Exception as e:
            return FileProcessingResult(filename, False, errors=[f"Erreur lors du traitement: {str(e)}"])
    
    def _decode_with_fallback(self, file_content: bytes) -> str:
        """Décode le contenu avec gestion des erreurs d'encodage"""
        encodings_to_try = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
        
        for encoding in encodings_to_try:
            try:
                content = file_content.decode(encoding)
                if encoding != 'utf-8':
                    logger.info(f"Fichier décodé avec l'encodage: {encoding}")
                return content
            except UnicodeDecodeError:
                continue
        
        # Dernier recours: ignorer les erreurs
        logger.warning("Impossible de décoder le fichier, utilisation du mode 'ignore'")
        return file_content.decode('utf-8', errors='ignore')
    
    def process_zip(self, zip_content: bytes, zip_filename: str) -> List[FileProcessingResult]:
        """Traite un fichier ZIP"""
        results = []
        
        try:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_file:
                for file_info in zip_file.filelist:
                    if not file_info.is_dir():
                        filename = file_info.filename
                        file_ext = filename.lower().split('.')[-1]
                        
                        if file_ext in ['csv', 'xml', 'xlsx', 'xls']:
                            try:
                                file_content = zip_file.read(file_info)
                                result = self.process_file(file_content, filename)
                                results.append(result)
                            except Exception as e:
                                error_result = FileProcessingResult(filename, False, errors=[f"Erreur lors de l'extraction: {str(e)}"])
                                results.append(error_result)
                        else:
                            warning_result = FileProcessingResult(filename, False, warnings=[f"Format de fichier ignoré: {file_ext}"])
                            results.append(warning_result)
        
        except zipfile.BadZipFile:
            error_result = FileProcessingResult(zip_filename, False, errors=["Fichier ZIP corrompu"])
            results.append(error_result)
        except Exception as e:
            error_result = FileProcessingResult(zip_filename, False, errors=[f"Erreur lors du traitement du ZIP: {str(e)}"])
            results.append(error_result)
        
        return results
