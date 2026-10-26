"""Entrada convencional do gerenciador de complementos QGIS."""
def classFactory(iface):
    from .plugin import AuditoriaRedesPlugin
    return AuditoriaRedesPlugin(iface)
