"""Declarações GIS versionadas; não constroem arestas nem escrevem nas fontes."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from qgis.core import QgsExpression, QgsFeatureRequest, QgsVariantUtils, Qgis
from .modelo_gis import chave_feicao

POSICOES = ('DESCONHECIDA', 'INICIO', 'FIM', 'INTERMEDIARIA')


def referencia(fonte, feicao):
    campo = fonte['campos_mapeados'].get('id')
    valor = feicao[campo] if campo else None
    chave = chave_feicao(fonte, valor)
    if chave is None: raise ValueError('Mapeie um ID da feição não vazio antes de declarar conexões.')
    if type(valor) not in (str, int, float, bool):
        raise ValueError('Use um identificador textual ou numérico persistente.')
    return dict(fonte_uid=fonte['uid'], origem=fonte['origem_estavel'], categoria=fonte['categoria'],
                campo=campo, tipo=chave[2], valor=valor, assinatura=fonte['assinatura'])


def verificar_referencia(ref, fonte, snapshot, cancelar=lambda: False):
    if (ref['fonte_uid'], ref['origem'], ref['campo']) != (fonte['uid'], fonte['origem_estavel'], fonte['campos_mapeados'].get('id')):
        raise ValueError('Identidade alterada. Revise a associação; não será transferida automaticamente.')
    if ref['campo'] not in snapshot.fields().names(): raise ValueError('ID ausente na fonte atual.')
    eq = QgsExpression.quotedColumnRef(ref['campo']) + ' = ' + QgsExpression.quotedValue(ref['valor'])
    expr = '(' + eq + ')' + (' AND (' + fonte['filtro'] + ')' if fonte['filtro'] else '')
    req = QgsFeatureRequest().setFilterExpression(expr).setLimit(2).setFlags(Qgis.FeatureRequestFlag.NoGeometry)
    req.setSubsetOfAttributes([ref['campo']], snapshot.fields())
    n = 0
    for f in snapshot.getFeatures(req):
        if cancelar(): raise InterruptedError('Declaração cancelada; dados anteriores preservados.')
        if not QgsVariantUtils.isNull(f[ref['campo']]) and type(f[ref['campo']]).__name__ == ref['tipo']:
            n += 1
    if n != 1: raise ValueError('ID ausente ou repetido no filtro da fonte. Confira os identificadores.')


def declarar(fonte, equipamento, tubos, posicao='DESCONHECIDA', anterior=None):
    if fonte['categoria'] not in ('RESERVOIR', 'TANK') or equipamento['fonte_uid'] != fonte['uid']:
        raise ValueError('Selecione um Reservoir ou Tank da fonte cadastrada.')
    if not tubos or any(t['categoria'] != 'PIPE' for t in tubos) or posicao not in POSICOES:
        raise ValueError('Selecione tubulações e uma posição válida, ou desconhecida.')
    nova = deepcopy(fonte)
    hist = nova.setdefault('associacoes_rede', [])
    if anterior and not any(r['uuid'] == anterior for r in hist): raise ValueError('Associação anterior não encontrada.')
    hist.append(dict(uuid=uuid4().hex, anterior=anterior, data_utc=datetime.now(timezone.utc).isoformat(),
                     equipamento=deepcopy(equipamento), tubulacoes=deepcopy(tubos), posicao=posicao,
                     natureza='DECLARADA_MANUALMENTE', situacao='ATIVA',
                     significado='Relação investigativa GIS declarada; não comprova conexão hidráulica.'))
    return nova


def vigentes(fonte):
    hist = fonte.get('associacoes_rede', [])
    substituidas = {r.get('anterior') for r in hist}
    return [r for r in hist if r['uuid'] not in substituidas and r['situacao'] != 'REMOVIDA']


def remover(fonte, uid):
    nova = deepcopy(fonte)
    alvo = next((r for r in vigentes(fonte) if r['uuid'] == uid), None)
    if alvo is None: raise ValueError('Associação vigente não encontrada.')
    evento = deepcopy(alvo)
    evento.update(uuid=uuid4().hex, anterior=uid, data_utc=datetime.now(timezone.utc).isoformat(), situacao='REMOVIDA')
    nova['associacoes_rede'].append(evento)
    return nova


def pendencias(associacao, fontes):
    por_uid = {f['uid']: f for f in fontes}
    avisos = []
    for ref in [associacao['equipamento'], *associacao['tubulacoes']]:
        f = por_uid.get(ref['fonte_uid'])
        if not f or (f['origem_estavel'], f['campos_mapeados'].get('id'), f['assinatura']) != (ref['origem'], ref['campo'], ref['assinatura']):
            avisos.append('Associação pendente de revisão: fonte ou identidade alterada.')
    return sorted(set(avisos))
