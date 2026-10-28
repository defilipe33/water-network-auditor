"""Referências locais primeiro; geocodificação unitária somente por ação explícita."""
import json,math,time
from urllib.parse import urlsplit,urlencode
from qgis.core import (QgsGeometry,QgsSpatialIndex,QgsCoordinateReferenceSystem,QgsCoordinateTransform,QgsProject,QgsUnitTypes,QgsFeature,QgsPointXY)


def referencia_cadastral(pacote,caso,config):
    origem=config.get('origem');campo=config.get('campo');uids=set(caso.get('gis_uids',[]));valores=[]
    if not origem or not campo:return None
    for t in pacote['dossie']['tubulacoes']:
        if t['uid'] in uids and t['origem']==origem:
            v=t.get('atributos',{}).get(campo)
            if v is not None and str(v).strip() and v not in valores:valores.append(v)
    if not valores:return None
    return dict(texto='Referência cadastral: '+' / '.join(map(str,valores))+' (atributo informado; não é endereço confirmado).',fonte='CADASTRO_GIS',origem=origem,campo=campo,valores=valores,precisao='ATRIBUTO_PRESERVADO')


class Logradouros:
    def __init__(self,camada,campo,crs,cancelado=None):
        self.crs=QgsCoordinateReferenceSystem(crs);self.nome=camada.name();self.campo=campo;self.dados={};self.index=QgsSpatialIndex()
        if not self.crs.isValid() or self.crs.mapUnits()!=QgsUnitTypes.DistanceMeters:raise ValueError('Localização por distância requer CRS métrico validado.')
        if not camada.isValid() or campo not in camada.fields().names() or not camada.crs().isValid():raise ValueError('Camada de ruas/campo/CRS inválido')
        from auditoria_fronteiras.entradas import valor_python
        trans=QgsCoordinateTransform(camada.crs(),self.crs,QgsProject.instance())
        for n,f in enumerate(camada.getFeatures()):
            if n%512==0 and cancelado and cancelado():raise InterruptedError('Indexação de ruas cancelada')
            g=QgsGeometry(f.geometry())
            if g.isEmpty() or g.type()!=1:continue
            if camada.crs()!=self.crs and g.transform(trans)!=0:raise ValueError('Transformação de logradouro falhou')
            a=QgsFeature(n);a.setGeometry(g);self.index.addFeature(a);self.dados[n]=(valor_python(f[campo]),g)
    def consultar(self,ponto,raio=100):
        if raio<0 or not math.isfinite(raio):raise ValueError('Raio inválido')
        caixa=ponto.boundingBox();caixa.grow(raio);candidatos=[]
        for i in self.index.intersects(caixa):
            nome,g=self.dados[i];d=ponto.distance(g)
            if nome is not None and str(nome).strip() and 0<=d<=raio:candidatos.append(dict(nome=str(nome),distancia_m=d,id=i))
        candidatos.sort(key=lambda r:(r['distancia_m'],r['nome']));cruz=[]
        # Cruzamentos são consultados pela caixa de cada eixo, sem pares de toda
        # a rede. Os candidatos continuam integralmente registrados.
        por_id={a['id']:a for a in candidatos}
        for n,a in enumerate(candidatos):
            proximos=self.index.intersects(self.dados[a['id']][1].boundingBox())
            for b in (por_id[i] for i in proximos if i in por_id and i>a['id']):
                if a['nome']==b['nome']:continue
                inter=self.dados[a['id']][1].intersection(self.dados[b['id']][1])
                if not inter.isEmpty() and inter.type()==0 and ponto.distance(inter)<=raio:cruz.append(dict(ruas=[a['nome'],b['nome']],distancia_m=ponto.distance(inter),criterio='INTERSECAO_GEOMETRICA_2D_NAO_COMPROVA_CRUZAMENTO_EM_NIVEL'))
        texto='Referência de localização não disponível'
        if candidatos:texto='Próximo ao eixo '+candidatos[0]['nome']+f" (~{candidatos[0]['distancia_m']:.1f} m); não é endereço exato."
        if cruz:texto+=' Interseção geométrica candidata: '+' / '.join(cruz[0]['ruas'])+'.'
        return dict(texto=texto,fonte=self.nome,campo=self.campo,precisao='DISTANCIA_2D_A_EIXO',candidatos=candidatos,cruzamentos=cruz)


