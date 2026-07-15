# -*- coding: utf-8 -*-
"""
================================================================================
OUTIL DE PRÉ-DIAGNOSTIC ENVIRONNEMENTAL ET RÉGLEMENTAIRE POUR PSG FORESTIER
                            (version 2)
================================================================================
À exécuter dans la console Python de QGIS 3.x (menu : Extensions > Console
Python, ou via l'éditeur de script intégré).

Pour chaque couche de zonage réglementaire chargée dans le projet, le script :
  1. Calcule la valeur EXACTE intersectée avec la propriété :
       - en hectares pour les zonages SURFACIQUES (polygones)
       - en kilomètres pour les zonages LINÉAIRES (cours d'eau, réservoirs
         biologiques, etc.)
  2. Extrait le(s) polygone(s)/ligne(s) ENTIER(S) d'origine (non découpés)
     dans une couche mémoire, pour voir le contexte complet autour de la
     propriété.
  3. Génère un rapport de synthèse (.txt et .csv).

NOUVEAUTÉS DE LA VERSION 2 :
  - Une entrée du dictionnaire COUCHES_ZONAGES peut désormais être soit un
    nom de couche unique (str), soit une LISTE de noms de couches à fusionner
    automatiquement avant analyse (utile par exemple si vos "Monuments
    Historiques" sont éclatés en une couche par département).
  - Le script détecte automatiquement si un zonage est surfacique (polygone)
    ou linéaire (ligne) et adapte le calcul et l'affichage en conséquence.

Aucune modification du code n'est nécessaire en dehors de la section
"CONFIGURATION" ci-dessous.
================================================================================
"""

import os
import csv
import re
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsDistanceArea,
    QgsUnitTypes,
    QgsWkbTypes,
    QgsMessageLog,
    QgsProviderRegistry,
    QgsProviderSublayerDetails,
    QgsSettings,
    Qgis,
)
import processing
from qgis.PyQt.QtWidgets import QInputDialog, QFileDialog

# ==============================================================================
# 1. CONFIGURATION — À ADAPTER À VOTRE PROJET
# ==============================================================================

# --- GeoPackage intégré au plugin ---
# Le plugin embarque son propre GeoPackage de zonages (dossier "donnees/" à
# côté de ce fichier). C'est LUI qui est utilisé automatiquement, sans rien
# demander à l'utilisateur — pratique pour les collègues qui ne veulent pas
# se poser de questions.
# ==> POUR METTRE À JOUR LES DONNÉES (ex: nouvelles couches reçues du
#     CNPF) : remplacez simplement le fichier dans donnees/Analyse_
#     environnementale.gpkg par la nouvelle version (même nom, ou changez
#     CHEMIN_GPKG_ZONAGES_PAR_DEFAUT ci-dessous). Aucune autre modification
#     n'est nécessaire pour ce point.
DOSSIER_PLUGIN = os.path.dirname(os.path.abspath(__file__))
CHEMIN_GPKG_ZONAGES_PAR_DEFAUT = os.path.join(DOSSIER_PLUGIN, "donnees", "Analyse_environnementale.gpkg")

# --- Chargement automatique des couches de zonage depuis ce GeoPackage ---
CHARGER_GPKG_AUTOMATIQUEMENT = True

# Si False (recommandé pour un usage "grand public" par des collègues) :
# le GeoPackage intégré ci-dessus est utilisé directement, sans fenêtre de
# sélection - le diagnostic se lance en un clic.
# Si True : une fenêtre demande à chaque lancement quel GeoPackage utiliser
# (utile pour VOUS si vous voulez tester un autre fichier ponctuellement -
# le menu du plugin propose une entrée dédiée à ça, voir plugin_main.py).
DEMANDER_CHEMIN_GPKG_INTERACTIVEMENT = False

NOM_GROUPE_GPKG = "Zonages_Environnementaux (GPKG)"


# Clé utilisée pour mémoriser, d'une session QGIS à l'autre, le dernier
# GeoPackage sélectionné (via QgsSettings, propre à chaque utilisateur/poste).
# Pas besoin d'y toucher.
CLE_PARAMETRE_DERNIER_GPKG = "diagnostic_psg/dernier_gpkg_chemin"

# --- Sélection de la couche propriété : interactive ou fixe ---
# Si True (recommandé) : à chaque lancement, une fenêtre vous demande de
# choisir, parmi les couches POLYGONALES actuellement chargées dans le
# projet, laquelle représente le contour de la propriété/zone à analyser,
# puis vous demande le nom à afficher dans le rapport.
# Si False : le script utilise directement NOM_COUCHE_PROPRIETE et
# NOM_PROPRIETE_AFFICHAGE ci-dessous, sans rien demander (utile si vous
# voulez automatiser un traitement en série sans interaction).
DEMANDER_COUCHE_INTERACTIVEMENT = True

# --- Valeurs utilisées UNIQUEMENT si DEMANDER_COUCHE_INTERACTIVEMENT = False ---
# Nom EXACT (tel qu'il apparaît dans le panneau "Couches") de la couche
# contenant le(s) polygone(s) de votre propriété.
NOM_COUCHE_PROPRIETE = "Ma_Propriete"

# Nom de la propriété tel qu'il doit apparaître dans le rapport
NOM_PROPRIETE_AFFICHAGE = "Forêt du Grand Bois"

# Si la couche propriété contient PLUSIEURS polygones (parcelles cadastrales
# par ex.) et que vous ne voulez analyser que celles sélectionnées dans QGIS,
# laissez True. Si vous voulez toujours analyser TOUTES les entités de la
# couche (qu'il y ait une sélection ou non), mettez False.
UTILISER_SELECTION_SI_PRESENTE = True

# --- Dossier d'export du rapport ---
# Si DEMANDER_DOSSIER_EXPORT = True (recommandé) : une fenêtre vous demande,
# à chaque lancement, dans quel dossier enregistrer le rapport. Les fichiers
# sont nommés automatiquement "rapport_PSG_<nom_propriete>.txt/.csv".
# Si False : le script utilise directement DOSSIER_EXPORT_PAR_DEFAUT
# ci-dessous, sans rien demander.
DEMANDER_DOSSIER_EXPORT = True
DOSSIER_EXPORT_PAR_DEFAUT = r"C:\Users\Paul\Desktop\Analyse environnementale"

