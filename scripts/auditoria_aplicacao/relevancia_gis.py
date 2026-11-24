"""Interpretação reproduzível dos fatos persistidos; não calcula conectividade."""
from collections import Counter
from hashlib import sha256
import json

VERSAO = 'gis-relevancia-1'
ROTULOS = {'INFORMATIVA': 'Informativa', 'REVISAR': 'Revisar',
           'INCONSISTENCIA_IDENTIFICADA': 'Inconsistência identificada',
           'INDETERMINADA': 'Indeterminada'}
ATENCAO = frozenset(('REVISAR', 'INCONSISTENCIA_IDENTIFICADA'))
# Cor e forma também identificam o significado; não dependemos só da cor.
SIMBOLOS = {'INFORMATIVA': ('#648ca6', 'circle'), 'REVISAR': ('#d9901c', 'triangle'),
            'INCONSISTENCIA_IDENTIFICADA': ('#d84646', 'diamond'),
            'INDETERMINADA': ('#a17bc6', 'square')}


def classificar(evento, tubos_vinculados, tubos_disponiveis):
    t = evento.get('tecnico', {}); r = evento.get('registro', {})
    classe = t.get('classificacao'); vinculados = sorted(set(tubos_vinculados))
    ausentes = sorted(u for u in vinculados if u not in tubos_disponiveis)
    ambiguo = t.get('ambigua') is True or str(r.get('AMBIGUO', '')).strip().upper() in ('1', 'SIM', 'TRUE', 'S')
    if ausentes:
        categoria, criterio, motivo = ('INCONSISTENCIA_IDENTIFICADA', 'REFERENCIA_AUSENTE',
            'O resultado contém vínculo explícito com tubulação ausente do seu inventário. '
            'Inconsistência de referência do resultado; não comprova defeito hidráulico.')
    elif not classe or not vinculados:
        categoria, criterio, motivo = ('INDETERMINADA', 'DADOS_INSUFICIENTES',
            'Faltam classificação ou vínculos de tubulações para interpretar este registro.')
    elif classe == 'CONTINUIDADE_POTENCIAL':
        categoria, criterio, motivo = ('REVISAR', 'CONTINUIDADE_CANDIDATA',
            'Há extremidades próximas com continuidade candidata. A conexão não foi confirmada.')
    elif classe == 'AMBIGUA' or ambiguo:
        categoria, criterio, motivo = ('REVISAR', 'AMBIGUIDADE_REGISTRADA',
            'A auditoria registrou ambiguidade geométrica ou de identificação. Consulte os detalhes; '
            'isso não comprova uma falha de conexão.')
    elif classe in ('TRAVESSIA', 'TANGENCIA', 'EXTREMIDADE', 'COINCIDENCIA'):
        categoria, criterio, motivo = ('INFORMATIVA', 'CONTATO_COM_FRONTEIRA',
            'Contato geométrico com limite poligonal, sem outro indício registrado. '
            'Não demonstra conexão, desconexão ou necessidade de intervenção.')
    else:
        categoria, criterio, motivo = ('INDETERMINADA', 'CLASSE_SEM_REGRA',
            'Esta classificação não possui regra de relevância validada nesta versão.')
    entrada = dict(classe=classe, ambiguo=ambiguo, tubos=vinculados, ausentes=ausentes)
    assinatura = sha256(json.dumps(entrada, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(evento_uid=evento['uid'], categoria=categoria, motivo=motivo, criterio=criterio,
                regra=VERSAO, assinatura_entrada=assinatura)


def calcular(dossie):
    from collections import defaultdict
    vinculos = defaultdict(list)
    for r in dossie['evento_rede']: vinculos[r['evento_uid']].append(r['tubo_uid'])
    tubos = {t['uid'] for t in dossie['tubulacoes']}
    return {e['uid']: classificar(e, vinculos[e['uid']], tubos) for e in dossie['eventos']}


def resumo(registros):
    contagens = Counter(r['categoria'] for r in registros.values())
    return {k: contagens[k] for k in ROTULOS}
