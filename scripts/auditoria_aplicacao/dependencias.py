"""Contratos de navegação: não executam auditoria nem presumem validação."""
from dataclasses import dataclass,asdict
from enum import Enum

class Estado(str,Enum):
    CONCLUIDO='CONCLUÍDO'
    PENDENTE='PENDENTE'
    EM_ANDAMENTO='EM ANDAMENTO'
    VALIDACAO='REQUER VALIDAÇÃO'
    INCOMPATIVEL='INCOMPATÍVEL'
    INDISPONIVEL='INDISPONÍVEL'
    OPCIONAL='OPCIONAL'

@dataclass
class Requisito:
    chave:str
    estado:Estado
    motivo:str
    acao:str
    def dados(self):return asdict(self)

FERRAMENTAS={
 'gis':('Nova auditoria GIS',(), 'Seleciona entradas e parâmetros; produz eventos e locais sem alterar o cadastro.'),
 'continuar_gis':('Continuar auditoria GIS',(),'Recupera eventos, locais e revisões sem recalcular.'),
 'preparar_wg':('Preparar modelo WaterGEMS',(), 'Seleciona modelo/cenário ou recupera base; não exige auditoria GIS.'),
 'topologia':('Analisar conectividade',('wg',),'Consulta elementos, componentes e diagnósticos; CRS não é requisito para consultar o grafo.'),
 'espacial':('Validar referência espacial',('wg','gis'),'Compara referências GIS e WaterGEMS; preserva versões anteriores.'),
 'correspondencia':('Conferir correspondências',('wg','gis'),'Verifica campos explícitos, identidades e geometrias; não pressupõe equivalência por nome.'),
 'integrar':('Criar investigação integrada',('gis','wg','espacial','compatibilidade','correspondencia'),'Confere fontes e publica outra investigação somente após validação.'),
 'continuar':('Continuar investigação',(),'Retoma ocorrências, filtros, resultados e histórico da versão escolhida.'),
 'corredores':('Investigar corredores',('wg',),'Calcula no grafo completo a partir de terminais escolhidos; não representa vazão.'),
 'ilhas':('Encontrar ilhas sem origem',('wg',),'Busca multiorigem no grafo completo; ausência de caminho não comprova desabastecimento.'),
 'selection_sets':('Explorar Selection Sets',('integrada',),'A implementação atual persiste conjuntos na investigação e usa sua versão topológica.'),
 'relatorio':('Gerar relatório',('integrada',),'Usa resultados persistidos e fontes cartográficas permitidas; offline por padrão.'),
 'historico':('Consultar histórico / versões',(), 'Catálogo e históricos existentes; não recalcula nem transfere decisões.'),
 'cenarios':('Explorar cenários e setores',('wg',),'Cada cenário possui Active Topology própria, resolvida por herança. Base não é união dos filhos.'),
}

def avaliar(fatos,ocupado=False):
    rs={}
    for k,acao,motivo in [('gis','gis','Crie uma auditoria GIS ou recupere uma execução concluída.'),('wg','preparar_wg','Prepare ou recupere uma base topológica íntegra.'),('integrada','continuar','Abra uma investigação integrada persistida.')]:
        valor=fatos.get(k,{});estado=Estado.CONCLUIDO if valor.get('valido') else Estado.INCOMPATIVEL if valor.get('erro') else Estado.PENDENTE
        rs[k]=Requisito(k,estado,valor.get('erro') or motivo,acao)
    rs['espacial']=Requisito('espacial',Estado.CONCLUIDO if fatos.get('espacial') else Estado.VALIDACAO if rs['wg'].estado==Estado.CONCLUIDO else Estado.PENDENTE,'Integração espacial requer CRS/unidades validados para a versão selecionada. Consulta topológica continua disponível.','espacial')
    rs['compatibilidade']=Requisito('compatibilidade',Estado.CONCLUIDO if fatos.get('compativel') is True else Estado.INCOMPATIVEL if fatos.get('compativel') is False else Estado.PENDENTE,'Confira o projeto, identidades e fontes das duas bases. Nomes não estabelecem correspondência cadastral.','correspondencia')
    rs['correspondencia']=Requisito('correspondencia',Estado.CONCLUIDO if fatos.get('correspondencia') else Estado.PENDENTE,'Selecione campos GIS e confira a prévia; ambiguidades não são equivalência comprovada.','correspondencia')
    if ocupado:
        for r in rs.values():
            if r.estado!=Estado.CONCLUIDO:r.estado=Estado.EM_ANDAMENTO
    return rs

def disponibilidade(chave,requisitos,ocupado=False):
    if chave not in FERRAMENTAS:raise ValueError('Ferramenta desconhecida')
    faltam=[requisitos[k] for k in FERRAMENTAS[chave][1] if requisitos[k].estado!=Estado.CONCLUIDO]
    return not ocupado and not faltam,faltam

def recomendar(rs):
    for requisito,acao in [('integrada','continuar'),('gis','preparar_wg'),('wg','topologia')]:
        if rs[requisito].estado==Estado.CONCLUIDO:
            if requisito=='gis' and rs['wg'].estado==Estado.CONCLUIDO:
                if rs['espacial'].estado!=Estado.CONCLUIDO:return 'espacial'
                if rs['correspondencia'].estado!=Estado.CONCLUIDO or rs['compatibilidade'].estado!=Estado.CONCLUIDO:return 'correspondencia'
                return 'integrar'
            return acao
    return 'gis'
