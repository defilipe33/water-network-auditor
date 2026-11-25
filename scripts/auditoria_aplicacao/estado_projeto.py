"""Preferências de consulta e rascunho separados das fotografias."""

from pathlib import Path
from hashlib import sha256
import json
from math import isfinite

from .manifesto_projeto import gravar_json
from .trabalhos_projeto import agora


VISUAL = 'visualizacao'
RASCUNHO = 'rascunho'


def caminho_relativo(projeto, tipo):
    if tipo not in (VISUAL,RASCUNHO):
        raise ValueError('Tipo de estado desconhecido.')
    # Vários manifestos antigos podem estar na mesma pasta.
    ident = sha256(projeto['uuid'].encode()).hexdigest()[:24]
    return Path('estado')/ident/(tipo+'.json')


def arquivo(raiz, projeto, tipo):
    relativo = caminho_relativo(projeto, tipo)
    if projeto.get('manifesto_wna'):
        return Path(projeto['manifesto_wna']).parent/relativo
    return Path(raiz)/'estado_projetos'/Path(*relativo.parts[1:])


def ler(raiz, projeto, tipo):
    arq=arquivo(raiz,projeto,tipo)
    if not arq.is_file():
        return {}
    d=json.loads(arq.read_text(encoding='utf-8'))
    if (not isinstance(d,dict) or (d.get('versao'),d.get('projeto_uid'),d.get('tipo'))!=(1,projeto['uuid'],tipo)
            or not isinstance(d.get('dados'),dict)):
        raise ValueError(f'Identidade do estado de projeto incompatível: {arq}')
    return d['dados']


def atualizar(raiz, projeto, tipo, funcao):
    from .contexto_trabalho import Projetos
    arq=arquivo(raiz,projeto,tipo)
    arq.parent.mkdir(parents=True,exist_ok=True)
    with Projetos.trava(arq):
        d=ler(raiz,projeto,tipo)
        novo=funcao(d)
        if novo!=d:
            gravar_json(arq,dict(versao=1,projeto_uid=projeto['uuid'],tipo=tipo,dados=novo))
        return novo


def guardar_trabalho(raiz, projeto, tipo, uid, *, aberto=False, visual=None):
    def alterar(d):
        k=f'{tipo}:{uid}'
        anterior=d.get(k,{})
        estado=dict(anterior)
        if aberto:estado['ultima_abertura']=agora()
        if visual is not None:estado.update(visual)
        return dict(d,**{k:estado})
    return atualizar(raiz,projeto,VISUAL,alterar)


def extensao_valida(valores):
    if not isinstance(valores,list) or len(valores)!=4:return False
    if not all(isinstance(v,(int,float)) and isfinite(v) for v in valores):return False
    return valores[0]<valores[2] and valores[1]<valores[3]