# --- Dictionnaire des couches de zonage à analyser ---
# Structure : {Thématique : {Libellé affiché dans le rapport : Nom(s) EXACT(S)
#              de la couche dans le projet QGIS}}
#
# ==> C'est ICI que vous devez faire correspondre les noms de VOS couches
#     (telles que chargées via SHP, GeoPackage ou flux WFS) avec les
#     libellés du rapport.
#
# NOUVEAU : la valeur peut être :
#   - une chaîne de caractères  : "Nom_De_Ma_Couche"
#   - une LISTE de chaînes      : ["Couche_Dept_04", "Couche_Dept_05", ...]
#     Dans ce cas, les couches listées sont automatiquement FUSIONNÉES avant
#     l'analyse (utile pour les Monuments Historiques éclatés par département,
#     par exemple).
#   - un DICTIONNAIRE {"couche": "Nom_De_Ma_Couche", "filtre": "expression QGIS", "champ_nom": "NOM_CHAMP"}
#     Toutes les clés sauf "couche" sont optionnelles :
#       - "filtre" : seules les entités vérifiant l'expression (syntaxe QGIS,
#         ex: "\"CODE_R_ENP\" = 'D'") sont conservées avant l'analyse. Utile
#         quand une seule couche source contient plusieurs zonages distincts
#         à séparer dans le rapport (ex: Réserves Biologiques Dirigées/
#         Intégrales dans une même couche INPN, distinguées par un champ).
#       - "champ_nom" : nom du champ attributaire contenant le nom du site/
#         de l'entité (ex: "NOM_SITE"). Si renseigné, le rapport ajoute après
#         l'analyse le ou les noms des entités effectivement concernées par
#         la propriété (ex: "[Site(s) : Étang de Berre]").
#
# Si une couche n'est pas chargée dans le projet, le script l'ignore
# proprement et le signale dans le rapport (aucun plantage).
COUCHES_ZONAGES = {

    # --- Protections réglementaires fortes (les plus contraignantes pour le PSG) ---
    "Protections fortes": {
        "Réserve Naturelle Nationale (RNN)":         {"couche": "Réserves naturelles nationales", "champ_nom": "nom_site"},
        "Réserve Naturelle Régionale (RNR)":         {"couche": "reserves-naturelles-regionales-rnr", "champ_nom": "nom_site"},
        # Nouvelle couche dédiée APPB (remplace l'ancienne N_ENP_APB_S_R93,
        # conservée en commentaire ci-dessous si jamais besoin de revenir dessus)
        #"Arrêté de Protection de Biotope (APPB)":    {"couche": "Arrete de protection de biotope", "champ_nom": ["NOM", "ID_MNHN", "URL"]},
        "Arrêté de Protection de Biotope (APPB)":  {"couche": "N_ENP_APB_S_R93", "champ_nom": "nom_site"},  # ancienne source INPN
        "Réserve Biologique Dirigée (RBD, INPN)":    {"couche": "Réserves biologiques", "filtre": "\"CODE_R_ENP\" = 'D'", "champ_nom": "NOM_SITE"},
        "Réserve Biologique Intégrale (RBI, INPN)":  {"couche": "Réserves biologiques", "filtre": "\"CODE_R_ENP\" = 'I'", "champ_nom": "NOM_SITE"},
        "Forêt de Protection":                       {"couche": "N_FORET_PROTECTION_ZINF_S_084", "champ_nom": "NOM_FORET"},
        # Espace Boisé Classé (PLU/POS, art. L113-1 du Code de l'urbanisme) :
        # simple présence + surface/%, pas de nom d'entité (nombreux petits
        # polygones sans intérêt individuel à nommer).
        "Espace Boisé Classé (EBC)":                  {"couche": "Espaces Boisés Classés"},
        # --- Parc National : zones distinguées séparément (contraintes très différentes) ---
        # Attention : la casse du champ diffère selon la couche (données
        # d'origines/millésimes différents) — vérifié directement dans le GeoPackage.
        "Réserve Intégrale du Parc National":        {"couche": "pnx-reserves-integrales — pnx_reserves_integrales", "champ_nom": "NOM_SITE"},
        "Cœur du Parc National":                     {"couche": "pnx-coeur-aa-ama — pnx_coeur_aa_ama", "champ_nom": "nom_site"},
        "Aire Optimale d'Adhésion du Parc National":  {"couche": "pnx-aoa — pnx_aoa", "champ_nom": "nom_site"},
    },

    # --- Zonages européens et inventaires scientifiques ---
    "Europe & Inventaires": {
        "Natura 2000 (ZSC - Directive Habitat)":  {"couche": "DH_ZSC", "champ_nom": "sitename"},
        "Natura 2000 (ZPS - Directive Oiseaux)":  {"couche": "DO_ZPS", "champ_nom": "sitename"},
        "ZNIEFF de type I":                        {"couche": "ZNIEFF_TERRE_1", "champ_nom": "nom"},
        "ZNIEFF de type II":                       {"couche": "ZNIEFF_TERRE_2", "champ_nom": "nom"},
    },

    # --- Eau & Risques naturels ---
    # NB : PPRI/PPRIF/PPRS à ajouter ici une fois récupérés via Géorisques
    # (georisques.gouv.fr/donnees/bases-de-donnees, par département 04/05/06/13/83/84)
    "Eau & Risques": {
        "Périmètre de captage (eau potable)":              "Perimetre_Captage",  # <-- accès restreint ARS, souvent non disponible
        "Zone humide":                                      "Zones_Humides_pour_PSG",
        "Zone Inondable - Atlas (AZI, informatif)":         "azi",  # <-- IMPORTANT : non opposable réglementairement, contrairement au PPRI
        "PPRI (Inondation - réglementaire)":                "PPRI",               # <-- à ajouter (Géorisques, en attente)
        "PPRIF (Incendie - réglementaire)":                 "PPRIF",              # <-- à ajouter (Géorisques, en attente)
        "PPRS (Séisme - réglementaire)":                    "PPRS",               # <-- à ajouter (Géorisques, en attente)
    },

    # --- Continuités écologiques (trame verte et bleue - SRCE) ---
    # NB : le réservoir biologique est une couche LINÉAIRE (cours d'eau) ;
    # le script calculera un linéaire en km, pas une surface en ha.
    "Continuités écologiques": {
        "Réservoir biologique (SDAGE/SRCE)": "RESERVOIR_BIOLOGIQUE",
    },

    # --- Patrimoine culturel et paysager ---
    "Patrimoine": {
        "Site Classé":  {"couche": "Site_Classe", "champ_nom": "nom"},
        "Site Inscrit": {"couche": "Site_Inscrit", "champ_nom": "nom"},
        # Vos couches sont éclatées par département : elles seront fusionnées
        # automatiquement par le script. Ajoutez/retirez des départements
        # selon ceux qui concernent réellement votre propriété.
        "Abords Monuments Historiques (PDA / 500m)": {
            "couche": [
                "Protection monuments historiques 04",
                "Protection monuments historiques 05",
                "Protection monuments historiques 06",
                "Protection monuments historiques 13",
                "Protection monuments historiques 83",
                "Protection monuments historiques 84",
            ],
            "champ_nom": "appelation",  # confirmé dans le GeoPackage (pas de champ "NOM" direct, "appelation" contient la désignation de l'édifice)
        },
    },

    # --- Périmètres contractuels (non réglementaires, mais à mentionner dans le PSG) ---
    "Chartes & périmètres contractuels": {
        "Parc Naturel Régional (PNR) - Charte": {"couche": "pnr_polygonPolygon", "champ_nom": "name"},
        # Périmètre global du Parc National (l'ensemble du territoire couvert
        # par le parc, tous types de zones confondus), à ne pas confondre
        # avec les 3 sous-zones déjà détaillées dans "Protections fortes".
        # <-- À ADAPTER : mettez ici le nom de VOTRE couche représentant le
        #     périmètre global du parc (si vous en avez une distincte des
        #     couches pnx-reserves-integrales / pnx-coeur-aa-ama / pnx-aoa).
        #     Par défaut, on réutilise l'AOA (couverture la plus large des 3).
        "Parc National": {"couche": "pnx-aoa — pnx_aoa", "champ_nom": "nom_site"},
    },
}

# --- Nom du groupe dans lequel seront rangées les couches extraites ---
NOM_GROUPE_RESULTATS = "Diagnostic_PSG_Contexte"

# --- Nombre de décimales pour les hectares / km et pourcentages affichés ---
DECIMALES_HA = 4
DECIMALES_KM = 2
DECIMALES_PCT = 1

# ==============================================================================
# 1bis. MODULE CARTE DES SOLS (analyse par répartition, pas par simple zonage)
# ==============================================================================
# Contrairement aux zonages réglementaires ci-dessus (qui touchent la
# propriété ou non), la carte des sols COUVRE TOUJOURS 100% de la surface,
# mais avec des types de sol différents à différents endroits. Le script
# liste donc chaque type de sol présent avec sa surface, plutôt qu'une
# simple ligne "touché / pas touché".

# Si True, cette analyse est effectuée en plus des zonages réglementaires.
ANALYSER_CARTE_SOLS = True

