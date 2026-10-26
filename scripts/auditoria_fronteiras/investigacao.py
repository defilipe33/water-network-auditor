"""Locais investigativos e sínteses, posteriores ao núcleo e sem inferência hidráulica."""
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import combinations
import math

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsSpatialIndex
from .apresentacao import preparar_apresentacao, legivel
from .entradas import digest
from .modelos import verificar_cancelamento

VERSAO = 'locais-1'
CAMPOS_LOCAIS = ('LOCAL','N_EVENTOS','EVENTOS','CLASSIF','TIPOS_LIM','AREAS','REGIOES',
                 'REDE','ID_REDE','N_TUBOS','AMBIGUO','X','Y','SITUACAO')
CAMPOS_PARES = ('LEITURA','TIPO_LIM','REGIAO_A','REGIAO_B','N_EVENTOS','EVENTOS')


@dataclass(frozen=True)
class OpcoesLocais:
    habilitado: bool = False
    distancia: float = 5.0
    extensao_maxima: float = 5.0

    def validar(self):
        for v in (self.distancia,self.extensao_maxima):
            if not math.isfinite(v) or v<0:
                raise ValueError('Distâncias dos locais devem ser finitas e não negativas')


@dataclass
class AnaliseLocais:
    opcoes: OpcoesLocais
    assinatura_eventos: str
    locais: list = field(default_factory=list)
    vinculos: list = field(default_factory=list)
    pares: list = field(default_factory=list)
    saidas: list = field(default_factory=list)
    tecnicos_pares: list = field(default_factory=list)
    metadados: dict = field(default_factory=dict)
    contadores: dict = field(default_factory=dict)


def instante_execucao():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def assinatura(resultado):
    return digest([resultado.fontes,asdict(resultado.parametros),
        sorted((e.id,e.classificacao,bytes(e.geometria.asWkb()).hex(),
                e.tubulacoes,e.poligonos,e.regiao_antes,e.regiao_depois)
               for e in resultado.ocorrencias)])


def validar_analise(resultado, analise):
    if analise.assinatura_eventos!=assinatura(resultado):
        raise ValueError('Análise dos locais não corresponde a estes eventos')
    eventos={e.id for e in resultado.ocorrencias}
    if analise.opcoes.habilitado:
        ids=[v['evento_uid'] for v in analise.vinculos]
        if len(ids)!=len(eventos) or set(ids)!=eventos:
            raise ValueError('Vínculos incompletos ou duplicados entre eventos e locais')
        locais={l['uid'] for l in analise.locais}
        if len(locais)!=len(analise.locais):
            raise ValueError('IDs de locais duplicados')
        if any(v['local_uid'] not in locais for v in analise.vinculos):
            raise ValueError('Vínculo aponta para local inexistente')
        mapa={l['uid']:set(l['eventos']) for l in analise.locais}
        for local in analise.locais:
            membros=[v['evento_uid'] for v in analise.vinculos if v['local_uid']==local['uid']]
            if set(membros)!=mapa[local['uid']] or len(membros)!=local['registro']['N_EVENTOS']:
                raise ValueError('Vínculos e contagens do local divergentes')


def _chaves(refs):
    return {r['chave'] for r in refs}


def _regioes(e):
    return _chaves(e.regiao_antes+e.regiao_depois)


def _fronteira_comum(a,b):
    return bool(_chaves(a.poligonos)&_chaves(b.poligonos))


def _dist(a,b):
    return a['ponto'].distance(b['ponto'])


def _certificados(itens,tolerancia,cancelar):
    """Conserva o testemunho de continuidade e suas extremidades exatas."""
    por_tubo=defaultdict(list)
    for i in itens:
        if i['evento'].classificacao=='EXTREMIDADE':
            for chave in _chaves(i['evento'].tubulacoes):
                por_tubo[chave].append(i)
    certificados=defaultdict(set)
    for c in itens:
        verificar_cancelamento(cancelar)
        if c['evento'].classificacao!='CONTINUIDADE_POTENCIAL':
            continue
        encontrados=[]
        for extremo in c['evento'].detalhes.get('extremidades',[]):
            p=QgsGeometry.fromPointXY(QgsPointXY(extremo['x'],extremo['y']))
            for e in por_tubo[extremo['tubulacao']]:
                if (e['evento'].parte==extremo['parte'] and _fronteira_comum(c['evento'],e['evento'])
                        and e['ponto'].distance(p)<=max(1e-8,tolerancia)):
                    encontrados.append(e)
        for a,b in combinations(encontrados,2):
            if a['uid']!=b['uid'] and not (_chaves(a['evento'].tubulacoes)&_chaves(b['evento'].tubulacoes)):
                certificados[frozenset((a['uid'],b['uid']))].add(c['uid'])
    return certificados


