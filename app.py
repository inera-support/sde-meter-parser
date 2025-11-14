"""
Dashboard Streamlit pour la conversion des relevés manuels de compteurs
"""

import streamlit as st
import pandas as pd
import zipfile
import io
from datetime import datetime
from typing import List, Dict, Any
import tempfile
import os

# Import des modules locaux
from parsers import FileProcessor, FileProcessingResult
from validation import QualityReportGenerator
from export import EnergyWorxExporter, SummaryTableGenerator
from visualization import create_load_curve_chart, create_index_chart, get_readings_by_cldn_and_type

# Configuration de la page
st.set_page_config(
    page_title="Parser Relevés Manuels Compteurs",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personnalisé
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 0.375rem;
        padding: 1rem;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 0.375rem;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 0.375rem;
        padding: 1rem;
        margin: 1rem 0;
    }
    .metric-card {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 0.375rem;
        padding: 1rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

def main():
    """Fonction principale de l'application"""
    
    # En-tête
    st.markdown('<h1 class="main-header">⚡ Parser Relevés Manuels Compteurs</h1>', unsafe_allow_html=True)
    
    st.markdown("""
    Cette application permet de convertir les relevés manuels de compteurs électriques 
    (CSV BlueLink, XML MAP110, Excel) vers le format EnergyWorx pour l'ingestion dans le MDMS.
    """)
    
    # Initialisation des variables de session
    if 'processing_results' not in st.session_state:
        st.session_state.processing_results = []
    if 'quality_report' not in st.session_state:
        st.session_state.quality_report = None
    if 'exported_files' not in st.session_state:
        st.session_state.exported_files = {}
    
    # Sidebar
    with st.sidebar:
        st.header("📋 Instructions")
        st.markdown("""
        1. **Uploadez vos fichiers** : CSV, XML, Excel ou ZIP
        2. **Vérifiez les résultats** dans le tableau de synthèse
        3. **Téléchargez les fichiers** convertis au format EnergyWorx
        
        **Formats supportés :**
        - CSV BlueLink (compteurs Ensor)
        - XML MAP110 (compteurs Landis)
        - Excel BlueLink
        - Fichiers ZIP contenant les formats ci-dessus
        """)
        
        st.header("🔧 Paramètres")
        
        # Option pour forcer un CLDN
        force_cldn = st.text_input(
            "CLDN forcé (optionnel)",
            help="Si les fichiers ne contiennent pas de CLDN, utilisez cette valeur"
        )
        
        # Option pour le fuseau horaire
        timezone_option = st.selectbox(
            "Fuseau horaire source",
            ["Europe/Zurich", "Europe/Paris", "UTC"],
            help="Fuseau horaire des données d'entrée"
        )
        
        st.header("📊 Aide - Colonnes de complétude")
        st.markdown("""
        **Colonnes "Complet" et "Pourcentage" :**
        
        Ces colonnes indiquent la **qualité temporelle** des données :
        
        - **Complet** : True/False selon si ≥95% de couverture
        - **Pourcentage** : Pourcentage exact de couverture (0-100%)
        
        **Calcul :**
        1. Période totale = Dernière lecture - Première lecture
        2. Lectures attendues = Période ÷ 15 minutes + 1
        3. Pourcentage = (Lectures réelles ÷ Lectures attendues) × 100
        
        **Exemple :**
        - 24h de données → 97 lectures attendues
        - 92 lectures réelles → 94.8% → Complet = False
        """)
    
    # Section principale
    tab1, tab2, tab3, tab4 = st.tabs(["📁 Upload", "📊 Synthèse", "🔍 Qualité", "💾 Export"])
    
    with tab1:
        upload_section(force_cldn, timezone_option)
    
    with tab2:
        summary_section()
    
    with tab3:
        quality_section()
    
    with tab4:
        export_section()

def upload_section(force_cldn: str, timezone_option: str):
    """Section d'upload des fichiers"""
    
    st.header("📁 Upload des fichiers")
    
    # Zone de drag & drop
    uploaded_files = st.file_uploader(
        "Glissez-déposez vos fichiers ou cliquez pour sélectionner",
        type=['csv', 'xml', 'xlsx', 'xls', 'zip'],
        accept_multiple_files=True,
        help="Formats supportés : CSV BlueLink, XML MAP110, Excel BlueLink, ZIP"
    )
    
    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} fichier(s) sélectionné(s)")
        
        # Bouton de traitement
        if st.button("🔄 Traiter les fichiers", type="primary"):
            process_files(uploaded_files, force_cldn, timezone_option)
    