# Nom EXACT de la couche "carte des sols" dans le projet
NOM_COUCHE_SOLS = "Carte des sols"  # <-- vérifiez ce nom exact

# Noms EXACTS des champs contenant le type de sol, sa description et le
# lien vers la fiche descriptive (respectez la casse telle qu'affichée
# dans la table attributaire QGIS).
CHAMP_TYPE_SOL = "ger_nom"
CHAMP_DESCRIPTION_SOL = "nom_ucs"
CHAMP_LIEN_SOL = "lien_ger"

# Si True, le regroupement par type de sol ignore tout suffixe entre
# parenthèses dans CHAMP_TYPE_SOL (ex: "CALCOSOL(65%)" -> "CALCOSOL").
# Ce suffixe est une info pédologique (proportion du sol au sein d'une
# unité complexe), pas un pourcentage sur votre propriété : le regrouper
# évite d'avoir des dizaines de lignes quasi-identiques dans le rapport.
NORMALISER_TYPE_SOL = True


# ==============================================================================
# 1ter. MODULE GÉNÉRALITÉS (Sylvoécorégion, Climat, etc.)
# ==============================================================================
# Comme la carte des sols, ces couches couvrent toute la propriété avec des
# valeurs différentes selon les secteurs (une propriété est rarement à
# cheval sur 2 sylvoécorégions ou 2 zones climatiques, mais le script gère
# aussi ce cas en listant chaque valeur rencontrée avec sa surface).
#
# Cette section apparaît en tête du rapport, avant les zonages réglementaires.
#
# Si True, cette analyse est effectuée.
ANALYSER_GENERALITES = True

# Liste des couches "de contexte général" à analyser. Chaque entrée :
#   - "titre"            : libellé affiché dans le rapport
#   - "couche"            : nom EXACT de la couche dans le projet
#   - "champ_principal"   : champ dont chaque valeur distincte donne une ligne
#   - "champ_secondaire"  : (optionnel) champ complémentaire affiché entre
#                            parenthèses à côté de la valeur principale
#   - "texte_source"      : (optionnel) texte de citation/source affiché tel
#                            quel à la fin de chaque ligne
GENERALITES = [
    {
        "titre": "Sylvoécorégion",
        "couche": "Sylvoécorégions",
        "champ_principal": "NomSER",           # <-- vérifiez ce nom exact
        "champ_secondaire": "codeser",         # <-- vérifiez ce nom exact
        "texte_source": None,
    },
    {
        "titre": "Zonage climatique",
        "couche": "Climat",                    # <-- vérifiez ce nom exact
        "champ_principal": "Type",             # <-- vérifiez ce nom exact
        "champ_secondaire": None,
        "texte_source": (
            "Données tirées de : « Les types de climats en France, une "
            "construction spatiale », Hilal, Mohamed ; Joly, Daniel, 2019."
        ),
    },
]


# ==============================================================================
# 2. FONCTIONS UTILITAIRES (ne pas modifier sauf besoin spécifique)
# ==============================================================================

def obtenir_couche_par_nom(nom_couche):
    """Retourne la première couche du projet portant exactement ce nom,
    ou None si elle n'est pas chargée."""
    couches = QgsProject.instance().mapLayersByName(nom_couche)
    return couches[0] if couches else None


def obtenir_couche_zonage(reference_couche):
    """
    Résout une entrée du dictionnaire COUCHES_ZONAGES, qu'elle soit :
      - une chaîne de caractères (nom de couche unique)
      - une liste de chaînes (plusieurs couches à fusionner)
      - un dictionnaire {"couche": nom_ou_liste, "filtre": expr, "champ_nom": nom}
        où "couche" est obligatoire (str ou liste) et "filtre"/"champ_nom"
        sont optionnels

    Retourne un tuple (couche_travail, noms_manquants, couche_reference_style, champ_nom) où :
      - couche_travail est une QgsVectorLayer (mémoire si fusion/filtre) ou
        None si rien trouvé, utilisée pour les calculs géométriques
      - noms_manquants est la liste des noms de couches demandés mais absents
        du projet (utile pour le rapport de diagnostic)
      - couche_reference_style est la couche ORIGINALE du projet (jamais une
        couche mémoire de travail) dont on peut récupérer le style/la
        symbologie d'origine pour l'appliquer aux couches extraites
      - champ_nom est le nom du champ contenant le nom du site (ou None si
        non renseigné), utilisé pour lister les entités concernées
    """
    # --- Normalisation : on ramène tout au format dictionnaire ---
    if isinstance(reference_couche, dict):
        couche_ref = reference_couche.get("couche")
        expression_filtre = reference_couche.get("filtre")
        champ_nom = reference_couche.get("champ_nom")
    else:
        couche_ref = reference_couche  # str ou liste
        expression_filtre = None
        champ_nom = None

    # --- Résolution de la (ou des) couche(s) source(s) ---
    if isinstance(couche_ref, str):
        couche_source = obtenir_couche_par_nom(couche_ref)
        if couche_source is None:
            return None, [couche_ref], None, champ_nom
        couche_travail = couche_source
        noms_manquants = []
        couche_reference_style = couche_source

    else:
        # Liste de noms à fusionner
        couches_trouvees = []
        noms_manquants = []
        for nom in couche_ref:
            couche = obtenir_couche_par_nom(nom)
            if couche is not None:
                couches_trouvees.append(couche)
            else:
                noms_manquants.append(nom)

        if not couches_trouvees:
            return None, noms_manquants, None, champ_nom

        if len(couches_trouvees) == 1:
            couche_travail = couches_trouvees[0]
            couche_reference_style = couches_trouvees[0]
        else:
            # Fusion via native:mergevectorlayers (reprojection auto si CRS différents)
            crs_cible = couches_trouvees[0].crs()
            resultat_fusion = processing.run("native:mergevectorlayers", {
                'LAYERS': couches_trouvees,
                'CRS': crs_cible,
                'OUTPUT': 'memory:'
            })
            couche_travail = resultat_fusion['OUTPUT']
            # La première couche de la liste sert de référence de style (les
            # couches d'un même zonage éclaté par département partagent en
            # général la même symbologie)
            couche_reference_style = couches_trouvees[0]

    # --- Application du filtre attributaire, si demandé ---
    if expression_filtre:
        resultat_filtre = processing.run("native:extractbyexpression", {
            'INPUT': couche_travail,
            'EXPRESSION': expression_filtre,
            'OUTPUT': 'memory:'
        })
        couche_travail = resultat_filtre['OUTPUT']
        # couche_reference_style reste la couche complète (avant filtre) :
        # sa symbologie (souvent déjà catégorisée sur le même champ que le
        # filtre) reste pertinente pour la couche filtrée.

    return couche_travail, noms_manquants, couche_reference_style, champ_nom


def creer_calculateur_surface(crs_reference):
    """Crée un QgsDistanceArea configuré sur l'ellipsoïde du projet,
    ce qui permet un calcul de surface/longueur précis quel que soit
    le système de coordonnées des couches en entrée (y compris en WGS84/
    coordonnées géographiques, ce qui est fréquent pour les flux WFS)."""
    calculateur = QgsDistanceArea()
    calculateur.setSourceCrs(crs_reference, QgsProject.instance().transformContext())
    calculateur.setEllipsoid(QgsProject.instance().ellipsoid() or 'WGS84')
    return calculateur


def surface_totale_ha(couche_vecteur, calculateur):
    """Additionne la surface (en hectares) de toutes les entités d'une
    couche vectorielle POLYGONALE, en utilisant un QgsDistanceArea
    ellipsoïdal."""
    total_m2 = 0.0
    for entite in couche_vecteur.getFeatures():
        geom = entite.geometry()
        if geom and not geom.isEmpty():
            total_m2 += calculateur.measureArea(geom)
    return calculateur.convertAreaMeasurement(total_m2, QgsUnitTypes.AreaHectares)


