"""
Module de visualisation pour les données de compteurs
Génère des graphiques de charge optimisés avec détection des trous
Optimisé avec WebGL, downsampling adaptatif et cache
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from parsers import MeterReading
import numpy as np
import hashlib

# Cache global pour les calculs coûteux (limité à 50 entrées pour éviter la surcharge mémoire)
_computation_cache = {}
_MAX_CACHE_SIZE = 50


def _get_cache_key(readings: List[MeterReading], interval_minutes: int) -> str:
    """Génère une clé de cache unique basée sur les lectures et l'intervalle"""
    if not readings:
        return "empty"
    
    # Créer un hash basé sur les timestamps et valeurs
    data_str = f"{len(readings)}_{readings[0].timestamp}_{readings[-1].timestamp}_{interval_minutes}"
    return hashlib.md5(data_str.encode()).hexdigest()


def _adaptive_downsample(df: pd.DataFrame, max_points: int = 50000) -> pd.DataFrame:
    """
    Downsampling adaptatif intelligent qui préserve les caractéristiques importantes
    
    Stratégie:
    - Si < max_points: garder tous les points
    - Sinon: utiliser une méthode de réduction qui préserve les variations importantes
    """
    if len(df) <= max_points:
        return df
    
    # Trier par timestamp
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    # Calculer le ratio de réduction
    ratio = len(df) / max_points
    
    # Méthode 1: Réduction uniforme simple (rapide)
    if ratio <= 2:
        step = int(ratio)
        return df.iloc[::step].copy()
    
    # Méthode 2: Réduction adaptative basée sur les variations (plus intelligent)
    # Garder les points avec de grandes variations
    df['value_diff'] = df['value'].diff().abs()
    
    # Trier par différence pour garder les points importants
    df_sorted = df.sort_values('value_diff', ascending=False)
    
    # Garder les top max_points points avec les plus grandes variations
    important_points = df_sorted.head(max_points // 2)
    
    # Ajouter des points uniformément espacés pour la continuité
    uniform_points = df.iloc[::int(ratio * 2)].copy()
    
    # Combiner et dédupliquer
    combined = pd.concat([important_points, uniform_points]).drop_duplicates(subset=['timestamp'])
    combined = combined.sort_values('timestamp').reset_index(drop=True)
    
    # Si encore trop de points, réduire uniformément
    if len(combined) > max_points:
        step = len(combined) // max_points
        combined = combined.iloc[::step]
    
    return combined.drop(columns=['value_diff'], errors='ignore')


def detect_missing_intervals(readings: List[MeterReading], interval_minutes: int = 15, use_cache: bool = True) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Détecte les intervalles manquants dans les données (avec cache)
    
    Args:
        readings: Liste des lectures
        interval_minutes: Intervalle attendu entre les mesures (défaut: 15 minutes)
        use_cache: Utiliser le cache pour accélérer les calculs répétés
    
    Returns:
        Tuple (df_complete, df_missing):
        - df_complete: DataFrame avec toutes les données (réelles + manquantes)
        - df_missing: DataFrame avec uniquement les intervalles manquants
    """
    if not readings:
        return pd.DataFrame(), pd.DataFrame()
    
    # Vérifier le cache
    if use_cache:
        cache_key = _get_cache_key(readings, interval_minutes)
        if cache_key in _computation_cache:
            cached_result = _computation_cache[cache_key]
            return cached_result['df_complete'].copy(), cached_result['df_missing'].copy()
    
    # Créer un DataFrame avec les données réelles
    df_real = pd.DataFrame([
        {
            'timestamp': r.timestamp,
            'value': r.value,
            'is_missing': False
        }
        for r in readings
    ])
    
    if df_real.empty:
        return pd.DataFrame(), pd.DataFrame()
    
    # Trier par timestamp
    df_real = df_real.sort_values('timestamp').reset_index(drop=True)
    
    # Calculer la période totale
    start_time = df_real['timestamp'].min()
    end_time = df_real['timestamp'].max()
    
    # Générer toutes les dates attendues (96 par jour = 15 minutes d'intervalle)
    expected_times = pd.date_range(
        start=start_time,
        end=end_time,
        freq=f'{interval_minutes}min'
    )
    
    # Créer un DataFrame avec toutes les dates attendues
    df_expected = pd.DataFrame({
        'timestamp': expected_times,
        'is_expected': True
    })
    
    # Fusionner avec les données réelles
    df_complete = df_expected.merge(
        df_real[['timestamp', 'value']],
        on='timestamp',
        how='left'
    )
    
    # Marquer les valeurs manquantes
    df_complete['is_missing'] = df_complete['value'].isna()
    
    # Interpoler les valeurs pour les trous (optionnel, pour la visualisation)
    df_complete['value_interpolated'] = df_complete['value'].interpolate(method='linear')
    
    # Créer un DataFrame avec uniquement les trous
    df_missing = df_complete[df_complete['is_missing']].copy()
    
    # Mettre en cache (limiter la taille du cache)
    if use_cache:
        if len(_computation_cache) >= _MAX_CACHE_SIZE:
            # Supprimer la plus ancienne entrée (FIFO simple)
            oldest_key = next(iter(_computation_cache))
            del _computation_cache[oldest_key]
        
        _computation_cache[cache_key] = {
            'df_complete': df_complete.copy(),
            'df_missing': df_missing.copy()
        }
    
    return df_complete, df_missing


def create_availability_chart(
    df_complete: pd.DataFrame,
    interval_minutes: int = 15
) -> go.Figure:
    """
    Crée un graphique de disponibilité montrant les périodes avec/sans données
    
    Args:
        df_complete: DataFrame complet avec colonnes timestamp et is_missing
        interval_minutes: Intervalle attendu
    
    Returns:
        Figure Plotly
    """
    if df_complete.empty:
        return go.Figure()
    
    # Regrouper par jour pour calculer la disponibilité quotidienne
    df_complete['date'] = pd.to_datetime(df_complete['timestamp']).dt.date
    daily_stats = df_complete.groupby('date').agg({
        'is_missing': lambda x: (1 - x.mean()) * 100,  # Pourcentage de disponibilité
        'timestamp': 'count'
    }).reset_index()
    daily_stats.columns = ['date', 'availability', 'count']
    
    # Créer le graphique de disponibilité quotidienne
    fig = go.Figure()
    
    # Bar chart avec gradient de couleur selon la disponibilité
    colors = ['red' if av < 50 else 'orange' if av < 80 else 'lightgreen' if av < 95 else 'green' 
              for av in daily_stats['availability']]
    
    fig.add_trace(go.Bar(
        x=daily_stats['date'],
        y=daily_stats['availability'],
        marker=dict(
            color=colors,
            line=dict(color='darkgray', width=0.5)
        ),
        name='Disponibilité',
        hovertemplate='<b>Date: %{x}</b><br>' +
                     'Disponibilité: %{y:.1f}%<br>' +
                     '<extra></extra>'
    ))
    
    # Ligne à 100%
    fig.add_hline(y=100, line_dash="dash", line_color="gray", 
                  annotation_text="100% (données complètes)")
    
    # Ligne à 95% (seuil de qualité)
    fig.add_hline(y=95, line_dash="dot", line_color="orange", 
                  annotation_text="95% (seuil qualité)")
    
    fig.update_layout(
        title="Disponibilité quotidienne des données",
        xaxis_title="Date",
        yaxis_title="Disponibilité (%)",
        yaxis=dict(range=[0, 105]),
        template='plotly_white',
        height=250,
        showlegend=False
    )
    
    return fig


def create_load_curve_chart(
    readings: List[MeterReading],
    title: str = "Courbe de charge",
    cldn: str = "",
    reading_type: str = "",
    interval_minutes: int = 15,
    max_points: int = 10000
) -> Tuple[go.Figure, go.Figure]:
    """
    Crée un graphique de courbe de charge optimisé avec détection des trous
    
    Args:
        readings: Liste des lectures
        title: Titre du graphique
        cldn: Identifiant du compteur
        reading_type: Type de lecture
        interval_minutes: Intervalle attendu entre les mesures
        max_points: Nombre maximum de points à afficher (pour optimisation)
    
    Returns:
        Tuple (figure principale, figure de disponibilité)
    """
    empty_fig = go.Figure()
    empty_fig.add_annotation(
        text="Aucune donnée disponible",
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False
    )
    
    if not readings:
        return empty_fig, empty_fig
    
    # Détecter les trous (avec cache)
    df_complete, df_missing = detect_missing_intervals(readings, interval_minutes, use_cache=True)
    
    if df_complete.empty:
        return empty_fig, empty_fig
    
    # Créer le graphique de disponibilité
    availability_fig = create_availability_chart(df_complete, interval_minutes)
    
    # Le downsampling adaptatif sera fait dans la fonction de tracé
    # Pas besoin de pré-échantillonner ici car Scattergl gère bien les grandes quantités
    
    # Séparer les données réelles et manquantes
    df_real_data = df_complete[~df_complete['is_missing']].copy()
    df_missing_data = df_complete[df_complete['is_missing']].copy()
    
    # Créer la figure
    fig = go.Figure()
    
    # Tracer les données réelles (courbe principale) avec WebGL pour performance
    if not df_real_data.empty:
        # Downsampling adaptatif si nécessaire
        display_data = _adaptive_downsample(df_real_data, max_points=50000)
        
        # Utiliser Scattergl (WebGL) pour de meilleures performances
        fig.add_trace(go.Scattergl(
            x=display_data['timestamp'],
            y=display_data['value'],
            mode='lines',
            name='Données réelles',
            line=dict(color='#0066cc', width=2),
            hovertemplate='<b>Donnée réelle</b><br>' +
                         'Date: %{x|%Y-%m-%d %H:%M:%S}<br>' +
                         'Valeur: %{y:.2f}<br>' +
                         '<extra></extra>',
            # Optimisations WebGL
            connectgaps=False
        ))
        
        # Ajouter des points uniquement si peu de données (pour la visibilité)
        if len(display_data) <= 1000:
            fig.add_trace(go.Scattergl(
                x=display_data['timestamp'],
                y=display_data['value'],
                mode='markers',
                name='Points de mesure',
                marker=dict(size=4, color='#0066cc', symbol='circle'),
                showlegend=False,
                hoverinfo='skip'
            ))
    
    # Tracer les trous (zones manquantes) en rouge/orange
    if not df_missing_data.empty:
        # Grouper les trous consécutifs pour créer des segments
        df_missing_data = df_missing_data.sort_values('timestamp').reset_index(drop=True)
        
        # Identifier les groupes de trous consécutifs
        if len(df_missing_data) > 1:
            time_diff = df_missing_data['timestamp'].diff()
            df_missing_data['is_new_group'] = time_diff > timedelta(minutes=interval_minutes * 2)
            df_missing_data['group'] = df_missing_data['is_new_group'].cumsum()
        else:
            df_missing_data['group'] = 0
        
        # Pour chaque groupe de trous, créer une zone
        for group_id in df_missing_data['group'].unique():
            group_data = df_missing_data[df_missing_data['group'] == group_id]
            
            if len(group_data) == 0:
                continue
            
            # Trouver les valeurs avant et après le groupe
            first_missing_time = group_data['timestamp'].min()
            last_missing_time = group_data['timestamp'].max()
            
            # Valeur avant le trou
            before_data = df_complete[df_complete['timestamp'] < first_missing_time]
            before_val = before_data['value'].iloc[-1] if len(before_data) > 0 and pd.notna(before_data['value'].iloc[-1]) else None
            
            # Valeur après le trou
            after_data = df_complete[df_complete['timestamp'] > last_missing_time]
            after_val = after_data['value'].iloc[0] if len(after_data) > 0 and pd.notna(after_data['value'].iloc[0]) else None
            
            # Créer une zone pour le groupe de trous
            if before_val is not None or after_val is not None:
                y_min = df_complete['value'].min() * 0.95 if len(df_complete) > 0 else 0
                y_max = df_complete['value'].max() * 1.05 if len(df_complete) > 0 else 100
                
                if before_val is not None and after_val is not None:
                    y_min = min(before_val, after_val) * 0.95
                    y_max = max(before_val, after_val) * 1.05
                elif before_val is not None:
                    y_min = before_val * 0.95
                    y_max = before_val * 1.05
                elif after_val is not None:
                    y_min = after_val * 0.95
                    y_max = after_val * 1.05
                
                # Couleur selon la taille du trou
                num_missing = len(group_data)
                if num_missing <= 4:  # Petit trou (< 1h)
                    fillcolor = 'rgba(255, 165, 0, 0.3)'  # Orange
                elif num_missing <= 96:  # Trou moyen (< 1 jour)
                    fillcolor = 'rgba(255, 100, 0, 0.4)'  # Orange foncé
                else:  # Grand trou (> 1 jour)
                    fillcolor = 'rgba(255, 0, 0, 0.5)'  # Rouge
                
                fig.add_shape(
                    type="rect",
                    x0=first_missing_time - timedelta(minutes=interval_minutes/2),
                    x1=last_missing_time + timedelta(minutes=interval_minutes/2),
                    y0=y_min,
                    y1=y_max,
                    fillcolor=fillcolor,
                    line=dict(color='red', width=1, dash='dot'),
                    layer='below'
                )
        
        # Statistiques des trous (sera affiché dans le titre ou une annotation séparée)
        total_groups = len(df_missing_data['group'].unique())
    
    # Calculer les statistiques avant la mise en forme
    total_expected = len(df_complete)
    total_real = len(df_real_data)
    total_missing = len(df_missing_data) if not df_missing_data.empty else 0
    completeness = (total_real / total_expected * 100) if total_expected > 0 else 0
    
    # Couleur selon la complétude
    if completeness >= 95:
        box_color = "rgba(200, 255, 200, 0.9)"
        border_color = "green"
        status = "✅ Excellente"
    elif completeness >= 80:
        box_color = "rgba(255, 255, 200, 0.9)"
        border_color = "orange"
        status = "⚠️ Acceptable"
    else:
        box_color = "rgba(255, 200, 200, 0.9)"
        border_color = "red"
        status = "❌ Insuffisante"
    
    # Construire le titre avec les informations importantes
    title_text = f"{title}"
    subtitle_text = f"{cldn} - {reading_type}"
    
    # Ajouter les statistiques des trous dans le sous-titre si présent
    if not df_missing_data.empty:
        total_groups = len(df_missing_data['group'].unique())
        subtitle_text += f" | 🔴 {total_groups} période(s) manquante(s)"
    
    # Mise en forme avec optimisations pour WebGL
    fig.update_layout(
        title={
            'text': f"{title_text}<br><sub>{subtitle_text}</sub>",
            'x': 0.5,
            'xanchor': 'center',
            'font': dict(size=14)
        },
        xaxis_title="Date et heure",
        yaxis_title="Valeur (kWh)",
        hovermode='closest',  # Plus performant que 'x unified' avec WebGL
        template='plotly_white',
        height=500,
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.98,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(255, 255, 255, 0.8)",
            bordercolor="gray",
            borderwidth=1
        ),
        # Optimisations pour WebGL
        dragmode='pan',  # Mode de zoom optimisé
        selectdirection='h',  # Sélection horizontale uniquement
        # Marges pour éviter les superpositions
        margin=dict(t=100, b=80, l=60, r=20)
    )
    
    # Annotation des statistiques en bas à droite (position ajustée pour éviter superposition)
    fig.add_annotation(
        text=f"<b>Complétude: {completeness:.1f}%</b><br>"
             f"({status})<br>"
             f"Réelles: {total_real:,}<br>"
             f"Manquantes: {total_missing:,}<br>"
             f"Attendu: {total_expected:,}",
        xref="paper", yref="paper",
        x=0.99, y=0.01,
        xanchor="right", yanchor="bottom",
        bgcolor=box_color,
        bordercolor=border_color,
        borderwidth=2,
        showarrow=False,
        font=dict(size=9),
        align="right"
    )
    
    return fig, availability_fig


def create_index_chart(
    readings: List[MeterReading],
    title: str = "Évolution de l'index",
    cldn: str = "",
    reading_type: str = ""
) -> go.Figure:
    """
    Crée un graphique d'évolution de l'index (cumulatif)
    
    Args:
        readings: Liste des lectures
        title: Titre du graphique
        cldn: Identifiant du compteur
        reading_type: Type de lecture
    
    Returns:
        Figure Plotly
    """
    if not readings:
        fig = go.Figure()
        fig.add_annotation(
            text="Aucune donnée disponible",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False
        )
        return fig
    
    # Trier par timestamp
    sorted_readings = sorted(readings, key=lambda x: x.timestamp)
    
    # Créer un DataFrame
    df = pd.DataFrame([
        {
            'timestamp': r.timestamp,
            'value': r.value
        }
        for r in sorted_readings
    ])
    
    # Créer la figure
    fig = go.Figure()
    
    # Downsampling adaptatif pour l'index si nécessaire
    display_df = _adaptive_downsample(df, max_points=20000)
    
    # Utiliser Scattergl pour de meilleures performances
    fig.add_trace(go.Scattergl(
        x=display_df['timestamp'],
        y=display_df['value'],
        mode='lines+markers',
        name='Index',
        line=dict(color='#2ca02c', width=2),
        marker=dict(size=4, color='#2ca02c'),
        hovertemplate='<b>Index</b><br>' +
                     'Date: %{x|%Y-%m-%d %H:%M:%S}<br>' +
                     'Valeur: %{y:.2f}<br>' +
                     '<extra></extra>'
    ))
    
    # Mise en forme
    fig.update_layout(
        title={
            'text': f"{title}<br><sub>{cldn} - {reading_type}</sub>",
            'x': 0.5,
            'xanchor': 'center'
        },
        xaxis_title="Date et heure",
        yaxis_title="Index (cumulatif)",
        hovermode='x unified',
        template='plotly_white',
        height=400,
        showlegend=True
    )
    
    return fig


def get_readings_by_cldn_and_type(
    processing_results: List,
    cldn: str,
    libelle_original: str,
    obis_mapping: Dict = None
) -> List[MeterReading]:
    """
    Extrait les lectures pour un CLDN et un libellé original spécifiques
    
    Args:
        processing_results: Liste des résultats de traitement
        cldn: Identifiant du compteur
        libelle_original: Libellé original (ex: "A+ IX15m")
        obis_mapping: Mapping OBIS pour trouver le reading_type correspondant
    
    Returns:
        Liste des lectures correspondantes
    """
    readings = []
    
    # Si un mapping est fourni, trouver le reading_type correspondant au libellé
    reading_types = []
    if obis_mapping:
        for reading_type_key, obis_info in obis_mapping.items():
            if obis_info.get('libelle_original') == libelle_original:
                reading_types.append(reading_type_key)
    
    # Si aucun mapping ou aucun type trouvé, chercher directement par libellé
    if not reading_types:
        # Fallback : chercher dans les lectures avec le libellé comme reading_type
        reading_types = [libelle_original]
    
    for result in processing_results:
        if not result.success or not result.readings:
            continue
        
        for reading in result.readings:
            if reading.cldn == cldn and reading.reading_type in reading_types:
                readings.append(reading)
    
    return readings