def process_files(uploaded_files: List, force_cldn: str, timezone_option: str):
    """Traite les fichiers uploadés"""
    
    with st.spinner("🔄 Traitement des fichiers en cours..."):
        processor = FileProcessor()
        processing_results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, uploaded_file in enumerate(uploaded_files):
            status_text.text(f"Traitement de {uploaded_file.name}...")
            
            try:
                # Lecture du contenu du fichier
                file_content = uploaded_file.read()
                
                # Traitement selon le type de fichier
                if uploaded_file.name.lower().endswith('.zip'):
                    results = processor.process_zip(file_content, uploaded_file.name)
                    processing_results.extend(results)
                else:
                    result = processor.process_file(file_content, uploaded_file.name)
                    processing_results.append(result)
                
                # Application du CLDN forcé si nécessaire
                if force_cldn:
                    for result in processing_results:
                        if result.success and result.readings:
                            for reading in result.readings:
                                if not reading.cldn:
                                    reading.cldn = force_cldn
                
            except Exception as e:
                error_result = FileProcessingResult(
                    uploaded_file.name, 
                    False, 
                    errors=[f"Erreur lors du traitement: {str(e)}"]
                )
                processing_results.append(error_result)
            
            progress_bar.progress((i + 1) / len(uploaded_files))
        
        # Génération du rapport de qualité
        quality_generator = QualityReportGenerator()
        quality_report = quality_generator.generate_report(processing_results)
        
        # Mise à jour de la session avec les fichiers originaux pour conserver les tailles
        st.session_state.processing_results = processing_results
        st.session_state.quality_report = quality_report
        st.session_state.uploaded_files_info = {f.name: f.size for f in uploaded_files}
        
        status_text.text("✅ Traitement terminé!")
        progress_bar.empty()
        
        # Affichage des résultats
        display_processing_results(processing_results)

def display_processing_results(processing_results: List[FileProcessingResult]):
    """Affiche les résultats du traitement"""
    
    st.subheader("📊 Résultats du traitement")
    
    # Statistiques globales
    total_files = len(processing_results)
    successful_files = sum(1 for r in processing_results if r.success)
    failed_files = total_files - successful_files
    total_readings = sum(len(r.readings) for r in processing_results)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Fichiers traités", total_files)
    
    with col2:
        st.metric("Succès", successful_files, delta=f"{successful_files/total_files*100:.1f}%" if total_files > 0 else "0%")
    
    with col3:
        st.metric("Échecs", failed_files)
    
    with col4:
        st.metric("Lectures totales", total_readings)
    
    # Mise à jour du tableau des fichiers avec les résultats
    if processing_results:
        st.subheader("📋 État des fichiers")
        
        # Explication des colonnes
        with st.expander("ℹ️ Explication des colonnes"):
            st.markdown("""
            **Colonnes du tableau :**
            
            - **Nom** : Nom du fichier traité
            - **Taille** : Taille réelle du fichier en KB
            - **Type** : Extension du fichier (CSV, XML, XLSX, ZIP)
            - **Statut** : 
              - ✅ **Succès** : Fichier traité sans erreur critique
              - ❌ **Échec** : Erreur lors du traitement du fichier
            - **Nombre de canaux** : Nombre de types de mesures différents dans le fichier
            - **Mesures temporelles** : Nombre de mesures d'énergie extraites du fichier
            - **Erreurs** : Nombre d'erreurs critiques détectées (empêchent le traitement)
            - **Avertissements** : Nombre d'avertissements détectés (n'empêchent pas le traitement)
            
            **Types d'erreurs courantes :**
            - Format de fichier non supporté
            - Structure XML/CSV invalide
            - Données manquantes critiques (CLDN, timestamps)
            - Encodage de fichier non reconnu
            
            **Types d'avertissements courants :**
            - Valeurs manquantes dans certaines colonnes
            - Timestamps en dehors de la plage attendue
            - Valeurs d'énergie anormalement élevées ou négatives
            - Doublons détectés dans les données
            """)
        
        # Créer un dictionnaire pour mapper les résultats par nom de fichier
        results_by_filename = {result.filename: result for result in processing_results}
        
        # Mettre à jour les informations des fichiers
        updated_file_info = []
        for result in processing_results:
            status = "✅ Succès" if result.success else "❌ Échec"
            
            # Récupérer la taille réelle du fichier si disponible
            file_size = st.session_state.get('uploaded_files_info', {}).get(result.filename, 0)
            if file_size > 0:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{len(result.readings) * 0.1:.1f} KB"  # Estimation basée sur les lectures
            
            # Compter les types uniques pour ce fichier
            unique_types = set(r.reading_type for r in result.readings)
            
            updated_file_info.append({
                'Nom': result.filename,
                'Taille': size_str,
                'Type': result.filename.split('.')[-1].upper(),
                'Statut': status,
                'Nombre de canaux': len(unique_types),
                'Mesures temporelles': len(result.readings),
                'Erreurs': len(result.errors),
                'Avertissements': len(result.warnings)
            })
        
        df_updated = pd.DataFrame(updated_file_info)
        st.dataframe(df_updated, use_container_width=True)
        
        # Affichage des erreurs
        errors_found = any(len(r.errors) > 0 for r in processing_results)
        if errors_found:
            st.subheader("❌ Erreurs détectées")
            
            for result in processing_results:
                if result.errors:
                    with st.expander(f"Erreurs dans {result.filename}"):
                        for error in result.errors:
                            st.error(error)