def longueur_totale_km(couche_vecteur, calculateur):
    """Additionne la longueur (en kilomètres) de toutes les entités d'une
    couche vectorielle LINÉAIRE, en utilisant un QgsDistanceArea
    ellipsoïdal."""
    total_m = 0.0
    for entite in couche_vecteur.getFeatures():
        geom = entite.geometry()
        if geom and not geom.isEmpty():
            total_m += calculateur.measureLength(geom)
    return calculateur.convertLengthMeasurement(total_m, QgsUnitTypes.DistanceKilometers)


def type_geometrie_couche(couche):
    """Retourne le type de géométrie générique d'une couche :
    QgsWkbTypes.PolygonGeometry, LineGeometry ou PointGeometry."""
    return QgsWkbTypes.geometryType(couche.wkbType())


def demander_chemin_gpkg():
    """
    Ouvre une fenêtre "Ouvrir un fichier" permettant de choisir le
    GeoPackage contenant les couches de zonage environnemental.

    La fenêtre s'ouvre par défaut sur le DERNIER GeoPackage utilisé
    (mémorisé d'une session QGIS à l'autre via QgsSettings, propre à
    chaque utilisateur/poste) — pratique quand on réanalyse plusieurs
    propriétés à la suite avec le même fichier de zonages.

    Retourne le chemin choisi (str), ou None si l'utilisateur annule
    (auquel cas le script continuera en supposant que les couches sont
    déjà chargées manuellement dans le projet).
    """
    parametres = QgsSettings()
    dernier_chemin_utilise = parametres.value(CLE_PARAMETRE_DERNIER_GPKG, "", type=str)

    if dernier_chemin_utilise and os.path.isfile(dernier_chemin_utilise):
        dossier_depart = dernier_chemin_utilise  # QFileDialog accepte un chemin de fichier comme point de départ
    elif CHEMIN_GPKG_ZONAGES_PAR_DEFAUT and os.path.isfile(CHEMIN_GPKG_ZONAGES_PAR_DEFAUT):
        dossier_depart = CHEMIN_GPKG_ZONAGES_PAR_DEFAUT
    else:
        dossier_depart = ""

    chemin_choisi, _ = QFileDialog.getOpenFileName(
        None,
        "Diagnostic PSG — Sélectionnez le GeoPackage des zonages environnementaux",
        dossier_depart,
        "GeoPackage (*.gpkg)"
    )

    if not chemin_choisi:
        QgsMessageLog.logMessage(
            "Sélection du GeoPackage annulée : le script suppose que les "
            "couches de zonage sont déjà chargées manuellement dans le projet.",
            "Diagnostic PSG", level=Qgis.Warning
        )
        return None

    # Mémorisation pour le prochain lancement
    parametres.setValue(CLE_PARAMETRE_DERNIER_GPKG, chemin_choisi)

    return chemin_choisi


def charger_couches_gpkg(chemin_gpkg, nom_groupe):
    """
    Ouvre le GeoPackage indiqué et charge TOUTES les couches qu'il contient
    dans le projet QGIS, rangées dans un groupe dédié.

    Les couches déjà présentes dans le projet (même nom) ne sont PAS
    rechargées, pour éviter les doublons si vous relancez le script
    plusieurs fois dans la même session.

    Ne lève pas d'exception si le fichier est introuvable : le script
    continue simplement en supposant que les couches sont déjà chargées
    manuellement (comportement de repli).

    Retourne le groupe QGIS (QgsLayerTreeGroup) contenant les couches du
    GeoPackage, ou None si rien n'a pu être chargé — utilisé ensuite pour
    exclure ces couches de zonage de la liste proposée comme "propriété".
    """
    if not chemin_gpkg or not os.path.isfile(chemin_gpkg):
        QgsMessageLog.logMessage(
            f"GeoPackage introuvable au chemin indiqué : '{chemin_gpkg}'. "
            "Chargement automatique ignoré — assurez-vous que vos couches "
            "de zonage sont déjà chargées manuellement dans le projet.",
            "Diagnostic PSG", level=Qgis.Warning
        )
        return None

    try:
        details_sous_couches = QgsProviderRegistry.instance().querySublayers(chemin_gpkg)
    except Exception as erreur:
        QgsMessageLog.logMessage(
            f"Impossible de lire le contenu du GeoPackage '{chemin_gpkg}' : {erreur}",
            "Diagnostic PSG", level=Qgis.Warning
        )
        return None

    if not details_sous_couches:
        QgsMessageLog.logMessage(
            f"Aucune couche trouvée dans le GeoPackage '{chemin_gpkg}'.",
            "Diagnostic PSG", level=Qgis.Warning
        )
        return None

    groupe_gpkg = obtenir_ou_creer_groupe(nom_groupe)
    noms_deja_charges = {c.name() for c in QgsProject.instance().mapLayers().values()}

    # Options requises par toLayer() dans les versions récentes de QGIS
    # (>= 3.22 environ) : on lui passe le contexte de transformation de
    # coordonnées du projet.
    options_chargement = QgsProviderSublayerDetails.LayerOptions(
        QgsProject.instance().transformContext()
    )

    nb_chargees = 0
    for details in details_sous_couches:
        nom_couche = details.name()
        if nom_couche in noms_deja_charges:
            continue  # déjà présente dans le projet : on ne duplique pas

        couche = details.toLayer(options_chargement)
        if couche is None or not couche.isValid():
            QgsMessageLog.logMessage(
                f"Couche '{nom_couche}' invalide ou illisible dans le GeoPackage, ignorée.",
                "Diagnostic PSG", level=Qgis.Warning
            )
            continue

        QgsProject.instance().addMapLayer(couche, False)
        groupe_gpkg.addLayer(couche)
        nb_chargees += 1

    print(f"GeoPackage : {nb_chargees} couche(s) chargée(s) automatiquement "
          f"dans le groupe '{nom_groupe}'.")

    return groupe_gpkg


def obtenir_ids_couches_du_groupe(groupe):
    """Retourne l'ensemble des identifiants de couches (layer id) contenues
    dans un groupe QGIS, utilisé pour exclure les couches de zonage de la
    liste de sélection de la propriété."""
    if groupe is None:
        return set()
    return {noeud_couche.layerId() for noeud_couche in groupe.findLayers()}


def construire_chemins_rapport(dossier, nom_propriete_affichage):
    """Construit les chemins complets rapport_PSG_<nom>.txt/.csv dans le
    dossier donné, en nettoyant le nom de propriété pour un nom de fichier
    valide sous Windows. Réutilisée par demander_dossier_export() et par
    l'interface graphique du plugin (ui_dialog.py)."""
    caracteres_interdits = '<>:"/\\|?*'
    nom_fichier_propre = "".join(c for c in nom_propriete_affichage if c not in caracteres_interdits).strip()
    if not nom_fichier_propre:
        nom_fichier_propre = "propriete"

    chemin_txt = os.path.join(dossier, f"rapport_PSG_{nom_fichier_propre}.txt")
    chemin_csv = os.path.join(dossier, f"rapport_PSG_{nom_fichier_propre}.csv")
    return chemin_txt, chemin_csv


def demander_dossier_export(nom_propriete_affichage):
    """
    Ouvre une fenêtre de sélection de dossier pour choisir où enregistrer
    le rapport, et construit les chemins complets des fichiers .txt et .csv.

    Retourne un tuple (chemin_txt, chemin_csv).
    """
    dossier_choisi = QFileDialog.getExistingDirectory(
        None,
        "Diagnostic PSG — Choisissez le dossier d'enregistrement du rapport",
        DOSSIER_EXPORT_PAR_DEFAUT if os.path.isdir(DOSSIER_EXPORT_PAR_DEFAUT) else ""
    )

    if not dossier_choisi:
        # L'utilisateur a annulé : on se replie sur le dossier par défaut
        dossier_choisi = DOSSIER_EXPORT_PAR_DEFAUT
        os.makedirs(dossier_choisi, exist_ok=True)

    return construire_chemins_rapport(dossier_choisi, nom_propriete_affichage)


