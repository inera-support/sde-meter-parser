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
                 errors: List[str] = None, warnings: List[str] = None):
        self.filename = filename
        self.success = success
        self.readings = readings or []
        self.errors = errors or []
        self.warnings = warnings or []

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
    
    # Mapping étendu des codes OBIS MAP110 vers EnergyWorx
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
    }
    
    def parse(self, content: str, filename: str) -> FileProcessingResult:
        """Parse un fichier XML MAP110"""
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
            
            # Extraction des données de profil
            profile_data = self._extract_profile_data(root)
            
            for data_point in profile_data:
                try:
                    reading = self._create_reading_from_profile(data_point, cldn)
                    if reading:
                        readings.append(reading)
                except Exception as e:
                    errors.append(f"Erreur lors du traitement des données de profil: {str(e)}")
            
            if not readings:
                warnings.append("Aucune lecture valide trouvée")
            
        except ET.ParseError as e:
            errors.append(f"Erreur de parsing XML: {str(e)}")
            return FileProcessingResult(filename, False, errors=errors)
        except Exception as e:
            errors.append(f"Erreur lors du parsing: {str(e)}")
            return FileProcessingResult(filename, False, errors=errors)
        
        return FileProcessingResult(filename, len(errors) == 0, readings, errors, warnings)
    
    def _extract_cldn(self, root: ET.Element) -> Optional[str]:
        """Extrait le CLDN du fichier XML"""
        # Recherche dans MAPInfos
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
    
    def _extract_profile_data(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Extrait les données de profil du XML MAP110"""
        profile_data = []
        
        # Recherche des objets avec des données de profil
        objects = root.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Objects')
        
        for obj in objects:
            logical_name = obj.get('ObjectLogicalName')
            if logical_name and logical_name in self.OBIS_MAPPING:
                # Recherche des attributs avec des valeurs de données
                attributes = obj.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Attributes')
                
                for attr in attributes:
                    # Chercher des attributs de données (pas seulement les métadonnées)
                    attr_name = attr.get('AttributeName', '')
                    if 'value' in attr_name.lower() or 'data' in attr_name.lower():
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
                                    elif field_type in ['Int8', 'Int16', 'Int32']:
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
        
        # Si aucune donnée de profil trouvée, essayer de chercher des données de registre
        if not profile_data:
            profile_data = self._extract_register_data(root)
        
        return profile_data
    
    def _extract_register_data(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Extrait les données de registre du XML MAP110"""
        register_data = []
        
        # Recherche des objets de registre d'énergie
        objects = root.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Objects')
        
        for obj in objects:
            logical_name = obj.get('ObjectLogicalName')
            if logical_name and logical_name in self.OBIS_MAPPING:
                # Chercher des attributs avec des valeurs de registre
                attributes = obj.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Attributes')
                
                for attr in attributes:
                    # Chercher des attributs de valeur (pas les métadonnées)
                    attr_name = attr.get('AttributeName', '')
                    if 'value' in attr_name.lower() or 'register' in attr_name.lower():
                        fields = attr.findall('.//{http://tempuri.org/DeviceDescriptionDataSet.xsd}Fields')
                        
                        for field in fields:
                            field_value = field.get('FieldValue')
                            if field_value and field_value != "0000000000000000":
                                try:
                                    # Essayer de convertir la valeur
                                    if field_value.startswith('0x') or len(field_value) > 8:
                                        # Valeur hexadécimale
                                        decimal_value = int(field_value, 16)
                                    else:
                                        # Valeur numérique
                                        decimal_value = int(field_value)
                                    
                                    register_data.append({
                                        'logical_name': logical_name,
                                        'value': decimal_value,
                                        'timestamp': datetime.now(timezone.utc)
                                    })
                                    
                                except (ValueError, TypeError):
                                    continue
        
        return register_data
    
    def _create_reading_from_profile(self, data_point: Dict[str, Any], cldn: str) -> Optional[MeterReading]:
        """Crée une lecture à partir des données de profil"""
        logical_name = data_point['logical_name']
        value = data_point['value']
        timestamp = data_point['timestamp']
        
        reading_type = self.OBIS_MAPPING.get(logical_name)
        if not reading_type:
            return None
        
        # Détermination de l'unité
        unit = "kWh" if "0100010800FF" in logical_name or "0100020800FF" in logical_name else "kvarh"
        
        return MeterReading(
            timestamp=timestamp,
            value=value,
            reading_type=reading_type,
            unit=unit,
            cldn=cldn
        )

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
    
    def process_file(self, file_content: bytes, filename: str) -> FileProcessingResult:
        """Traite un fichier selon son type"""
        file_ext = filename.lower().split('.')[-1]
        
        try:
            if file_ext == 'csv':
                content = self._decode_with_fallback(file_content)
                return self.csv_parser.parse(content, filename)
            elif file_ext in ['xml']:
                content = self._decode_with_fallback(file_content)
                return self.xml_parser.parse(content, filename)
            elif file_ext in ['xlsx', 'xls']:
                return self.excel_parser.parse(file_content, filename)
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
