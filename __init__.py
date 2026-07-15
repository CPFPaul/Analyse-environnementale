# -*- coding: utf-8 -*-
"""
Point d'entrée du plugin, requis par QGIS. Ne pas modifier sauf si vous
savez ce que vous faites : c'est ce fichier que QGIS appelle au démarrage
pour savoir comment charger le plugin.
"""


def classFactory(iface):
    from .plugin_main import DiagnosticPSGPlugin
    return DiagnosticPSGPlugin(iface)