def demander_couche_propriete(ids_a_exclure=None):
    """
    Ouvre une fenêtre de dialogue QGIS permettant de choisir, parmi les
    couches POLYGONALES actuellement chargées dans le projet, celle qui
    représente le contour de la propriété/zone à analyser, puis demande
    le nom à afficher dans le rapport.

    ids_a_exclure : ensemble d'identifiants de couches à ne PAS proposer
    (typiquement les couches de zonage tout juste chargées depuis le
    GeoPackage, pour ne pas les confondre avec la propriété).

    Retourne un tuple (couche_choisie, nom_affichage).
    Lève une exception si l'utilisateur annule ou si aucune couche
    polygonale n'est disponible.
    """
    ids_a_exclure = ids_a_exclure or set()

    toutes_les_couches = list(QgsProject.instance().mapLayers().values())
    couches_polygonales = [
        c for c in toutes_les_couches
        if isinstance(c, QgsVectorLayer)
        and c.isValid()
        and c.id() not in ids_a_exclure
        and QgsWkbTypes.geometryType(c.wkbType()) == QgsWkbTypes.PolygonGeometry
    ]

    if not couches_polygonales:
        raise ValueError(
            "Aucune couche polygonale (hors couches de zonage) n'est "
            "actuellement chargée dans le projet. Chargez le contour de "
            "votre propriété/zone à analyser, puis relancez le script."
        )

    noms_disponibles = [c.name() for c in couches_polygonales]

    nom_choisi, confirme = QInputDialog.getItem(
        None,
        "Diagnostic PSG — Sélection de la propriété",
        "Choisissez la couche représentant le contour de la\n"
        "propriété (ou de la zone) à analyser :",
        noms_disponibles,
        0,      # index par défaut
        False   # liste non éditable
    )

    if not confirme:
        raise ValueError("Sélection annulée par l'utilisateur : diagnostic interrompu.")

    couche_choisie = next(c for c in couches_polygonales if c.name() == nom_choisi)

    nom_affichage, confirme_nom = QInputDialog.getText(
        None,
        "Diagnostic PSG — Nom de la propriété",
        "Nom à afficher dans le rapport et les noms de fichiers :",
        text=nom_choisi
    )

    if not confirme_nom or not nom_affichage.strip():
        nom_affichage = nom_choisi  # repli sur le nom de la couche si champ vide

    return couche_choisie, nom_affichage.strip()


def construire_couche_propriete_unique(couche_propriete, utiliser_selection):
    """Fusionne les entités de la couche propriété (sélection ou totalité)
    en une seule géométrie, et retourne une couche mémoire à une seule
    entité représentant le contour global de la propriété."""

    if utiliser_selection and couche_propriete.selectedFeatureCount() > 0:
        entites = list(couche_propriete.selectedFeatures())
    else:
        entites = list(couche_propriete.getFeatures())

    if not entites:
        raise ValueError(
            "Aucune entité trouvée dans la couche propriété "
            f"'{couche_propriete.name()}'. Vérifiez qu'elle contient bien "
            "des polygones (et une sélection, si UTILISER_SELECTION_SI_PRESENTE=True)."
        )

    geometries = [e.geometry() for e in entites if e.geometry() and not e.geometry().isEmpty()]
    geometrie_fusionnee = QgsGeometry.unaryUnion(geometries)

    couche_temp = QgsVectorLayer(
        f"Polygon?crs={couche_propriete.crs().authid()}",
        "propriete_fusionnee_temp",
        "memory"
    )
    provider = couche_temp.dataProvider()
    entite_temp = QgsFeature()
    entite_temp.setGeometry(geometrie_fusionnee)
    provider.addFeature(entite_temp)
    couche_temp.updateExtents()

    return couche_temp


def obtenir_ou_creer_groupe(nom_groupe):
    """Retourne le groupe de couches portant ce nom dans le projet,
    en le créant s'il n'existe pas encore."""
    racine = QgsProject.instance().layerTreeRoot()
    groupe = racine.findGroup(nom_groupe)
    if groupe is None:
        groupe = racine.insertGroup(0, nom_groupe)
    return groupe


def analyser_couche_repartition(couche_propriete_unique, surface_propriete_ha, calculateur,
                                 groupe_resultats, nom_couche, champ_principal,
                                 champ_secondaire=None, champ_lien=None,
                                 normaliser_parentheses=False, prefixe_extraction="Contexte"):
    """
    Analyse générique "par répartition" : contrairement à un zonage
    réglementaire (touché / pas touché), la couche COUVRE TOUTE la
    propriété mais avec des valeurs différentes selon les secteurs
    (types de sol, sylvoécorégions, zones climatiques...). Calcule, pour
    CHAQUE valeur distincte du champ principal, la surface occupée sur la
    propriété, et extrait le contexte complet dans le projet.

    Si normaliser_parentheses=True, tout suffixe entre parenthèses est
    retiré de la valeur du champ principal avant regroupement (utile pour
    la carte des sols, où "CALCOSOL(65%)" et "CALCOSOL(70%)" doivent être
    comptés comme un seul type "CALCOSOL").

    Retourne une liste de dictionnaires triée par surface décroissante :
    [{"type": ..., "description": ..., "lien": ..., "surface_ha": ..., "pourcentage": ...}, ...]
    Retourne None si la couche n'est pas chargée dans le projet.
    """
    couche_source = obtenir_couche_par_nom(nom_couche)
    if couche_source is None:
        return None

    # --- Intersection avec la propriété ---
    resultat_intersection = processing.run("native:intersection", {
        'INPUT': couche_propriete_unique,
        'OVERLAY': couche_source,
        'INPUT_FIELDS': [],
        'OUTPUT': 'memory:'
    })
    couche_intersection = resultat_intersection['OUTPUT']

    if couche_intersection.featureCount() == 0:
        return []

    # --- Regroupement par valeur du champ principal, cumul des surfaces ---
    repartition = {}  # {valeur: {"m2": float, "description": str, "lien": str}}
    champs = couche_intersection.fields()
    a_champ_principal = champs.indexOf(champ_principal) != -1
    a_champ_secondaire = champ_secondaire and champs.indexOf(champ_secondaire) != -1
    a_champ_lien = champ_lien and champs.indexOf(champ_lien) != -1

    if not a_champ_principal:
        raise ValueError(
            f"Le champ '{champ_principal}' est introuvable dans la couche "
            f"'{nom_couche}'. Vérifiez le nom du champ (et sa casse exacte)."
        )

    for entite in couche_intersection.getFeatures():
        geom = entite.geometry()
        if not geom or geom.isEmpty():
            continue

        valeur = entite[champ_principal]
        valeur = str(valeur) if valeur is not None else "Non renseigné"

        if normaliser_parentheses:
            valeur = re.sub(r'\s*\([^)]*\)\s*$', '', valeur).strip()

        if valeur not in repartition:
            repartition[valeur] = {
                "m2": 0.0,
                "description": str(entite[champ_secondaire]) if a_champ_secondaire and entite[champ_secondaire] is not None else "",
                "lien": str(entite[champ_lien]) if a_champ_lien and entite[champ_lien] is not None else "",
            }

        repartition[valeur]["m2"] += calculateur.measureArea(geom)

    # --- Extraction du contexte complet (toutes valeurs confondues) ---
    resultat_extraction = processing.run("native:extractbylocation", {
        'INPUT': couche_source,
        'PREDICATE': [0],  # intersects
        'INTERSECT': couche_propriete_unique,
        'OUTPUT': 'memory:'
    })
    couche_extraite = resultat_extraction['OUTPUT']
    if couche_extraite.featureCount() > 0:
        couche_extraite.setName(f"{prefixe_extraction} - {nom_couche}")
        try:
            if couche_source.renderer() is not None:
                couche_extraite.setRenderer(couche_source.renderer().clone())
            if couche_source.labelsEnabled():
                couche_extraite.setLabeling(couche_source.labeling().clone())
                couche_extraite.setLabelsEnabled(True)
        except Exception as erreur_style:
            QgsMessageLog.logMessage(
                f"Impossible de reprendre la symbologie de '{nom_couche}' : {erreur_style}",
                "Diagnostic PSG", level=Qgis.Warning
            )
        QgsProject.instance().addMapLayer(couche_extraite, False)
        groupe_resultats.addLayer(couche_extraite)
        couche_extraite.triggerRepaint()

    # --- Mise en forme des résultats, triés par surface décroissante ---
    resultats = []
    for valeur, infos in repartition.items():
        surface_ha = calculateur.convertAreaMeasurement(infos["m2"], QgsUnitTypes.AreaHectares)
        pourcentage = (surface_ha / surface_propriete_ha) * 100 if surface_propriete_ha > 0 else 0
        resultats.append({
            "type": valeur,
            "description": infos["description"],
            "lien": infos["lien"],
            "surface_ha": surface_ha,
            "pourcentage": pourcentage,
        })

    resultats.sort(key=lambda r: r["surface_ha"], reverse=True)
    return resultats


