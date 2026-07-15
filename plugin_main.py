# -*- coding: utf-8 -*-
"""
Classe principale du plugin : ajoute une entrée de menu et un bouton dans
la barre d'outils QGIS. Un clic ouvre une petite fenêtre (ui_dialog.py)
pour choisir la propriété, la source des zonages et le dossier d'export,
puis lance le diagnostic (diagnostic_logic.py) avec ces choix.

Ce fichier n'a normalement PAS besoin d'être modifié pour les mises à jour
courantes (nouvelles couches, nouveaux champs, etc.) : tout ça se passe
dans diagnostic_logic.py.
"""

import os
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon


class DiagnosticPSGPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.nom_menu = "&Analyse Environnementale"
        self.dossier_plugin = os.path.dirname(os.path.abspath(__file__))

    def initGui(self):
        icone = QIcon(os.path.join(self.dossier_plugin, "icon.png"))

        self.action_principale = QAction(icone, "Lancer l'analyse environnementale", self.iface.mainWindow())
        self.action_principale.triggered.connect(self.ouvrir_fenetre)
        self.iface.addToolBarIcon(self.action_principale)
        self.iface.addPluginToMenu(self.nom_menu, self.action_principale)
        self.actions.append(self.action_principale)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.nom_menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []

    def ouvrir_fenetre(self):
        # Imports différés : si diagnostic_logic.py ou ui_dialog.py contient
        # une erreur après une modification, QGIS démarre quand même et
        # affiche un message clair plutôt que de bloquer le chargement du
        # plugin entier.
        try:
            from . import diagnostic_logic
            from .ui_dialog import DiagnosticPSGDialog
        except Exception as erreur:
            QMessageBox.critical(
                self.iface.mainWindow(), "Analyse Environnementale — Erreur de chargement",
                f"Impossible de charger le plugin :\n\n{erreur}"
            )
            raise

        chemin_icone_dialog = os.path.join(self.dossier_plugin, "icon_dialog.png")
        fenetre = DiagnosticPSGDialog(
            parent=self.iface.mainWindow(),
            chemin_icone=chemin_icone_dialog,
            chemin_gpkg_defaut=diagnostic_logic.CHEMIN_GPKG_ZONAGES_PAR_DEFAUT,
            dossier_export_defaut=diagnostic_logic.DOSSIER_EXPORT_PAR_DEFAUT,
        )

        if fenetre.exec_():
            couche, nom_affichage, chemin_gpkg, dossier_export = fenetre.obtenir_resultats()
            try:
                diagnostic_logic.executer_diagnostic(
                    couche_propriete=couche,
                    nom_propriete_affichage=nom_affichage,
                    chemin_gpkg=chemin_gpkg,
                    dossier_export=dossier_export,
                )
                self.iface.messageBar().pushSuccess(
                    "Analyse Environnementale", f"Rapport généré pour « {nom_affichage} »."
                )
            except Exception as erreur:
                QMessageBox.critical(
                    self.iface.mainWindow(), "Analyse Environnementale — Erreur",
                    f"Une erreur est survenue pendant le diagnostic :\n\n{erreur}\n\n"
                    "Consultez le panneau de messages QGIS (Affichage > Panneaux > "
                    "Messages) pour plus de détails."
                )
                raise

