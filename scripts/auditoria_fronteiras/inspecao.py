"""Dossiê relacional de inspeção; não altera eventos, agrupamentos ou fontes."""
from copy import deepcopy
from dataclasses import asdict
import json
from uuid import uuid4

from qgis.core import QgsGeometry
from .apresentacao import preparar_apresentacao, legivel, CAMPOS_PRINCIPAIS
from .investigacao import validar_analise, AnaliseLocais, OpcoesLocais,CAMPOS_LOCAIS,CAMPOS_PARES
from .modelos import Resultado, Parametros, Ocorrencia, Modo


def construir_dossie(resultado, analise, campos=None):
    validar_analise(resultado, analise)
    campos=deepcopy(campos or {})
    itens=preparar_apresentacao(resultado)
    fontes={f['origem']:deepcopy(f) for f in resultado.fontes}
    redes,poligonos,ev_rede,ev_pol={},{},[],[]
    eventos=[]
    for i in itens:
        e=i['evento']
        eventos.append(dict(uid=i['uid'],registro=deepcopy(i['registro']),tecnico=deepcopy(i['tecnico'])))
        for r in e.tubulacoes:
            chave=r['chave']
            if chave not in redes:
                extra={n:r.get('atributos_originais',{}).get(c) if c else None
                       for n,c in campos.get(r['origem'],{}).items()}
                redes[chave]=dict(uid=chave,origem=r['origem'],camada=r['camada'],
                    id_bruto=r.get('id_original'),id_exibido=legivel(r.get('id_original')),
                    atributos=deepcopy(r.get('atributos_originais',{})),campos=campos.get(r['origem'],{}),
                    extras=extra,regioes_geometricas=[])
            if e.modo==Modo.TRANSICAO:
                candidatas=redes[chave]['regioes_geometricas']
                for reg in e.regiao_antes+e.regiao_depois:
                    if reg['chave'] not in [c['chave'] for c in candidatas]:
                        candidatas.append(deepcopy(reg))
            ev_rede.append(dict(evento_uid=e.id,tubo_uid=chave))
        for papel,refs in [('FRONTEIRA',e.poligonos),('ANTES',e.regiao_antes),('DEPOIS',e.regiao_depois)]:
            for p in refs:
                poligonos.setdefault(p['chave'],deepcopy(p))
                ev_pol.append(dict(evento_uid=e.id,pol_uid=p['chave'],papel=papel))
    locais=deepcopy(analise.locais)
    evmap={i['uid']:i for i in eventos}
    for l in locais:
        l['eventos_ambiguos']=[u for u in l['eventos'] if evmap[u]['registro']['AMBIGUO']=='Sim']
        l['ambiguidades_agrupamento']=[]  # Política atual não cria indicador adicional.
        l['revisao']=dict(situacao='PENDENTE',observacoes='',responsavel='',data=None)
    return dict(versao=1,execucao_uid=uuid4().hex,campos_interesse=campos,
        contexto=dict(parametros=asdict(resultado.parametros),ambiente=deepcopy(resultado.ambiente),
            fontes=list(fontes.values()),problemas=deepcopy(resultado.problemas),
            contadores=deepcopy(resultado.contadores),cancelado=resultado.cancelado),
        analise=asdict(analise),eventos=eventos,locais=locais,tubulacoes=list(redes.values()),
        poligonos=list(poligonos.values()),evento_rede=ev_rede,evento_poligono=ev_pol,
        local_evento=[dict(local_uid=v['local_uid'],evento_uid=v['evento_uid']) for v in analise.vinculos],
        reconciliacoes=[])


def restaurar(dossie):
    contexto=deepcopy(dossie['contexto'])
    parametros=Parametros(**contexto.pop('parametros'))
    resultado=Resultado(parametros,**contexto)
    for i in dossie['eventos']:
        t=deepcopy(i['tecnico'])
        geom=QgsGeometry()
        geom.fromWkb(bytes.fromhex(t.pop('geometria_wkb_hex')))
        if geom.isNull() or geom.isEmpty():
            raise ValueError('Geometria técnica inválida')
        t.pop('apresentacao',None)
        t['modo']=Modo(t['modo'])
        resultado.ocorrencias.append(Ocorrencia(geometria=geom,**t))
    a=deepcopy(dossie['analise'])
    a['opcoes']=OpcoesLocais(**a['opcoes'])
    # JSON/SQLite não garantem ordem de chaves. Restabelece o contrato dos
    # adaptadores existentes sem alterar agrupamento nem simbologia.
    for l in a['locais']:
        l['registro']={c:l['registro'][c] for c in CAMPOS_LOCAIS}
    a['pares']=[{c:p[c] for c in CAMPOS_PARES} for p in a['pares']]
    for s in a['saidas']:
        s['registro']={c:s['registro'][c] for c in CAMPOS_PRINCIPAIS}
    analise=AnaliseLocais(**a)
    validar_analise(resultado,analise)
    return resultado,analise


def detalhes_local(dossie,uid):
    local=next(l for l in dossie['locais'] if l['uid']==uid)
    eventos=[e for e in dossie['eventos'] if e['uid'] in local['eventos']]
    tubos={r['tubo_uid'] for r in dossie['evento_rede'] if r['evento_uid'] in local['eventos']}
    polis={r['pol_uid'] for r in dossie['evento_poligono'] if r['evento_uid'] in local['eventos']}
    return dict(local=local,eventos=eventos,
        tubulacoes=[r for r in dossie['tubulacoes'] if r['uid'] in tubos],
        poligonos=[p for p in dossie['poligonos'] if p['chave'] in polis])


def contagens(dossie):
    return dict(eventos=len(dossie['eventos']),locais=len(dossie['locais']),
        eventos_ambiguos=sum(e['registro']['AMBIGUO']=='Sim' for e in dossie['eventos']),
        locais_ambiguos=sum(bool(l['eventos_ambiguos'] or l['ambiguidades_agrupamento']) for l in dossie['locais']))


def texto(dados):
    return json.dumps(dados,ensure_ascii=False,default=str,sort_keys=True)