def analyser_zonage(couche_propriete_unique, surface_propriete_ha, calculateur,
                     couche_zonage, couche_reference_style, libelle_affichage,
                     groupe_resultats, champ_nom=None):
    """
    Réalise les deux opérations géométriques demandées pour UNE couche de
    zonage donnée (déjà résolue/fusionnée) :
      1. Intersection (native:intersection) -> calcul de surface OU longueur
         touchée, selon le type de géométrie de la couche
      2. Extraction des entités entières (native:extractbylocation) ->
         chargement du polygone/ligne complet dans le projet si intersection,
         avec reprise de la symbologie (couleurs, style) de la couche
         d'origine (couche_reference_style)

    Si champ_nom est renseigné, collecte aussi la liste des valeurs
    distinctes de ce champ parmi les entités intersectées (ex: noms des
    sites Natura 2000 effectivement concernés par la propriété).

    Retourne un dictionnaire de résultats pour le rapport.
    """

    type_geom = type_geometrie_couche(couche_zonage)
    est_surfacique = (type_geom == QgsWkbTypes.PolygonGeometry)
    est_lineaire = (type_geom == QgsWkbTypes.LineGeometry)

    resultat = {
        "libelle": libelle_affichage,
        "type_geometrie": "surface" if est_surfacique else ("lineaire" if est_lineaire else "point"),
        "intersecte": False,
        "valeur": 0.0,          # ha si surfacique, km si linéaire
        "pourcentage": None,    # uniquement pertinent pour le surfacique
        "nb_entites_extraites": 0,
        "extrait_dans_projet": False,
        "noms_entites": [],     # noms des sites concernés (si champ_nom fourni)
    }

    # --- 1. Calcul de la valeur intersectée (découpage à la propriété) ---
    resultat_intersection = processing.run("native:intersection", {
        'INPUT': couche_propriete_unique,
        'OVERLAY': couche_zonage,
        'INPUT_FIELDS': [],
        'OVERLAY_FIELDS': [],
        'OVERLAY_FIELDS_PREFIX': '',
        'OUTPUT': 'memory:'
    })
    couche_intersection = resultat_intersection['OUTPUT']

    if couche_intersection.featureCount() > 0:
        resultat["intersecte"] = True

        if est_surfacique:
            valeur = surface_totale_ha(couche_intersection, calculateur)
            resultat["valeur"] = valeur
            resultat["pourcentage"] = (
                (valeur / surface_propriete_ha) * 100 if surface_propriete_ha > 0 else 0
            )
        elif est_lineaire:
            valeur = longueur_totale_km(couche_intersection, calculateur)
            resultat["valeur"] = valeur
            # Le pourcentage n'a pas de sens pour un linéaire par rapport à
            # une surface de propriété : on ne le calcule pas.
        else:
            # Cas ponctuel (rare dans ce contexte) : on compte simplement les entités
            resultat["valeur"] = couche_intersection.featureCount()

        # --- Collecte des noms de sites, si un champ (ou une liste de champs) a été indiqué ---
        if champ_nom:
            champs_demandes = champ_nom if isinstance(champ_nom, list) else [champ_nom]
            champs_disponibles = couche_intersection.fields()
            champs_valides = [c for c in champs_demandes if champs_disponibles.indexOf(c) != -1]
            champs_absents = [c for c in champs_demandes if c not in champs_valides]

            if champs_absents:
                QgsMessageLog.logMessage(
                    f"'{libelle_affichage}' : champ(s) introuvable(s) pour l'affichage "
                    f"du nom : {', '.join(champs_absents)}.",
                    "Diagnostic PSG", level=Qgis.Warning
                )

            if champs_valides:
                noms_rencontres = set()
                for entite in couche_intersection.getFeatures():
                    morceaux = []
                    for champ in champs_valides:
                        valeur_champ = entite[champ]
                        if valeur_champ is not None and str(valeur_champ).strip():
                            morceaux.append(str(valeur_champ).strip())
                    if morceaux:
                        noms_rencontres.add(" - ".join(morceaux))
                resultat["noms_entites"] = sorted(noms_rencontres)

        # --- 2. Extraction des entités ENTIÈRES (contexte global) ---
        # Prédicat 0 = "intersecte" (voir énumération native:extractbylocation)
        resultat_extraction = processing.run("native:extractbylocation", {
            'INPUT': couche_zonage,
            'PREDICATE': [0],  # 0 = intersects
            'INTERSECT': couche_propriete_unique,
            'OUTPUT': 'memory:'
        })
        couche_extraite = resultat_extraction['OUTPUT']
        nb_entites = couche_extraite.featureCount()
        resultat["nb_entites_extraites"] = nb_entites

        if nb_entites > 0:
            nom_couche_finale = f"Contexte - {libelle_affichage}"
            couche_extraite.setName(nom_couche_finale)

            # --- Reprise de la symbologie d'origine ---
            # On clone le renderer (couleurs/styles) et, si présent,
            # l'étiquetage de la couche source, pour que la couche extraite
            # ait exactement le même rendu visuel que dans le GeoPackage.
            if couche_reference_style is not None:
                try:
                    if couche_reference_style.renderer() is not None:
                        couche_extraite.setRenderer(couche_reference_style.renderer().clone())
                    if couche_reference_style.labelsEnabled():
                        couche_extraite.setLabeling(couche_reference_style.labeling().clone())
                        couche_extraite.setLabelsEnabled(True)
                    couche_extraite.setOpacity(couche_reference_style.opacity())
                except Exception as erreur_style:
                    QgsMessageLog.logMessage(
                        f"Impossible de reprendre la symbologie d'origine pour "
                        f"'{libelle_affichage}' : {erreur_style}",
                        "Diagnostic PSG", level=Qgis.Warning
                    )

            QgsProject.instance().addMapLayer(couche_extraite, False)
            groupe_resultats.addLayer(couche_extraite)
            couche_extraite.triggerRepaint()
            resultat["extrait_dans_projet"] = True

    return resultat