def _compativel(a,b,certificados,membros):
    ea,eb=a['evento'],b['evento']
    ca,cb=ea.classificacao,eb.classificacao
    # Toques e trechos coincidentes não são convertidos em travessias pontuais.
    if 'COINCIDENCIA' in (ca,cb) and ca!=cb:
        return None
    if 'TANGENCIA' in (ca,cb) and ca!=cb:
        return None
    mesma_fronteira=_fronteira_comum(ea,eb)
    mesmo_tubo=bool(_chaves(ea.tubulacoes)&_chaves(eb.tubulacoes))
    fontes_a={p['origem'] for p in ea.poligonos}
    fontes_b={p['origem'] for p in eb.poligonos}
    regioes_comuns=bool(_regioes(ea)&_regioes(eb))
    if mesmo_tubo and (mesma_fronteira or regioes_comuns or fontes_a.isdisjoint(fontes_b)):
        return 'Mesma tubulação e fronteiras/regiões relacionadas ou próximas'
    testemunhos=certificados.get(frozenset((a['uid'],b['uid'])),set())
    if testemunhos & membros:
        return 'Extremidades correspondentes a continuidade potencial presente no local'
    if (mesma_fronteira and ca==cb and _dist(a,b)<=1e-8):
        return 'Eventos coincidentes da mesma classe e fronteira'
    return None


def _extensao(itens):
    diametro=max((_dist(a,b) for a,b in combinations(itens,2)),default=0.)
    if any(i['evento'].classificacao=='COINCIDENCIA' for i in itens):
        caixa=itens[0]['evento'].geometria.boundingBox()
        for i in itens[1:]:
            caixa.combineExtentWith(i['evento'].geometria.boundingBox())
        diametro=max(diametro,math.hypot(caixa.width(),caixa.height()))
    return diametro


def _sinteses(itens,analise):
    pares={}
    for i in itens:
        e=i['evento']
        if e.modo.value!='TRANSICAO' or e.classificacao not in ('TRAVESSIA','AMBIGUA'):
            continue
        if not (e.lado_antes_disponivel and e.lado_depois_disponivel):
            continue
        a,b=e.regiao_antes,e.regiao_depois
        if i['registro']['AMBIGUO']=='Sim' or len(a)>1 or len(b)>1:
            leitura='MULTIPLA' if len(a)>1 or len(b)>1 else 'INDETERMINADA'
            analise.pares.append(dict(zip(CAMPOS_PARES,[leitura,i['registro']['TIPO_LIM'],
                i['registro']['REG_ANTES'],i['registro']['REG_DEPOIS'],1,str(i['registro']['ID'])])))
            analise.tecnicos_pares.append(dict(leitura=leitura,eventos=[i['uid']],
                antes=a,depois=b))
        elif len(a)==1 and len(b)==1 and a[0]['chave']!=b[0]['chave']:
            refs=sorted([(a[0],i['registro']['REG_ANTES']),(b[0],i['registro']['REG_DEPOIS'])],
                        key=lambda t:(t[0]['origem'],t[0]['chave']))
            chave=tuple((r['origem'],r['chave']) for r,_ in refs)
            if chave not in pares:
                pares[chave]=dict(registro=dict(zip(CAMPOS_PARES,['INEQUIVOCA',i['registro']['TIPO_LIM'],
                    refs[0][1],refs[1][1],0,''])),uids=[],ids=[],regioes=[r for r,_ in refs])
            p=pares[chave]
            p['uids'].append(i['uid'])
            p['ids'].append(i['registro']['ID'])
        elif (len(a),len(b)) in ((0,1),(1,0)) and e.classificacao=='TRAVESSIA':
            analise.saidas.append(dict(uid=i['uid'],registro=i['registro'].copy()))
    for chave,p in sorted(pares.items()):
        p['registro']['N_EVENTOS']=len(set(p['uids']))
        p['registro']['EVENTOS']='; '.join(str(v) for v in p['ids'])
        analise.pares.append(p['registro'])
        analise.tecnicos_pares.append(dict(leitura='INEQUIVOCA',eventos=p['uids'],regioes=p['regioes']))


