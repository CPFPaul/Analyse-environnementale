# -*- coding: utf-8 -*-
"""
Fenêtre principale du plugin : remplace la suite de popups (QInputDialog /
QFileDialog en cascade) par une seule fenêtre regroupant tous les choix
avant de lancer le diagnostic.

Ce fichier gère uniquement l'AFFICHAGE. Toute la logique d'analyse reste
dans diagnostic_logic.py.
"""

import os
from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QGroupBox, QRadioButton, QFileDialog, QMessageBox,
    QDialogButtonBox, QFormLayout
)
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtCore import Qt


class DiagnosticPSGDialog(QDialog):

    def __init__(self, parent=None, chemin_icone=None, chemin_gpkg_defaut=None,
                 dossier_export_defaut=""):
        super().__init__(parent)
        self.chemin_gpkg_defaut = chemin_gpkg_defaut
        self.couches_disponibles = []

        self.setWindowTitle("Analyse Environnementale")
        self.setMinimumWidth(460)
        self._construire_interface(chemin_icone, dossier_export_defaut)
        self._peupler_couches()

    # --------------------------------------------------------------------
    # Construction de l'interface
    # --------------------------------------------------------------------
    def _construire_interface(self, chemin_icone, dossier_export_defaut):
        layout_principal = QVBoxLayout(self)
        layout_principal.setSpacing(14)

        # --- En-tête (icône + titre) ---
        entete = QHBoxLayout()
        if chemin_icone and os.path.isfile(chemin_icone):
            label_icone = QLabel()
            pixmap = QPixmap(chemin_icone).scaled(
                48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            label_icone.setPixmap(pixmap)
            entete.addWidget(label_icone)

        bloc_titre = QVBoxLayout()
        titre = QLabel("Analyse Environnementale")
        titre.setStyleSheet("font-size: 15pt; font-weight: bold;")
        sous_titre = QLabel("Pré-diagnostic environnemental et réglementaire")
        sous_titre.setStyleSheet("color: #666;")
        bloc_titre.addWidget(titre)
        bloc_titre.addWidget(sous_titre)
        entete.addLayout(bloc_titre)
        entete.addStretch()
        layout_principal.addLayout(entete)

        # --- Groupe : propriété à analyser ---
        groupe_propriete = QGroupBox("Propriété à analyser")
        form_propriete = QFormLayout()
        self.combo_couche = QComboBox()
        self.combo_couche.currentTextChanged.connect(self._nom_propriete_auto)
        form_propriete.addRow("Couche du contour :", self.combo_couche)
        self.champ_nom_propriete = QLineEdit()
        form_propriete.addRow("Nom dans le rapport :", self.champ_nom_propriete)
        groupe_propriete.setLayout(form_propriete)
        layout_principal.addWidget(groupe_propriete)

        # --- Groupe : source des zonages ---
        groupe_gpkg = QGroupBox("Source des zonages environnementaux")
        layout_gpkg = QVBoxLayout()
        self.radio_gpkg_integre = QRadioButton("GeoPackage intégré au plugin (recommandé)")
        self.radio_gpkg_integre.setChecked(True)
        layout_gpkg.addWidget(self.radio_gpkg_integre)

        self.radio_gpkg_autre = QRadioButton("Autre GeoPackage :")
        layout_gpkg.addWidget(self.radio_gpkg_autre)

        ligne_autre = QHBoxLayout()
        self.champ_gpkg = QLineEdit()
        self.champ_gpkg.setReadOnly(True)
        self.champ_gpkg.setEnabled(False)
        bouton_parcourir_gpkg = QPushButton("Parcourir…")
        bouton_parcourir_gpkg.clicked.connect(self._choisir_gpkg)
        ligne_autre.addWidget(self.champ_gpkg)
        ligne_autre.addWidget(bouton_parcourir_gpkg)
        layout_gpkg.addLayout(ligne_autre)

        self.radio_gpkg_autre.toggled.connect(self.champ_gpkg.setEnabled)
        groupe_gpkg.setLayout(layout_gpkg)
        layout_principal.addWidget(groupe_gpkg)

        # --- Groupe : export du rapport ---
        groupe_export = QGroupBox("Export du rapport (.txt + .csv)")
        ligne_export = QHBoxLayout()
        self.champ_dossier_export = QLineEdit(dossier_export_defaut)
        bouton_parcourir_export = QPushButton("Parcourir…")
        bouton_parcourir_export.clicked.connect(self._choisir_dossier_export)
        ligne_export.addWidget(self.champ_dossier_export)
        ligne_export.addWidget(bouton_parcourir_export)
        groupe_export.setLayout(ligne_export)
        layout_principal.addWidget(groupe_export)

        # --- Boutons ---
        boutons = QDialogButtonBox()
        self.bouton_lancer = boutons.addButton("Lancer le diagnostic", QDialogButtonBox.AcceptRole)
        self.bouton_lancer.setStyleSheet(
            "QPushButton { font-weight: bold; padding: 6px 14px; }"
        )
        boutons.addButton("Annuler", QDialogButtonBox.RejectRole)
        boutons.accepted.connect(self._valider)
        boutons.rejected.connect(self.reject)
        layout_principal.addWidget(boutons)

    # --------------------------------------------------------------------
    # Peuplement / comportements dynamiques
    # --------------------------------------------------------------------
    def _peupler_couches(self):
        self.couches_disponibles = [
            c for c in QgsProject.instance().mapLayers().values()
            if isinstance(c, QgsVectorLayer) and c.isValid()
            and QgsWkbTypes.geometryType(c.wkbType()) == QgsWkbTypes.PolygonGeometry
        ]
        self.combo_couche.clear()
        for couche in self.couches_disponibles:
            self.combo_couche.addItem(couche.name())
        if self.couches_disponibles:
            self._nom_propriete_auto(self.couches_disponibles[0].name())
        else:
            self.champ_nom_propriete.setEnabled(False)
            self.combo_couche.addItem("(aucune couche polygonale chargée)")

    def _nom_propriete_auto(self, nom_couche):
        # Ne remplace le nom que si le champ est vide ou contenait encore
        # le nom d'une autre couche (pour ne pas écraser une saisie manuelle)
        noms_couches = [c.name() for c in self.couches_disponibles]
        if not self.champ_nom_propriete.text().strip() or self.champ_nom_propriete.text() in noms_couches:
            self.champ_nom_propriete.setText(nom_couche)

    def _choisir_gpkg(self):
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Choisir un GeoPackage de zonages", "", "GeoPackage (*.gpkg)"
        )
        if chemin:
            self.champ_gpkg.setText(chemin)
            self.radio_gpkg_autre.setChecked(True)

    def _choisir_dossier_export(self):
        dossier = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier d'export du rapport", self.champ_dossier_export.text()
        )
        if dossier:
            self.champ_dossier_export.setText(dossier)

    # --------------------------------------------------------------------
    # Validation
    # --------------------------------------------------------------------
    def _valider(self):
        if not self.couches_disponibles:
            QMessageBox.warning(
                self, "Analyse Environnementale",
                "Aucune couche polygonale n'est chargée dans le projet.\n"
                "Chargez le contour de votre propriété avant de lancer le diagnostic."
            )
            return
        if not self.champ_dossier_export.text().strip():
            QMessageBox.warning(self, "Analyse Environnementale", "Veuillez choisir un dossier d'export.")
            return
        if self.radio_gpkg_autre.isChecked() and not self.champ_gpkg.text().strip():
            QMessageBox.warning(self, "Analyse Environnementale", "Veuillez choisir un GeoPackage.")
            return
        self.accept()

    def obtenir_resultats(self):
        """Retourne (couche_propriete, nom_affichage, chemin_gpkg, dossier_export)."""
        index = self.combo_couche.currentIndex()
        couche = self.couches_disponibles[index]
        nom_affichage = self.champ_nom_propriete.text().strip() or couche.name()
        chemin_gpkg = self.champ_gpkg.text().strip() if self.radio_gpkg_autre.isChecked() else self.chemin_gpkg_defaut
        dossier_export = self.champ_dossier_export.text().strip()
        return couche, nom_affichage, chemin_gpkg, dossier_export