def formater_ligne_rapport(libelle_affichage, resultat):
    """Construit la ligne de texte du rapport pour un zonage donné, en
    adaptant le libellé selon qu'il s'agit d'une surface, d'un linéaire ou
    d'un zonage ponctuel. Ajoute le nom des entités concernées si
    disponible (champ_nom renseigné dans la configuration)."""

    if not resultat["intersecte"]:
        return f"- {libelle_affichage} : Pas d'intersection détectée."

    suffixe_extraction = (
        " (Polygone/entité entière extrait(e) dans le projet)"
        if resultat["extrait_dans_projet"] else ""
    )

    noms_entites = resultat.get("noms_entites") or []
    suffixe_noms = f" [Nom(s) : {', '.join(noms_entites)}]" if noms_entites else ""

    if resultat["type_geometrie"] == "surface":
        surface_str = f"{resultat['valeur']:.{DECIMALES_HA}f}"
        pct_str = f"{resultat['pourcentage']:.{DECIMALES_PCT}f}"
        return (
            f"- {libelle_affichage} : {surface_str} ha touchés "
            f"(soit {pct_str}% de la propriété).{suffixe_extraction}{suffixe_noms}"
        )

    elif resultat["type_geometrie"] == "lineaire":
        km_str = f"{resultat['valeur']:.{DECIMALES_KM}f}"
        return (
            f"- {libelle_affichage} : {km_str} km de linéaire présents "
            f"sur la propriété.{suffixe_extraction}{suffixe_noms}"
        )

    else:  # ponctuel
        return (
            f"- {libelle_affichage} : {int(resultat['valeur'])} entité(s) "
            f"ponctuelle(s) présente(s) sur la propriété.{suffixe_extraction}{suffixe_noms}"
        )


# ==============================================================================
# 3. SCRIPT PRINCIPAL
# ==============================================================================

