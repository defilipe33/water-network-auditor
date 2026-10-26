"""Execute pelo console QGIS após incluir a pasta scripts em sys.path."""
def abrir_interface():
    from auditoria_topologica_watergems.interface import abrir_interface as abrir
    return abrir()


def abrir_integracao():
    from auditoria_topologica_watergems.interface_integracao import abrir_integracao as abrir
    return abrir()


def abrir_diagnosticos(gpkg,versao=None):
    """Reabre o snapshot integrado sem reprocessar os arquivos de entrada."""
    from auditoria_topologica_watergems.saidas_integracao import reabrir
    from auditoria_topologica_watergems.painel_diagnosticos import abrir_diagnosticos as abrir
    from qgis.utils import iface
    from qgis.core import QgsProject
    global _diagnosticos
    anterior=globals().get('_diagnosticos')
    if anterior and anterior._ativo and hasattr(anterior,'resolver_alteracoes') and not anterior.resolver_alteracoes():return anterior
    if anterior and anterior._ativo and not hasattr(anterior,'resolver_alteracoes') and anterior.legado.tem_edicoes() and not anterior.legado.resolver_edicoes():return anterior
    novo=abrir(reabrir(gpkg,versao),gpkg,QgsProject.instance(),
        iface.mainWindow() if iface else None,iface.mapCanvas() if iface else None)
    if anterior:anterior.desativar()
    _diagnosticos=novo
    return _diagnosticos


if __name__=='__main__':
    abrir_interface()
