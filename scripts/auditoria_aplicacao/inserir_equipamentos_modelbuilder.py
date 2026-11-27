"""Divisão exportável para equipamentos explicitamente associados ao interior de um Pipe."""

from collections import defaultdict

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento
from .investigacao_gis import geometria
from .tipos_modelbuilder import DIRECIONAIS, PROPRIEDADES, atributos
from .validacao_modelbuilder_gis import EPS, linha


def inserir(previa,pipes,nos,perfil,tolerancia,substituidos,cancelar):
    """Recorta somente o segmento receptor declarado e conserva as portas originais."""
    por_parte=defaultdict(list)
    for p in pipes:
        if not p.get('segmento_anterior'):por_parte[p['parte']].append(p)
    por_uid={n['uid']:n for n in nos}
    por_pipe=defaultdict(list)
    pendencias={}
    for e in previa['equipamentos']:
        verificar_cancelamento(cancelar)
        t,u=e['categoria'],e['uid']
        if t not in perfil['tipos'] or t not in (*DIRECIONAIS,'HYDRANT','AIR_VALVE'):
            continue
        ds=[d for d in e.get('declaracoes',()) if d['posicao']=='INTERMEDIARIA']
        if not ds:continue
        if any(d.get('portas') for d in e.get('declaracoes',())):
            pendencias[u]='Há declarações simultâneas de ponta e interior. Confira a posição do equipamento.'
            continue
        valores=atributos(t,e.get('atributos_originais') or {},perfil)
        if any(valores.get(k) is None for k in PROPRIEDADES[t]):
            continue
        if t in DIRECIONAIS and {valores['mb_jus'],valores['mb_mont']}!={'PORTA_A','PORTA_B'}:
            pendencias[u]='Para criar a divisão, indique os lados PORTA_A e PORTA_B nos campos de orientação.'
            continue
        partes={p for d in ds for p in d.get('tubos_uid',())}
        g=geometria(e.get('wkb'))
        if len(partes)!=1 or not g or g.type()!=0 or g.isMultipart():
            pendencias[u]='A inserção requer um ponto e exatamente uma parte de Pipe declarada.'
            continue
        alvos=[]
        existentes=defaultdict(int)
        for p in por_parte[next(iter(partes))]:
            geom=linha(p)
            if not 0<=geom.distance(g)<=tolerancia:continue
            medida=geom.lineLocatePoint(g)
            comp=geom.length()
            if min(medida,comp-medida)>EPS:
                alvos.append((p,geom,medida/comp))
            elif medida>=0:
                no,fr=(p['no_a'],p['inicio']) if medida<=EPS else (p['no_b'],p['fim'])
                if 0<fr<1:existentes[no]+=1
        if len(alvos)==1 and not existentes:
            p,geom,f=alvos[0]
            por_pipe[p['uid']].append((e,geom,f))
        elif len(existentes)==1 and max(existentes.values())==2 and not alvos:
            pendencias[u]=('NO_EXISTENTE',next(iter(existentes)))
        else:
            pendencias[u]='A posição declarada está ausente ou coincide com mais de um segmento.'
    saida=[]
    complementos={}
    for p in pipes:
        verificar_cancelamento(cancelar)
        propostas=por_pipe.get(p['uid'],())
        if len(propostas)!=1:
            for e,_,_ in propostas:pendencias[e['uid']]='Mais de um equipamento disputa o mesmo segmento. Confira o recorte.'
            saida.append(p)
            continue
        e,g,f=propostas[0]
        t=e['categoria']
        if t in DIRECIONAIS:
            a=atributos(t,e.get('atributos_originais') or {},perfil)
            diagnostico=(a['mb_estado']=='ATIVO' if t=='PUMP' else a['mb_ajuste']<0 or
                         t in ('PRV','PSV','FCV') and a['mb_ajuste']==0)
            if diagnostico:
                pendencias[e['uid']]='O estado ou ajuste hidráulico é incompatível com o equipamento.'
                saida.append(p)
                continue
        corte=p['inicio']+(p['fim']-p['inicio'])*f
        uid=digest(['no-exportacao-equipamento',p['parte'],corte])
        if uid in por_uid:
            raise ValueError('A inserção de equipamento produziria nó duplicado.')
        ponto=g.interpolate(g.length()*f).asPoint()
        base=por_uid[p['no_a']]
        n={**base,'uid':uid,'WNA_UID':uid,'xy':[ponto.x(),ponto.y()],'portas':[[p['parte'],corte]],
           'natureza':'DIVISAO_EXPORTACAO_EQUIPAMENTO','original':None,'label':None,'gis_id':None,
           'WNA_ORIG_UID':None,'WNA_ID_GIS':None,'WNA_PROCEDENCIA':'DERIVADO','WNA_SITUACAO':'DIVISAO_EXPORTACAO_EQUIPAMENTO'}
        trechos=[]
        for ini,fim,f0,f1,no_a,no_b in ((0,f,p['inicio'],corte,p['no_a'],uid),(f,1,corte,p['fim'],uid,p['no_b'])):
            geom=type(g)(g.constGet().curveSubstring(ini*g.length(),fim*g.length()))
            u=digest(['segmento_gis',p['parte'],f0,f1])
            trechos.append(dict(p,uid=u,WNA_UID=u,no_a=no_a,no_b=no_b,wkb=bytes(geom.asWkb()),
                comprimento_m=geom.length(),inicio=f0,fim=f1,segmento_anterior=p['uid'],
                natureza='DIVISAO_EXPORTACAO_EQUIPAMENTO',WNA_PROCEDENCIA='DERIVADO'))
        if min(r['comprimento_m'] for r in trechos)<=EPS or abs(sum(r['comprimento_m'] for r in trechos)-g.length())>EPS:
            raise ValueError('A inserção não preserva o comprimento ou produz segmento degenerado.')
        nos.append(n)
        por_uid[uid]=n
        substituidos[p['uid']]=trechos
        complementos[e['uid']]=(uid,trechos[0]['uid'],trechos[1]['uid'])
        saida.extend(trechos)
    for u,estado in list(pendencias.items()):
        if isinstance(estado,tuple):
            complementos[u]=(estado[1],None,None)
            del pendencias[u]
    return saida,complementos,pendencias