def executer_diagnostic(forcer_dialogue_gpkg=False, couche_propriete=None,
                         nom_propriete_affichage=None, chemin_gpkg=None,
                         dossier_export=None):
    """
    Tous les paramètres sont optionnels : s'ils ne sont pas fournis, le
    script retombe sur son comportement habituel (popups interactifs ou
    valeurs fixes de la CONFIGURATION, selon les réglages DEMANDER_*).

    Fournis (ex: par l'interface graphique du plugin, ui_dialog.py), ils
    permettent de sauter les popups correspondants :
      - couche_propriete + nom_propriete_affichage : sélection de la propriété
      - chemin_gpkg : GeoPackage à charger
      - dossier_export : dossier où écrire le rapport
      - forcer_dialogue_gpkg : ouvre quand même la fenêtre de sélection du
        GeoPackage (ignoré si chemin_gpkg est fourni)
    """

    # --- Chargement automatique de toutes les couches du GeoPackage de zonages ---
    groupe_gpkg = None
    if CHARGER_GPKG_AUTOMATIQUEMENT:
        if chemin_gpkg:
            chemin_gpkg_choisi = chemin_gpkg
        elif DEMANDER_CHEMIN_GPKG_INTERACTIVEMENT or forcer_dialogue_gpkg:
            chemin_gpkg_choisi = demander_chemin_gpkg()
        else:
            chemin_gpkg_choisi = CHEMIN_GPKG_ZONAGES_PAR_DEFAUT
        if chemin_gpkg_choisi:
            groupe_gpkg = charger_couches_gpkg(chemin_gpkg_choisi, NOM_GROUPE_GPKG)
    ids_couches_zonages = obtenir_ids_couches_du_groupe(groupe_gpkg)

    # --- Sélection de la couche propriété : fournie, interactive, ou fixe ---
    if couche_propriete is not None and nom_propriete_affichage:
        pass  # déjà fournis par l'appelant (interface du plugin)
    elif DEMANDER_COUCHE_INTERACTIVEMENT:
        couche_propriete, nom_propriete_affichage = demander_couche_propriete(ids_couches_zonages)
    else:
        couche_propriete = obtenir_couche_par_nom(NOM_COUCHE_PROPRIETE)
        if couche_propriete is None:
            raise ValueError(
                f"La couche propriété '{NOM_COUCHE_PROPRIETE}' n'est pas chargée "
                "dans le projet. Vérifiez la variable NOM_COUCHE_PROPRIETE."
            )
        nom_propriete_affichage = NOM_PROPRIETE_AFFICHAGE

    # --- Choix du dossier d'export : fourni, interactif, ou fixe ---
    if dossier_export:
        os.makedirs(dossier_export, exist_ok=True)
        chemin_rapport_txt, chemin_rapport_csv = construire_chemins_rapport(dossier_export, nom_propriete_affichage)
    elif DEMANDER_DOSSIER_EXPORT:
        chemin_rapport_txt, chemin_rapport_csv = demander_dossier_export(nom_propriete_affichage)
    else:
        os.makedirs(DOSSIER_EXPORT_PAR_DEFAUT, exist_ok=True)
        chemin_rapport_txt, chemin_rapport_csv = construire_chemins_rapport(DOSSIER_EXPORT_PAR_DEFAUT, nom_propriete_affichage)

    print("=" * 70)
    print(f"DÉMARRAGE DU DIAGNOSTIC PSG — {nom_propriete_affichage}")
    print("=" * 70)

    # --- Fusion en une géométrie unique (gère multi-parcelles / sélection) ---
    couche_propriete_unique = construire_couche_propriete_unique(
        couche_propriete, UTILISER_SELECTION_SI_PRESENTE
    )

    # --- Calculateur de surface/longueur basé sur l'ellipsoïde du projet ---
    calculateur = creer_calculateur_surface(couche_propriete.crs())
    surface_propriete_ha = surface_totale_ha(couche_propriete_unique, calculateur)

    if surface_propriete_ha <= 0:
        raise ValueError(
            "La surface calculée de la propriété est nulle. Vérifiez la "
            "géométrie de la couche propriété."
        )

    print(f"Surface totale de la propriété : {surface_propriete_ha:.{DECIMALES_HA}f} ha")

    # --- Groupe de couches pour les résultats ---
    groupe_resultats = obtenir_ou_creer_groupe(NOM_GROUPE_RESULTATS)

    # --- Analyse de chaque couche de zonage, thématique par thématique ---
    lignes_rapport = []
    lignes_csv = []
    lignes_rapport.append(f"[PROPRIÉTÉ : {nom_propriete_affichage}]")
    lignes_rapport.append(f"Surface totale analysée : {surface_propriete_ha:.{DECIMALES_HA}f} ha\n")

    # --- Section Généralités (Sylvoécorégion, Climat, etc.) ---
    if ANALYSER_GENERALITES:
        lignes_rapport.append("")
        lignes_rapport.append("--- Généralités ---")
        lignes_rapport.append("")
        for entree_generalite in GENERALITES:
            titre = entree_generalite["titre"]
            try:
                repartition = analyser_couche_repartition(
                    couche_propriete_unique, surface_propriete_ha, calculateur, groupe_resultats,
                    nom_couche=entree_generalite["couche"],
                    champ_principal=entree_generalite["champ_principal"],
                    champ_secondaire=entree_generalite.get("champ_secondaire"),
                    prefixe_extraction="Contexte",
                )
            except Exception as erreur:
                lignes_rapport.append(f"- {titre} : ERREUR lors de l'analyse ({erreur})")
                QgsMessageLog.logMessage(
                    f"Erreur sur '{titre}' : {erreur}", "Diagnostic PSG", level=Qgis.Warning
                )
                lignes_csv.append(["Généralités", titre, "Erreur", "", "", "", ""])
                continue

            texte_source = entree_generalite.get("texte_source")
            suffixe_source = f" — {texte_source}" if texte_source else ""

            if repartition is None:
                lignes_rapport.append(
                    f"- {titre} : couche non chargée dans le projet "
                    f"(attendue sous le nom '{entree_generalite['couche']}')."
                )
                lignes_csv.append(["Généralités", titre, "Non chargée", "", "", "", ""])
            elif not repartition:
                lignes_rapport.append(f"- {titre} : Pas d'intersection détectée.")
                lignes_csv.append(["Généralités", titre, "0", "0", "Non", "0", "surface"])
            else:
                for entree in repartition:
                    surface_str = f"{entree['surface_ha']:.{DECIMALES_HA}f}"
                    pct_str = f"{entree['pourcentage']:.{DECIMALES_PCT}f}"
                    description_str = f" ({entree['description']})" if entree["description"] else ""
                    lignes_rapport.append(
                        f"- {titre} : {entree['type']}{description_str} — {surface_str} ha "
                        f"(soit {pct_str}% de la propriété).{suffixe_source}"
                    )
                    lignes_csv.append([
                        "Généralités", f"{titre} - {entree['type']}",
                        surface_str, pct_str, "Oui", "1", "surface"
                    ])
        lignes_rapport.append("")

    for thematique, couches_dict in COUCHES_ZONAGES.items():
        lignes_rapport.append("")
        lignes_rapport.append(f"--- {thematique} ---")
        lignes_rapport.append("")

        for libelle_affichage, reference_couche in couches_dict.items():

            couche_zonage, noms_manquants, couche_reference_style, champ_nom = obtenir_couche_zonage(reference_couche)

            # Cas : aucune des couches demandées n'est chargée dans le projet
            if couche_zonage is None:
                noms_str = ", ".join(noms_manquants)
                lignes_rapport.append(
                    f"- {libelle_affichage} : couche non chargée dans le projet "
                    f"(attendue sous le nom '{noms_str}')."
                )
                lignes_csv.append([thematique, libelle_affichage, "Non chargée", "", "", "", ""])
                continue

            # Cas : fusion partielle (certaines couches de la liste manquent)
            if noms_manquants:
                noms_str = ", ".join(noms_manquants)
                QgsMessageLog.logMessage(
                    f"'{libelle_affichage}' : couche(s) manquante(s) ignorée(s) lors "
                    f"de la fusion : {noms_str}",
                    "Diagnostic PSG", level=Qgis.Warning
                )

            try:
                resultat = analyser_zonage(
                    couche_propriete_unique, surface_propriete_ha, calculateur,
                    couche_zonage, couche_reference_style, libelle_affichage, groupe_resultats,
                    champ_nom=champ_nom
                )
            except Exception as erreur:
                lignes_rapport.append(f"- {libelle_affichage} : ERREUR lors de l'analyse ({erreur})")
                QgsMessageLog.logMessage(
                    f"Erreur sur la couche '{libelle_affichage}' : {erreur}",
                    "Diagnostic PSG", level=Qgis.Warning
                )
                continue

            # --- Mise en forme de la ligne de rapport ---
            lignes_rapport.append(formater_ligne_rapport(libelle_affichage, resultat))

            # --- Ligne CSV ---
            if not resultat["intersecte"]:
                lignes_csv.append([thematique, libelle_affichage, "0", "0", "Non", "0", resultat["type_geometrie"]])
            else:
                decimales = DECIMALES_HA if resultat["type_geometrie"] == "surface" else DECIMALES_KM
                valeur_str = f"{resultat['valeur']:.{decimales}f}"
                pct_str = (
                    f"{resultat['pourcentage']:.{DECIMALES_PCT}f}"
                    if resultat["pourcentage"] is not None else "N/A"
                )
                lignes_csv.append([
                    thematique, libelle_affichage, valeur_str, pct_str,
                    "Oui" if resultat["extrait_dans_projet"] else "Non",
                    resultat["nb_entites_extraites"],
                    resultat["type_geometrie"],
                ])

        lignes_rapport.append("")  # ligne vide entre thématiques

    # --- Section dédiée : carte des sols (répartition, pas un simple zonage) ---
    if ANALYSER_CARTE_SOLS:
        lignes_rapport.append("")
        lignes_rapport.append("--- Contexte pédologique (informatif) ---")
        lignes_rapport.append("")
        try:
            repartition_sols = analyser_couche_repartition(
                couche_propriete_unique, surface_propriete_ha, calculateur, groupe_resultats,
                nom_couche=NOM_COUCHE_SOLS,
                champ_principal=CHAMP_TYPE_SOL,
                champ_secondaire=CHAMP_DESCRIPTION_SOL,
                champ_lien=CHAMP_LIEN_SOL,
                normaliser_parentheses=NORMALISER_TYPE_SOL,
                prefixe_extraction="Contexte",
            )
        except Exception as erreur:
            lignes_rapport.append(f"- Carte des sols : ERREUR lors de l'analyse ({erreur})")
            QgsMessageLog.logMessage(
                f"Erreur sur la carte des sols : {erreur}",
                "Diagnostic PSG", level=Qgis.Warning
            )
            repartition_sols = None

        if repartition_sols is None:
            lignes_rapport.append(
                f"- Carte des sols : couche non chargée dans le projet "
                f"(attendue sous le nom '{NOM_COUCHE_SOLS}')."
            )
            lignes_csv.append(["Contexte pédologique", "Carte des sols", "Non chargée", "", "", "", ""])
        elif not repartition_sols:
            lignes_rapport.append("- Carte des sols : Pas d'intersection détectée.")
            lignes_csv.append(["Contexte pédologique", "Carte des sols", "0", "0", "Non", "0", "surface"])
        else:
            for entree_sol in repartition_sols:
                surface_str = f"{entree_sol['surface_ha']:.{DECIMALES_HA}f}"
                pct_str = f"{entree_sol['pourcentage']:.{DECIMALES_PCT}f}"
                description_str = f" — {entree_sol['description']}" if entree_sol["description"] else ""
                lien_str = f" [Fiche : {entree_sol['lien']}]" if entree_sol["lien"] else ""
                lignes_rapport.append(
                    f"- Sol « {entree_sol['type']} »{description_str} : {surface_str} ha "
                    f"(soit {pct_str}% de la propriété).{lien_str}"
                )
                lignes_csv.append([
                    "Contexte pédologique", f"Sol - {entree_sol['type']}",
                    surface_str, pct_str, "Oui", "1", "surface"
                ])
        lignes_rapport.append("")

    # --- Écriture du rapport texte brut ---
    os.makedirs(os.path.dirname(chemin_rapport_txt), exist_ok=True)
    with open(chemin_rapport_txt, "w", encoding="utf-8") as fichier_txt:
        fichier_txt.write("\n".join(lignes_rapport))

    # --- Écriture du rapport CSV ---
    os.makedirs(os.path.dirname(chemin_rapport_csv), exist_ok=True)
    with open(chemin_rapport_csv, "w", encoding="utf-8", newline="") as fichier_csv:
        ecrivain = csv.writer(fichier_csv, delimiter=";")
        ecrivain.writerow([
            "Thématique", "Zonage", "Valeur (ha ou km)", "Pourcentage (%)",
            "Entité(s) entière(s) extraite(s)", "Nb entités extraites", "Type de géométrie"
        ])
        ecrivain.writerows(lignes_csv)

    print("\n" + "\n".join(lignes_rapport))
    print("=" * 70)
    print(f"Rapport texte exporté : {chemin_rapport_txt}")
    print(f"Rapport CSV exporté   : {chemin_rapport_csv}")
    print("=" * 70)


# ==============================================================================
# 4. POINT D'ENTRÉE
# ==============================================================================
# NB : contrairement au script autonome, ce module ne s'exécute PAS
# automatiquement à l'import. C'est plugin_main.py qui appelle
# executer_diagnostic() quand on clique sur le menu du plugin.
# (Rien à faire ici, la fonction est déjà définie ci-dessus.)