def sanear_fonte(camada):
    """Nunca serializa URI, authcfg, senha ou tokens de conexões cartográficas."""
    m=camada.metadata()
    return dict(nome=camada.name(),provedor=camada.providerType(),crs=camada.crs().authid(),atribuicao=m.rights(),licencas=m.licenses(),tipo='REFERENCIA_CARTOGRAFICA')


class Geocodificador:
    def __init__(self):self.cache={};self.ultima=0
    def consultar(self,x,y,crs,config,autorizado=False):
        if not autorizado:raise PermissionError('Consultas externas desabilitadas. Nenhuma coordenada foi enviada.')
        endpoint=config.get('endpoint','');u=urlsplit(endpoint)
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:raise ValueError('Use endpoint HTTPS sem credenciais ou parâmetros na URL; autenticação fica no QGIS.')
        if u.hostname.lower()=='nominatim.openstreetmap.org':raise ValueError('A instância pública Nominatim não é oferecida como serviço genérico deste complemento. Configure serviço corporativo/contratado autorizado ou use ruas locais.')
        if not all(str(config.get(k,'')).strip() for k in ('termos','atribuicao','custos','armazenamento')):raise ValueError('Informe termos, atribuição, custos e política de armazenamento do serviço.')
        p=QgsCoordinateTransform(QgsCoordinateReferenceSystem(crs),QgsCoordinateReferenceSystem('EPSG:4326'),QgsProject.instance()).transform(QgsPointXY(x,y))
        chave=(endpoint,p.x(),p.y())
        if chave in self.cache:return self.cache[chave]
        if time.monotonic()-self.ultima<max(1,float(config.get('intervalo_s',1))):raise ValueError('Aguarde o intervalo de requisições do provedor.')
        from qgis.PyQt.QtCore import QUrl,QEventLoop,QTimer
        from qgis.PyQt.QtNetwork import QNetworkRequest,QNetworkReply
        from qgis.core import QgsNetworkAccessManager,QgsApplication
        req=QNetworkRequest(QUrl(endpoint+'?'+urlencode(dict(lat=p.y(),lon=p.x(),format='jsonv2'))));req.setRawHeader(b'User-Agent',b'WaterNetworkAuditor/1.8 location-single-request')
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute,QNetworkRequest.ManualRedirectPolicy)
        auth=config.get('authcfg')
        if auth:QgsApplication.authManager().updateNetworkRequest(req,auth)
        self.ultima=time.monotonic();reply=QgsNetworkAccessManager.instance().get(req);loop=QEventLoop();timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(reply.abort);reply.finished.connect(loop.quit);timer.start(10000)
        if not reply.isFinished():loop.exec_()
        timer.stop()
        try:
            if reply.error()!=QNetworkReply.NoError:raise RuntimeError('Serviço indisponível/sem autorização/timeout; use referência local ou manual.')
            status=reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if status is None or not 200<=int(status)<300:raise RuntimeError('Resposta HTTP não aprovada; nenhuma referência foi registrada.')
            if reply.bytesAvailable()>1024*1024:raise ValueError('Resposta externa excessiva')
            d=json.loads(bytes(reply.readAll()));texto=d.get('display_name')
            if not isinstance(texto,str) or not texto.strip():raise ValueError('Resposta externa sem referência interpretável')
            r=dict(texto=texto,fonte=u.hostname,precisao='GEOCODIFICACAO_NAO_ENDERECO_CONFIRMADO',atribuicao=config['atribuicao'],data=time.strftime('%Y-%m-%dT%H:%M:%S'))
            if config.get('cache_permitido'):self.cache[chave]=r
            return r
        finally:reply.deleteLater()