def analisar_investigacao(resultado,opcoes=None,cancelar=None,data_execucao=None):
    if resultado.cancelado:
        raise ValueError('Não agrupar resultado cancelado/parcial')
    opcoes=opcoes or OpcoesLocais(distancia=resultado.parametros.distancia_agrupamento,
                                extensao_maxima=resultado.parametros.distancia_agrupamento)
    opcoes.validar()
    itens=preparar_apresentacao(resultado,cancelar)
    analise=AnaliseLocais(opcoes,assinatura(resultado))
    analise.metadados=dict(versao=VERSAO,data_execucao_utc=data_execucao or 'Não registrada',
        data_posprocessamento_utc=instante_execucao(),crs=resultado.parametros.crs,
        parametros_nucleo=asdict(resultado.parametros),agrupamento=asdict(opcoes),
        fontes=resultado.fontes,contagens_entrada=resultado.contadores,avisos=resultado.problemas,
        ambiente=resultado.ambiente)
    _sinteses(itens,analise)
    if opcoes.habilitado:
        indice=QgsSpatialIndex()
        por_indice={}
        for n,item in enumerate(itens):
            f=QgsFeature(n)
            f.setGeometry(item['ponto'])
            indice.addFeature(f)
            por_indice[n]=item
        certificados=_certificados(itens,resultado.parametros.tolerancia_geometrica,cancelar)
        prioridade={'CONTINUIDADE_POTENCIAL':0,'EXTREMIDADE':1}
        ordem=sorted(itens,key=lambda i:(prioridade.get(i['evento'].classificacao,2),i['uid']))
        usados=set()
        for semente in ordem:
            verificar_cancelamento(cancelar)
            if semente['uid'] in usados:
                continue
            grupo=[semente]
            motivos=[]
            caixa=semente['ponto'].boundingBox()
            caixa.grow(opcoes.distancia)
            candidatos=[por_indice[n] for n in indice.intersects(caixa)
                        if por_indice[n]['uid'] not in usados and por_indice[n]['uid']!=semente['uid']]
            candidatos.sort(key=lambda i:(_dist(semente,i),i['uid']))
            for candidato in candidatos:
                verificar_cancelamento(cancelar)
                if _dist(semente,candidato)>opcoes.distancia:
                    continue
                membros={i['uid'] for i in grupo}
                criterios=[_compativel(a,candidato,certificados,membros) for a in grupo]
                if not all(criterios) or _extensao(grupo+[candidato])>opcoes.extensao_maxima:
                    continue
                motivos.extend(dict(a=a['uid'],b=candidato['uid'],criterio=c)
                               for a,c in zip(grupo,criterios))
                grupo.append(candidato)
            membros=sorted(i['uid'] for i in grupo)
            usados.update(membros)
            uid=digest([VERSAO,resultado.parametros.crs,membros])
            numero=f'L{len(analise.locais)+1:04d}'
            representante=min(grupo,key=lambda a:(max(_dist(a,b) for b in grupo),
                sum(_dist(a,b) for b in grupo),a['uid']))
            tubos={r['chave']:r for i in grupo for r in i['evento'].tubulacoes}
            tubos=[tubos[k] for k in sorted(tubos)]
            p=representante['ponto'].asPoint()
            def unir(campo):
                return '; '.join(dict.fromkeys(i['registro'][campo] for i in grupo if i['registro'][campo]))
            registro=dict(zip(CAMPOS_LOCAIS,[numero,len(grupo),
                '; '.join(str(i['registro']['ID']) for i in grupo),unir('CLASSIF'),unir('TIPO_LIM'),
                unir('AREA'),'; '.join(dict.fromkeys(i['registro'][c] for i in grupo for c in ('REG_ANTES','REG_DEPOIS')
                                                  if i['registro'][c])),
                '; '.join(r['camada'] for r in tubos),'; '.join(legivel(r['id_original']) for r in tubos),
                len(tubos),'Sim' if any(i['registro']['AMBIGUO']=='Sim' for i in grupo) else 'Não',
                p.x(),p.y(),'PENDENTE']))
            analise.locais.append(dict(uid=uid,registro=registro,eventos=membros,
                representante=representante['uid'],extensao_m=_extensao(grupo),
                criterio_representante='Evento medóide minimax; desempate pela soma das distâncias e UID',
                motivos=motivos,tubulacoes=tubos,
                poligonos={r['chave']:r for i in grupo for r in i['evento'].poligonos}))
            for i in grupo:
                analise.vinculos.append(dict(local_uid=uid,evento_uid=i['uid'],LOCAL=numero,
                    ID_EVENTO=i['registro']['ID'],MOTIVO='Isolado' if len(grupo)==1 else
                    'Compatibilidade completa entre membros; consultar critérios técnicos'))
    analise.contadores=dict(eventos=len(itens),locais=len(analise.locais),
        tubulacoes=len({r['chave'] for i in itens for r in i['evento'].tubulacoes}),
        pares_inequivocos=sum(p['LEITURA']=='INEQUIVOCA' for p in analise.pares),
        ocorrencias_par_inequivoco=sum(p['N_EVENTOS'] for p in analise.pares if p['LEITURA']=='INEQUIVOCA'),
        interpretacoes_multiplas=sum(p['LEITURA']!='INEQUIVOCA' for p in analise.pares),
        saidas_externas=len(analise.saidas),
        ambiguidades=sum(i['registro']['AMBIGUO']=='Sim' for i in itens))
    validar_analise(resultado,analise)
    return analise
