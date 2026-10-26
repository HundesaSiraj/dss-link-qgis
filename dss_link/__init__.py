"""QGIS entry point for DSS Link."""


def classFactory(iface):
    from .plugin import DssLinkPlugin

    return DssLinkPlugin(iface)
