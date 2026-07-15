# Analyse Environnementale — plugin QGIS

Plugin QGIS pour le pré-diagnostic environnemental et réglementaire des
Plans Simples de Gestion (PSG) forestiers en région PACA. Il analyse
automatiquement les contraintes (Natura 2000, ZNIEFF, réserves, EBC,
PPR, etc.) qui intersectent une propriété forestière, et génère un
rapport (.txt / .csv) ainsi que des couches de contexte dans le projet
QGIS.

## Structure du dépôt

```
analyse_environnementale/
├── __init__.py          # Point d'entrée technique du plugin (ne pas modifier)
├── metadata.txt          # Nom, version, description affichés par QGIS
├── plugin_main.py         # Intégration dans le menu/la barre d'outils QGIS
├── ui_dialog.py            # Fenêtre de sélection (propriété, GeoPackage, export)
├── diagnostic_logic.py     # Toute la logique métier : c'est ICI qu'on modifie
│                            # le dictionnaire des couches de zonage, les champs
│                            # de nom, etc.
├── icon.png / icon_dialog.png
└── donnees/
    └── (Analyse_environnementale.gpkg — NON versionné, voir ci-dessous)
```

## ⚠️ Le GeoPackage de données n'est PAS dans ce dépôt

Le fichier `donnees/Analyse_environnementale.gpkg` dépasse la limite de
100 Mo de GitHub. Il est distribué séparément via les **Releases** de ce
dépôt (onglet *Releases*, à droite de la page GitHub).

## Installation (utilisateurs finaux / collègues)

1. Télécharger la dernière version du plugin depuis l'onglet "Releases"
(⚠️ Attention : Ne téléchargez pas les liens "Source code" générés automatiquement par GitHub (ceux situés en bas de page). Ils ne contiennent pas les données SIG (fichiers .gpkg) et ne permettront pas au plugin de fonctionner correctement. Tout est expliqué dans la release note avec le lien de téléchargement)
2. QGIS : *Extensions > Installer/Gérer les extensions > Installer depuis
   un ZIP*
3. Sélectionner le fichier, Installer
4. Une icône apparaît dans la barre d'outils, et un menu
   *Analyse Environnementale* dans le menu Extensions

## Mettre à jour le plugin - Pour les developpeurs

- **Nouvelles couches / champs / logique d'analyse** → modifier
  `diagnostic_logic.py` (section `CONFIGURATION` en haut de fichier pour
  le dictionnaire `COUCHES_ZONAGES`, `GENERALITES`, etc.)
- **Nouvelles données reçues (ex: CNPF)** → mettre à jour le
  `.gpkg` localement, puis publier une nouvelle Release GitHub avec le
  fichier mis à jour
- **Apparence de la fenêtre** → `ui_dialog.py`
- **Menu / barre d'outils QGIS** → `plugin_main.py`


## Prérequis

QGIS 3.22 ou supérieur.
