"""Projeção legível dos resultados. Não altera classificação nem geometria."""
from dataclasses import fields
import math
from .modelos import Modo, verificar_cancelamento

CAMPOS_PRINCIPAIS = ('ID', 'CLASSIF', 'TIPO_LIM', 'AREA', 'REG_ANTES',
                     'REG_DEPOIS', 'REDE', 'ID_REDE', 'AMBIGUO', 'X', 'Y')


def vazio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def legivel(valor, ausente='Sem ID'):
    if vazio(valor):
        return ausente
    if isinstance(valor, float) and math.isfinite(valor):
        # Até dois ULPs, limitados a 1e-8: ruído binário, não arredondamento
        # decimal genérico. Acima de 2**53 não é possível garantir inteiro exato.
        inteiro = round(valor)
        if abs(valor) <= 2**53 and abs(valor-inteiro) <= min(1e-8, 2*math.ulp(valor)):
            return str(inteiro)
    return str(valor)


def ponto_representativo(evento):
    geom = evento.geometria
    if evento.classificacao == 'COINCIDENCIA':
        return geom.interpolate(geom.length()/2), 'MEIO_DO_TRECHO'
    return geom, ('MEIO_DAS_EXTREMIDADES' if evento.classificacao == 'CONTINUIDADE_POTENCIAL'
                  else 'PONTO_DO_EVENTO')


def preparar_apresentacao(resultado, cancelar=None):
    fontes = {f['origem']: f for f in resultado.fontes}
    saida, vistos = [], set()
    for numero, evento in enumerate(resultado.ocorrencias, 1):
        verificar_cancelamento(cancelar)
        if evento.id in vistos:
            raise ValueError('ID técnico de ocorrência duplicado; apresentação interrompida')
        vistos.add(evento.id)
        substituicoes = []
        sem_identificacao = []
        def area(ref, contexto):
            fonte = fontes.get(ref['origem'], {})
            campo = fonte.get('campo_nome')
            identificador = fonte.get('campo_id')
            valor = ref.get('nome') if campo else ref.get('id_original')
            if vazio(valor):
                if campo and campo != identificador:
                    substituicoes.append(dict(contexto=contexto, poligono=ref['chave'],
                        campo_exibicao=campo, campo_alternativo=identificador,
                        motivo='Exibição vazia; utilizado identificador',
                        valor_alternativo=ref.get('id_original')))
                valor = ref.get('id_original')
            if vazio(valor):
                sem_identificacao.append(dict(contexto=contexto, poligono=ref['chave']))
            return legivel(valor, 'Indeterminado')
        def regiao(refs, disponivel, contexto):
            if evento.modo != Modo.TRANSICAO:
                return ''
            if not disponivel:
                return 'Extremidade' if evento.classificacao == 'EXTREMIDADE' else 'Indeterminado'
            if refs:
                return '; '.join(area(r, contexto) for r in refs)
            # O núcleo não expõe incerteza por lado: não afirmar exterior em
            # ocorrência ambígua sem candidatos. Preservar a incerteza.
            if evento.ambigua or evento.classificacao == 'AMBIGUA':
                return 'Indeterminado'
            return 'Fora das regiões cadastradas'
        ponto, representacao = ponto_representativo(evento)
        if ponto.isNull() or ponto.isEmpty():
            raise ValueError(f'Ocorrência sem ponto representativo: {evento.id}')
        p = ponto.asPoint()
        areas = [dict(chave=r['chave'], origem=r['origem'], camada=r['camada'],
                      id_original=r.get('id_original'), rotulo=area(r, 'AREA'))
                 for r in evento.poligonos]
        linha = dict(zip(CAMPOS_PRINCIPAIS, [numero, evento.classificacao,
            '; '.join(dict.fromkeys(r['camada'] for r in evento.poligonos)),
            '; '.join(r['rotulo'] for r in areas),
            regiao(evento.regiao_antes, evento.lado_antes_disponivel, 'REG_ANTES'),
            regiao(evento.regiao_depois, evento.lado_depois_disponivel, 'REG_DEPOIS'),
            '; '.join(r['camada'] for r in evento.tubulacoes),
            '; '.join(legivel(r.get('id_original')) for r in evento.tubulacoes),
            '', p.x(), p.y()]))
        ambiguo = (evento.ambigua or evento.classificacao == 'AMBIGUA'
                   or bool(sem_identificacao) or len(evento.regiao_antes)>1
                   or len(evento.regiao_depois)>1)
        linha['AMBIGUO'] = 'Sim' if ambiguo else 'Não'
        tecnico = {f.name: getattr(evento, f.name) for f in fields(evento) if f.name != 'geometria'}
        tecnico['geometria_wkb_hex'] = bytes(evento.geometria.asWkb()).hex()
        tecnico['apresentacao'] = dict(ID=numero, geom_repr=representacao,
            substituicoes=substituicoes, sem_identificacao=sem_identificacao,
            ambiguidade_apresentacao=ambiguo, registro=linha.copy())
        saida.append(dict(uid=evento.id, modo=evento.modo.value, registro=linha,
                          tecnico=tecnico, ponto=ponto, evento=evento, areas=areas))
    return saida
