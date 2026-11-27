"""Contrato GIS para preparar tipos WaterGEMS, com mapeamento explícito de referências."""

from math import isfinite
import json


LINEARES={'m':1.,'cm':.01,'mm':.001,'km':1000.,'ft':.3048}
UNIDADES={
    'm':LINEARES, 'C':{'C':1.}, 'K':{'K':1.}, 'mca':{'mca':1.,'kPa':1/9.80665,'bar':100/9.80665},
    'L/s':{'L/s':1.,'m³/h':1/3.6,'m³/s':1000.}, 'referência':{'referência':1.}, 'estado':{'estado':1.},
    'composição':{'composição':1.},
}
COTA=('Elevação (m)','m')
MONTANTE=('Pipe a montante · UID ou ID GIS único','referência')
JUSANTE=('Pipe a jusante · UID ou ID GIS único','referência')
ESTADO=('Estado inicial declarado','estado')
DIRECIONAIS={
    'PRV':('Pressão de regulagem (mca)','mca'),
    'PSV':('Pressão de sustentação (mca)','mca'),
    'PBV':('Perda de carga fixa (m)','m'),
    'TCV':('Coeficiente de perda de carga K','K'),
    'FCV':('Vazão de regulagem (L/s)','L/s'),
    'PUMP':('Label da definição de bomba no modelo de destino','referência'),
}
CAMADAS=dict(JUNCTION='junctions',RESERVOIR='reservoirs',TANK='tanks',PRV='prvs',PSV='psvs',
             PBV='pbvs',TCV='tcvs',FCV='fcvs',PUMP='pumps',HYDRANT='hydrants',AIR_VALVE='air_valves',
             REGISTRO='isolation_valves')
TIPOS_NOS=tuple(t for t in CAMADAS if t!='REGISTRO')
PROPRIEDADES={
    'PIPE':{'mb_comp_h':('Comprimento hidráulico (m)','m'), 'mb_hw_c':('Coeficiente Hazen-Williams C','C')},
    'JUNCTION':{'mb_cota':COTA},
    'RESERVOIR':{'mb_carga':('Carga hidráulica do reservatório (m)','m')},
    'TANK':{'mb_cota':('Elevação da base (m)','m'), 'mb_nmin':('Nível mínimo relativo (m)','m'),
            'mb_nini':('Nível inicial relativo (m)','m'), 'mb_nmax':('Nível máximo relativo (m)','m'),
            'mb_diam':('Diâmetro cilíndrico (m)','m')},
    'HYDRANT':{'mb_cota':COTA},
    'AIR_VALVE':{'mb_cota':COTA},
    **{t:{'mb_cota':COTA,'mb_mont':MONTANTE,'mb_jus':JUSANTE,'mb_estado':ESTADO,
          ('mb_def' if t=='PUMP' else 'mb_ajuste'):ajuste} for t,ajuste in DIRECIONAIS.items()},
    'REGISTRO':{'mb_pipe':('Pipe associado · UID ou ID GIS único','referência'),'mb_estado':ESTADO},
    'BOOSTER':{'composicao':('Composição declarada em JSON por WNA_UID','composição')},
}
INVENTARIO={
    'BOOSTER':'Informe a composição e cadastre separadamente bombas, Pipes e nós de sucção e recalque.',
    'DISPOSITIVO':'A categoria precisa de um tipo hidráulico explícito.',
    'ENTRADA':'Ponto de abastecimento de referência, sem tipo nativo declarado.',
}
CAMPOS_EQUIPAMENTO=dict(mb_mont='MB_MONT',mb_jus='MB_JUS',mb_ajuste='MB_AJUSTE',mb_def='MB_DEF',
    mb_pipe='MB_PIPE',mb_estado='MB_ESTADO',no_topologico='NO_TOPO',equipamento_uid='EQ_UID',
    posicao_pipe='POS_PIPE')


def numero(valor, fator=1.):
    if valor is None or isinstance(valor,bool):
        return None
    try:
        n=float(valor)*fator
    except (TypeError,ValueError,OverflowError):
        return None
    return n if isfinite(n) else None


def atributos(tipo, origem, perfil):
    saida={}
    for k,regra in perfil['campos'].get(tipo,{}).items():
        v=origem.get(regra['campo'])
        un=regra['unidade']
        if un=='referência':
            saida[k]=str(v).strip() or None if isinstance(v,(str,int,float)) and not isinstance(v,bool) else None
        elif un=='estado':
            rotulos={'ABERTO':'ABERTO','FECHADO':'FECHADO','ATIVO':'ATIVO','OPEN':'ABERTO',
                     'CLOSED':'FECHADO','ACTIVE':'ATIVO','ON':'ABERTO','OFF':'FECHADO'}
            saida[k]=rotulos.get(v.strip().upper()) if isinstance(v,str) else None
        elif un=='composição':
            try:d=json.loads(v) if isinstance(v,str) else v
            except ValueError:d=None
            saida[k]=d if isinstance(d,dict) else None
        else:
            saida[k]=numero(v,UNIDADES[PROPRIEDADES[tipo][k][1]][un])
    return saida


def composicoes_booster(equipamentos,perfil,registros,vinculos):
    """Verifica a composição contra elementos individuais que já constam do pacote."""
    por_uid={r['uid']:r['tipo'] for r in registros}
    relacoes={r['uid']:r for r in vinculos if r['tipo']=='PUMP'}
    for e in equipamentos:
        if e['categoria']!='BOOSTER':continue
        d=atributos('BOOSTER',e.get('atributos_originais') or {},perfil).get('composicao') or {}
        campos={'bombas':{'PUMP'},'pipes':{'PIPE'},'nos':set(TIPOS_NOS),
                'dispositivos':set(CAMADAS)-{'JUNCTION','RESERVOIR','TANK','PUMP'}}
        valido=all(isinstance(d.get(k,[]),list) and all(isinstance(u,str) and por_uid.get(u) in ts
                  for u in d.get(k,[])) for k,ts in campos.items())
        bombas=d.get('bombas') if valido else None
        pipes=d.get('pipes') if valido else None
        s,r=d.get('succao'),d.get('recalque')
        if valido and bombas and pipes and isinstance(s,str) and isinstance(r,str) and s!=r and s in pipes and r in pipes:
            meios=[relacoes.get(u,{}) for u in bombas]
            valido=(any(m.get('montante')==s for m in meios) and any(m.get('jusante')==r for m in meios)
                    and all(m.get('montante') in pipes and m.get('jusante') in pipes for m in meios))
        else:
            valido=False
        yield dict(uid=e['uid'],id_gis=e.get('id'),label=e.get('label'),composicao=d or None,
                   situacao='COMPONENTES_REFERENCIADOS' if valido else 'COMPOSICAO_PENDENTE')
