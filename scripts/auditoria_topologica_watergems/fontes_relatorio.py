"""Seleção conservadora de basemaps: camada carregada não equivale a licença."""
import re
from urllib.parse import unquote
from pathlib import Path


class BasemapPendente(ValueError):
    def __init__(self,motivo,fonte='',uma_ocorrencia=False):
        super().__init__(motivo);self.fonte=fonte;self.uma_ocorrencia=uma_ocorrencia


class FalhaBasemap(RuntimeError):pass


def valida(c):
    if c is None:return False
    try:return c.isValid()
    except RuntimeError:return False


def uri_remota(prov,fonte):
    """Inspeção local anterior à construção de um provedor que possa consultar rede."""
    prov=prov.lower();uri=unquote(unquote(fonte)).lower()
    if prov not in ('memory','ogr','gdal','mdal','mesh_memory','spatialite','delimitedtext'):return True
    padrao=r'https?://|/vsi(curl|s3|gs|az|webhdfs)|(?:^|\s)pg:|(?:^|[ &])(?:host|service)='
    if re.search(padrao,uri):return True
    if prov=='gdal' and uri.split('|')[0].endswith('.vrt'):
        try:
            p=Path(fonte.split('|')[0])
            if p.stat().st_size>8*1024**2:return True
            return bool(re.search(padrao,p.read_text(encoding='utf8',errors='replace').lower()))
        except OSError:return True
    return False


def remota(c):
    """Sem requisições: examina provedor e URI, inclusive fontes vetoriais/VRT."""
    return uri_remota(c.providerType(),c.source())


def permissoes(c,config):
    m=c.metadata();licencas=[s.strip().lower().rstrip('/') for s in m.licenses()];direitos='; '.join(s for s in m.rights() if s.strip())
    def flag(v):
        if isinstance(v,str):
            if v.strip().lower() in ('false','0','no','não','nao'):return False
            if v.strip().lower() in ('true','1','yes','sim'):return True
        return v
    propriedade=flag(c.customProperty('wna/relatorio/exportacao_permitida',None))
    negada=propriedade in (False,'false','0',0) and propriedade is not None
    cc0=any(s in ('cc0','cc0-1.0','https://creativecommons.org/publicdomain/zero/1.0','public domain') for s in licencas)
    aberta=any(s in ('cc-by-4.0','cc-by-sa-4.0','odbl-1.0','https://creativecommons.org/licenses/by/4.0','https://creativecommons.org/licenses/by-sa/4.0') for s in licencas)
    credito=str(c.customProperty('wna/relatorio/atribuicao','') or direitos or config.get('atribuicao') or (c.name()+' · CC0' if cc0 else ''))
    permitida=not negada and (propriedade in (True,'true','1',1) or cc0 or aberta and bool(direitos) or bool(config.get('licenca_exportacao')))
    lote=flag(c.customProperty('wna/relatorio/lote_permitido',None))
    lote_negado=lote in (False,'false','0',0) and lote is not None
    return dict(exportar=bool(permitida and credito),credito=credito,lote=not lote_negado and (lote in (True,'true','1',1) or config.get('lote_online_autorizado',False)),negada=negada)


def candidatas_locais(camadas):
    from qgis.core import QgsRasterLayer
    return [c for c in camadas if valida(c) and not remota(c) and (isinstance(c,QgsRasterLayer) or c.customProperty('wna/mapa_base',False) in (True,'true','1',1)) and permissoes(c,{})['exportar']]


def resolver(camadas,config,quantidade):
    modo=config.get('basemap_modo','SELECIONAR' if camadas else 'NENHUM');config=dict(config)
    if not config.get('imagens',True) or modo=='NENHUM':return [],config
    if modo=='AUTOMATICO':
        fontes=candidatas_locais(camadas)
        if not fontes:
            config['avisos_basemap']=['Mapa-base não utilizado: nenhuma fonte local com exportação permitida foi identificada. Elementos da investigação preservados.'];return [],config
        camadas=fontes[:1]
    elif modo!='SELECIONAR':raise ValueError('Modo de mapa-base inválido')
    for c in camadas:
        if not valida(c):raise BasemapPendente('A fonte selecionada está indisponível. Gere sem mapa-base ou selecione outra fonte.')
        p=permissoes(c,config)
        if not p['exportar']:raise BasemapPendente('A exportação desta fonte não está autorizada ou seus créditos estão incompletos. As camadas da investigação podem ser usadas sem mapa-base.',c.name())
        if remota(c):
            if not config.get('mapas_online'):raise BasemapPendente('Este serviço precisa receber a área do mapa. Autorize essa consulta somente se seu uso for permitido, ou gere sem mapa-base.',c.name())
            if quantidade>1 and not p['lote']:raise BasemapPendente('Esta fonte não está autorizada para vários mapas. Você pode gerar sem mapa-base, trocar a fonte ou escolher uma única ocorrência.',c.name(),True)
        config['licenca_exportacao']=True;config['atribuicao']=p['credito']
    return list(camadas),config