def summary_section():
    """Section du tableau de synthèse"""
    
    st.header("📊 Tableau de synthèse des compteurs relevés")
    
    if not st.session_state.processing_results:
        st.info("Aucun fichier traité. Veuillez d'abord uploader et traiter des fichiers.")
        return
    
    # Génération du tableau de synthèse
    summary_generator = SummaryTableGenerator()
    summary_data = summary_generator.generate_summary_table(st.session_state.processing_results)
    
    if not summary_data:
        st.warning("Aucune donnée valide trouvée pour générer le tableau de synthèse.")
        return
    
    # Affichage du tableau
    df_summary = pd.DataFrame(summary_data)
    
    # Filtres
    col1, col2, col3 = st.columns(3)
    
    with col1:
        cldn_filter = st.multiselect(
            "Filtrer par CLDN",
            options=df_summary['CLDN'].unique(),
            default=df_summary['CLDN'].unique()
        )
    
    with col2:
        status_filter = st.multiselect(
            "Filtrer par statut de validation",
            options=df_summary['Statut Validation'].unique(),
            default=df_summary['Statut Validation'].unique()
        )
    
    with col3:
        energy_type_filter = st.multiselect(
            "Filtrer par type d'énergie",
            options=df_summary['Type Énergie'].unique(),
            default=df_summary['Type Énergie'].unique()
        )
    
    # Application des filtres
    filtered_df = df_summary[
        (df_summary['CLDN'].isin(cldn_filter)) &
        (df_summary['Statut Validation'].isin(status_filter)) &
        (df_summary['Type Énergie'].isin(energy_type_filter))
    ]
    
    # Explication des colonnes
    with st.expander("ℹ️ Explication des colonnes"):
        st.markdown("""
        **Colonnes principales :**
        - **CLDN** : Identifiant unique du compteur
        - **Libellé Original** : Nom du registre tel qu'il apparaît dans les données sources
        - **Code OBIS** : Code standard selon la norme IEC 62056-61
        - **Description Standard** : Signification du code OBIS selon la norme
        - **Type Énergie** : Active, Réactive, Apparente, Puissance
        - **Direction/Quadrant** : Direction (Importée/Exportée) ou Quadrant (Q1/Q2/Q3/Q4)
        - **Unité** : Unité de mesure (kWh, kvarh, kVAh, kW)
        - **Statut Validation** : CORRECT, AVERTISSEMENT, ERREUR, INCONNU
        - **Type de fichier** : Format source des données (CSV BlueLink, XML MAP110 E450, etc.)
        
        **Colonnes de comptage :**
        - **Nombre de canaux** : Nombre de types de mesures différents pour ce compteur (ex: 9 pour E450)
        - **Mesures temporelles** : Nombre de mesures pour ce type spécifique (ex: 4587 pour A+ Load1)
        
        **Colonnes de complétude :**
        - **Complet** : Indique si les données couvrent exactement 100% de la période attendue
        - **Pourcentage** : Pourcentage de couverture des données (0-100%)
        
        **Calcul de la complétude :**
        1. **Période totale** : De la première à la dernière lecture
        2. **Lectures attendues** : Durée totale ÷ 15 minutes + 1
        3. **Pourcentage** : (Lectures réelles ÷ Lectures attendues) × 100
        4. **Complet** : True si = 100%, False sinon
        
        **Exemple pour compteur E450 :**
        - **Nombre de canaux** : 9 (A+ import, A- export, Q1, Q2, Q3, Q4, Load1, Load2, Quality)
        - **Mesures temporelles** : 4587 (pour le canal A+ Load1 sur 15 minutes)
        """)
    
    # Affichage du tableau filtré
    st.dataframe(filtered_df, use_container_width=True)
    
    # Avertissements pour les erreurs OBIS
    error_rows = filtered_df[filtered_df['Statut Validation'] == 'ERREUR']
    if not error_rows.empty:
        st.subheader("⚠️ Erreurs OBIS détectées")
        st.warning(f"**{len(error_rows)} registre(s) avec des erreurs d'attribution OBIS détectées !**")
        
        # Filtres spécifiques pour les erreurs
        col1, col2 = st.columns(2)
        
        with col1:
            error_type_filter = st.multiselect(
                "Filtrer par type d'erreur",
                options=error_rows['Type Énergie'].unique(),
                default=error_rows['Type Énergie'].unique(),
                key="error_type_filter"
            )
        
        with col2:
            error_code_filter = st.multiselect(
                "Filtrer par code OBIS problématique",
                options=error_rows['Code OBIS'].unique(),
                default=error_rows['Code OBIS'].unique(),
                key="error_code_filter"
            )
        
        # Application des filtres d'erreur
        filtered_errors = error_rows[
            (error_rows['Type Énergie'].isin(error_type_filter)) &
            (error_rows['Code OBIS'].isin(error_code_filter))
        ]
        
        for _, row in filtered_errors.iterrows():
            with st.expander(f"❌ {row['CLDN']} - {row['Libellé Original']}"):
                st.error(f"**Code OBIS:** {row['Code OBIS']}")
                st.write(f"**Description standard:** {row['Description Standard']}")
                st.write(f"**Problème:** {row['Commentaire']}")
                st.write(f"**Recommandation:** Vérifiez la configuration du compteur ou contactez le fournisseur des données.")
        
        # Résumé des erreurs par type
        st.subheader("📊 Résumé des erreurs par type")
        
        error_summary = error_rows.groupby(['Type Énergie', 'Code OBIS']).size().reset_index(name='Nombre')
        error_summary = error_summary.sort_values('Nombre', ascending=False)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Par type d'énergie:**")
            type_summary = error_rows.groupby('Type Énergie').size().reset_index(name='Nombre')
            for _, row in type_summary.iterrows():
                st.write(f"- {row['Type Énergie']}: {row['Nombre']} erreur(s)")
        
        with col2:
            st.write("**Par code OBIS:**")
            code_summary = error_rows.groupby('Code OBIS').size().reset_index(name='Nombre')
            for _, row in code_summary.iterrows():
                st.write(f"- {row['Code OBIS']}: {row['Nombre']} erreur(s)")
    
    # Statistiques du tableau
    st.subheader("📈 Statistiques")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Compteurs uniques", len(filtered_df['CLDN'].unique()))
    
    with col2:
        st.metric("Types d'énergie uniques", len(filtered_df['Type Énergie'].unique()))
    
    with col3:
        complete_count = len(filtered_df[filtered_df['Complet'] == True])
        incomplete_count = len(filtered_df[filtered_df['Complet'] == False])
        st.metric("Registres complets", complete_count, delta=f"{complete_count/len(filtered_df)*100:.1f}%" if len(filtered_df) > 0 else "0%")
        
        # Explication de la complétude
        if incomplete_count > 0:
            st.caption(f"⚠️ {incomplete_count} registre(s) incomplet(s) détecté(s)")
            st.caption("Un registre est considéré comme complet s'il couvre exactement 100% de la période attendue")
    
    with col4:
        # Calculer le nombre total de canaux uniques
        total_channels = filtered_df['Nombre de canaux'].sum() if len(filtered_df) > 0 else 0
        total_measurements = filtered_df['Mesures temporelles'].sum() if len(filtered_df) > 0 else 0
        st.metric("Canaux total", total_channels)
        st.caption(f"Mesures temporelles: {total_measurements:,}")
    
    # Section de visualisation des courbes de charge
    st.divider()
    st.subheader("📈 Visualisation des courbes de charge")
    
    if len(filtered_df) > 0:
        # Sélection du CLDN et du type de lecture
        col1, col2 = st.columns(2)
        
        with col1:
            selected_cldn = st.selectbox(
                "Sélectionner un compteur (CLDN)",
                options=sorted(filtered_df['CLDN'].unique()),
                key="chart_cldn_select"
            )
        
        with col2:
            # Filtrer les types de lecture disponibles pour le CLDN sélectionné
            available_types = filtered_df[
                filtered_df['CLDN'] == selected_cldn
            ]['Libellé Original'].unique()
            
            selected_reading_type = st.selectbox(
                "Sélectionner un type de lecture",
                options=sorted(available_types),
                key="chart_reading_type_select"
            )
        
        # Récupérer les informations du type sélectionné
        selected_row = filtered_df[
            (filtered_df['CLDN'] == selected_cldn) &
            (filtered_df['Libellé Original'] == selected_reading_type)
        ].iloc[0]
        
        # Récupérer les lectures correspondantes
        # Utiliser le mapping OBIS du générateur de synthèse pour trouver le reading_type
        summary_generator = SummaryTableGenerator()
        readings = get_readings_by_cldn_and_type(
            st.session_state.processing_results,
            selected_cldn,
            selected_reading_type,
            obis_mapping=summary_generator.obis_mapping
        )
        
        if readings:
            # Afficher les informations
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Période", f"{selected_row['Date min'][:10]} → {selected_row['Date max'][:10]}")
            with col2:
                st.metric("Mesures", f"{len(readings):,}")
            with col3:
                st.metric("Complétude", selected_row['Pourcentage'])
            with col4:
                st.metric("Unité", selected_row['Unité'])
            
            # Options d'affichage
            col1, col2 = st.columns(2)
            with col1:
                show_load_curve = st.checkbox("Afficher la courbe de charge", value=True, key="show_load_curve")
            with col2:
                show_index = st.checkbox("Afficher l'évolution de l'index", value=False, key="show_index")
            
            # Graphique de courbe de charge
            if show_load_curve:
                st.markdown("#### Courbe de charge avec détection des trous")
                st.caption("🔵 Bleu = Données réelles | 🟠 Orange = Trous < 1 jour | 🔴 Rouge = Trous > 1 jour")
                
                chart, availability_chart = create_load_curve_chart(
                    readings=readings,
                    title="Courbe de charge",
                    cldn=selected_cldn,
                    reading_type=selected_reading_type,
                    interval_minutes=15
                )
                
                # Afficher le graphique de disponibilité d'abord
                st.plotly_chart(availability_chart, use_container_width=True)
                
                # Puis la courbe de charge détaillée
                st.plotly_chart(chart, use_container_width=True)
            
            # Graphique d'évolution de l'index
            if show_index:
                st.markdown("#### Évolution de l'index (cumulatif)")
                
                index_chart = create_index_chart(
                    readings=readings,
                    title="Évolution de l'index",
                    cldn=selected_cldn,
                    reading_type=selected_reading_type
                )
                st.plotly_chart(index_chart, use_container_width=True)
        else:
            st.warning(f"Aucune lecture trouvée pour {selected_cldn} - {selected_reading_type}")
    else:
        st.info("Sélectionnez des données dans le tableau ci-dessus pour afficher les graphiques.")
    
    # Boutons d'export
    st.divider()
    st.subheader("💾 Export du tableau")
    
    col1, col2 = st.columns(2)
    
    with col1:
        csv_data = summary_generator.export_summary_to_csv(filtered_df.to_dict('records'))
        st.download_button(
            label="📄 Télécharger CSV",
            data=csv_data,
            file_name=f"synthèse_compteurs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    with col2:
        excel_data = summary_generator.export_summary_to_excel(filtered_df.to_dict('records'))
        st.download_button(
            label="📊 Télécharger Excel",
            data=excel_data,
            file_name=f"synthèse_compteurs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

def quality_section():
    """Section de contrôle qualité"""
    
    st.header("🔍 Contrôle qualité des données")
    
    if not st.session_state.quality_report:
        st.info("Aucun rapport de qualité disponible. Veuillez d'abord traiter des fichiers.")
        return
    
    report = st.session_state.quality_report
    
    # Résumé global
    st.subheader("📊 Résumé global")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Fichiers traités", report['summary']['total_files'])
    
    with col2:
        st.metric("Lectures totales", report['summary']['total_readings'])
    
    with col3:
        st.metric("Erreurs", report['summary']['total_errors'])
    
    with col4:
        st.metric("Avertissements", report['summary']['total_warnings'])
    
    # Recommandations
    if report['recommendations']:
        st.subheader("💡 Recommandations")
        
        for recommendation in report['recommendations']:
            st.warning(recommendation)
    
    # Détail par fichier
    st.subheader("📋 Détail par fichier")
    
    for file_report in report['files']:
        with st.expander(f"{file_report['filename']} - {'✅' if file_report['success'] else '❌'}"):
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Lectures:** {file_report['readings_count']}")
                st.write(f"**Erreurs:** {len(file_report['errors'])}")
                st.write(f"**Avertissements:** {len(file_report['warnings'])}")
            
            with col2:
                if file_report['validation']:
                    validation = file_report['validation']
                    st.write(f"**Score de qualité:** {validation['quality_score']:.1f}%")
                    
                    if validation['statistics']:
                        stats = validation['statistics']
                        st.write(f"**Plage de dates:** {stats['date_range']['start'].strftime('%Y-%m-%d')} à {stats['date_range']['end'].strftime('%Y-%m-%d')}")
            
            # Erreurs
            if file_report['errors']:
                st.write("**Erreurs:**")
                for error in file_report['errors']:
                    st.error(error)
            
            # Avertissements
            if file_report['warnings']:
                st.write("**Avertissements:**")
                for warning in file_report['warnings']:
                    st.warning(warning)

def export_section():
    """Section d'export des fichiers"""
    
    st.header("💾 Export des fichiers EnergyWorx")
    
    if not st.session_state.processing_results:
        st.info("Aucun fichier traité. Veuillez d'abord uploader et traiter des fichiers.")
        return
    
    # Génération des fichiers d'export
    if st.button("🔄 Générer les fichiers EnergyWorx", type="primary"):
        with st.spinner("Génération des fichiers en cours..."):
            exporter = EnergyWorxExporter()
            exported_files = exporter.export_to_files(st.session_state.processing_results)
            st.session_state.exported_files = exported_files
        
        st.success(f"✅ {len(exported_files)} fichier(s) généré(s)")
    
    # Affichage des fichiers générés
    if st.session_state.exported_files:
        st.subheader("📁 Fichiers générés")
        
        file_list = []
        for filename, content in st.session_state.exported_files.items():
            file_list.append({
                'Nom': filename,
                'Taille': f"{len(content) / 1024:.1f} KB"
            })
        
        df_files = pd.DataFrame(file_list)
        st.dataframe(df_files, use_container_width=True)
        
        # Boutons de téléchargement
        st.subheader("📥 Téléchargement")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Téléchargement individuel
            st.write("**Téléchargement individuel:**")
            
            for filename, content in st.session_state.exported_files.items():
                st.download_button(
                    label=f"📄 {filename}",
                    data=content,
                    file_name=filename,
                    mime="application/json"
                )
        
        with col2:
            # Téléchargement en lot (ZIP)
            st.write("**Téléchargement en lot:**")
            
            exporter = EnergyWorxExporter()
            zip_content = exporter.create_zip_export(st.session_state.exported_files)
            
            st.download_button(
                label="📦 Télécharger tous les fichiers (ZIP)",
                data=zip_content,
                file_name=f"meter_readings_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip"
            )
    
    # Instructions d'ingestion
    st.subheader("📋 Instructions d'ingestion")
    
    st.markdown("""
    **Pour ingérer les fichiers dans EnergyWorx :**
    
    1. Téléchargez les fichiers JSON générés
    2. Utilisez l'API EnergyWorx ou l'interface d'ingestion
    3. Vérifiez que les CLDN correspondent aux compteurs dans le système
    4. Les fichiers sont au format standard EnergyWorx MeterReadings
    
    **Format des fichiers :**
    - Chaque fichier contient les lectures d'un compteur (CLDN)
    - Les timestamps sont en UTC
    - Les valeurs sont en kWh/kvarh selon le type de registre
    - Les ReadingTypes correspondent aux standards EnergyWorx
    """)

if __name__ == "__main__":
    main()
