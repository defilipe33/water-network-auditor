"""Resolve somente os pacotes embarcados, sem alterar PYTHONPATH/sys.path."""
import importlib.abc
import importlib.machinery
from pathlib import Path
import sys
from hashlib import sha256

PACOTES={'auditoria_fronteiras','auditoria_topologica_watergems','auditoria_aplicacao','AUDITORIA_FRONTEIRAS','AUDITORIA_TOPOLOGICA_WATERGEMS'}
class Bibliotecas(importlib.abc.MetaPathFinder):
    def __init__(self,raiz):self.raiz=Path(raiz).resolve()
    def find_spec(self,fullname,path=None,target=None):
        if fullname in PACOTES:return importlib.machinery.PathFinder.find_spec(fullname,[str(self.raiz)])
        return None
def ativar(raiz):
    raiz=Path(raiz).resolve()
    manifesto=raiz.parent/'MANIFESTO.json'
    assinatura=sha256(manifesto.read_bytes()).hexdigest()
    registro=(str(raiz),assinatura)
    carregados=any(nome in sys.modules for nome in PACOTES)
    if carregados and getattr(sys,'_auditoria_redes_bibliotecas',None)!=registro:
        raise RuntimeError('Bibliotecas de outra distribuição já carregadas. Reinicie o QGIS para aplicar a atualização com segurança.')
    for nome in PACOTES:
        m=sys.modules.get(nome)
        if m is not None and getattr(m,'__file__',None) and not Path(m.__file__).resolve().is_relative_to(raiz):
            raise RuntimeError('Módulos de outra instalação já carregados. Reinicie o QGIS para evitar misturar versões: '+nome)
    sys._auditoria_redes_bibliotecas=registro
    finder=Bibliotecas(raiz);sys.meta_path.insert(0,finder);return finder
