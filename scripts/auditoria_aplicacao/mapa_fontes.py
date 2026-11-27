"""Destaques efêmeros de fontes cadastradas, sem alterar seleção ou renderer."""
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry,
    QgsProject, QgsRectangle, QgsVariantUtils, QgsVectorLayer, QgsVectorLayerFeatureSource,
    QgsExpressionContext,
)
from qgis.gui import QgsRubberBand

from .modelo_gis import expressao, identificar


def ler_destaque(fonte, filtro, ids, campos, cancelar, limite=500):
    expr = expressao(filtro, fonte.fields().names())
    atributos = sorted(set(campos) | (expr.referencedColumns() if expr else set()))
    request = QgsFeatureRequest().setSubsetOfAttributes(atributos, fonte.fields()).setLimit(limite + 1)
    if ids is not None:
        request.setFilterFids(ids)
    elif filtro:
        request.setFilterExpression(filtro)
    # FIDs e expressão são tipos de filtro exclusivos de QgsFeatureRequest.
    # Aplicar ambos no request substituiria a seleção por todas as correspondências.
    contexto = QgsExpressionContext()
    dados, amostras = [], []
    for i, f in enumerate(fonte.getFeatures(request)):
        if cancelar():
            raise InterruptedError('Destaque cancelado.')
        if ids is not None and expr is not None:
            contexto.setFeature(f)
            valor = expr.evaluate(contexto)
            if expr.hasEvalError():
                raise ValueError('Não foi possível avaliar o filtro do destaque: ' + expr.evalErrorString())
            if QgsVariantUtils.isNull(valor) or not valor:
                continue
        if i == limite:
            return dados, amostras, True
        if not f.hasGeometry() or f.geometry().isEmpty():
            continue
        dados.append(bytes(f.geometry().asWkb()))
        if len(amostras) < 8:
            valores = [f'{c} = ' + ('Nulo' if QgsVariantUtils.isNull(f[c]) else str(f[c])) for c in campos]
            amostras.append(f'FID {f.id()} · ' + ' · '.join(valores))
    return dados, amostras, False


class MapaFontes(QObject):
    mensagem = pyqtSignal(str)

    def __init__(self, app, parent, canvas=None):
        super().__init__(parent)
        self.app = app
        self.canvas = canvas if app is None else getattr(app.iface,'mapCanvas',lambda:None)()
        self.itens, self.caixas = [], []
        self.camada, self.fonte = None, None
        self.geracao = 0
        if self.canvas:
            self.canvas.destinationCrsChanged.connect(self.limpar)
        QgsProject.instance().layersWillBeRemoved.connect(self.removidas)

    def removidas(self, ids):
        if self.camada and not sip.isdeleted(self.camada) and self.camada.id() in ids:
            self.limpar()

    def limpar(self):
        self.geracao += 1
        if self.camada is not None and not sip.isdeleted(self.camada):
            try:
                self.camada.selectionChanged.disconnect(self.selecao)
            except (TypeError, RuntimeError):
                pass
        self.camada = self.fonte = None
        if self.canvas and not sip.isdeleted(self.canvas):
            for item in self.itens:
                self.canvas.scene().removeItem(item)
        self.itens.clear()
        self.caixas.clear()

    def selecao(self, *_):
        if not self.camada or sip.isdeleted(self.camada):
            return
        fonte, camada = self.fonte, self.camada
        ids = camada.selectedFeatureIds()
        self.destacar(fonte, ids if ids else None)

    def destacar(self, fonte, ids=None, aproximar=False):
        if self.app.atividades.em_execucao():
            self.mensagem.emit('Aguarde a atividade atual antes de destacar a fonte.')
            return False
        self.limpar()
        if not self.canvas or sip.isdeleted(self.canvas):
            self.mensagem.emit('Mapa QGIS indisponível nesta sessão.')
            return False
        camada = identificar(fonte, QgsProject.instance().mapLayers().values())
        if not isinstance(camada, QgsVectorLayer):
            self.mensagem.emit('Fonte indisponível ou sem geometria vetorial. Carregue ou relocalize a fonte.')
            return False
        if camada.geometryType() not in (0, 1, 2):
            self.mensagem.emit('Fonte tabular sem geometria para destaque.')
            return False
        crs = camada.crs()
        if not crs.isValid() or not self.canvas.mapSettings().destinationCrs().isValid():
            self.mensagem.emit('Destaque bloqueado. Confira o CRS da camada e do mapa.')
            return False
        try:
            expressao(fonte['filtro'], camada.fields().names())
        except ValueError as e:
            self.mensagem.emit(str(e))
            return False
        campos = list(dict.fromkeys(c for c in (fonte['campos_mapeados'].get('id'),
                                                  fonte['campos_mapeados'].get('label'),
                                                  fonte['campos_mapeados'].get('nome'))
                                    if c and c in camada.fields().names()))
        origem = QgsVectorLayerFeatureSource(camada)
        self.camada, self.fonte = camada, fonte
        camada.selectionChanged.connect(self.selecao)
        geracao = self.geracao
        destino = self.canvas.mapSettings().destinationCrs()
        trans = QgsCoordinateTransform(crs, destino, QgsProject.instance())

        def receber(dados):
            if geracao != self.geracao:
                return False
            wkbs, amostras, parcial = dados
            grupos = {}
            try:
                for wkb in wkbs:
                    g = QgsGeometry()
                    g.fromWkb(wkb)
                    g.transform(trans)
                    grupos.setdefault(g.type(), []).append(g)
                    self.caixas.append(g.boundingBox())
                for tipo, gs in grupos.items():
                    item = QgsRubberBand(self.canvas, tipo)
                    item.setColor(QColor('#2458bc' if tipo == 1 else '#126656'))
                    item.setFillColor(QColor(0, 0, 0, 0))
                    item.setWidth(3)
                    item.setIcon(QgsRubberBand.ICON_CIRCLE)
                    item.setIconSize(11)
                    item.setToGeometry(QgsGeometry.collectGeometry(gs), None)
                    self.itens.append(item)
            except Exception:
                self.limpar()
                raise
            texto = f"{fonte['nome']} · {len(wkbs)} feição(ões) destacada(s)"
            texto += ' · prévia limitada a 500; selecione feições para detalhar.' if parcial else '.'
            texto += '\n' + '\n'.join(amostras) if ids is not None else ''
            if not wkbs:
                texto += ' Sem geometria correspondente ao filtro/seleção.'
            self.mensagem.emit(texto)
            if aproximar and wkbs:
                self.aproximar()

        self.app.atividades.executar_thread(
            'Destacar fonte GIS', fonte['nome'],
            lambda parar, _: ler_destaque(origem, fonte['filtro'], ids, campos, parar),
            receber, self.mensagem.emit)
        return True

    def aproximar(self):
        if not self.canvas or not self.caixas:
            self.mensagem.emit('Destaque uma fonte ou feição antes de enquadrar.')
            return
        caixa = QgsRectangle(self.caixas[0])
        for c in self.caixas[1:]:
            caixa.combineExtentWith(c)
        if caixa.width() == 0 or caixa.height() == 0:
            caixa.grow(max(self.canvas.mapUnitsPerPixel() * 35, 0.000001))
        caixa.scale(1.2)
        self.canvas.setExtent(caixa)
        self.canvas.refresh()

    def destacar_geometria(self, geometria, crs, nome):
        if self.app.atividades.em_execucao() or not self.canvas:
            return False
        self.limpar()
        g = QgsGeometry(geometria)
        if not crs.isValid() or not self.canvas.mapSettings().destinationCrs().isValid():
            self.mensagem.emit('Confira o CRS do resultado e do mapa.'); return False
        trans = QgsCoordinateTransform(crs, self.canvas.mapSettings().destinationCrs(), QgsProject.instance())
        if g.transform(trans) != 0:
            self.mensagem.emit('Não foi possível transformar o destaque.'); return False
        b = QgsRubberBand(self.canvas, g.type())
        b.setColor(QColor(45, 110, 230, 200)); b.setWidth(3); b.setToGeometry(g, None)
        self.itens.append(b); self.caixas.append(g.boundingBox())
        self.mensagem.emit(nome + ' · destaque temporário; use Enquadrar para aproximar.')
        return True

    def destacar_investigacao(self, itens, crs, aproximar=False,toda_extensao=False,foco=None):
        if (self.app is not None and self.app.atividades.em_execucao()) or not self.canvas:return False
        self.limpar()
        destino=self.canvas.mapSettings().destinationCrs()
        if not crs.isValid() or not destino.isValid():raise ValueError('Confira o CRS do trabalho e do mapa.')
        trans=QgsCoordinateTransform(crs,destino,QgsProject.instance())
        caixas=[]
        for papel,geom in itens:
            if geom is None or geom.isNull() or geom.isEmpty():continue
            g=QgsGeometry(geom)
            if g.transform(trans)!=0:raise ValueError('Falha na transformação do destaque.')
            from .relevancia_gis import SIMBOLOS
            categoria=papel.removeprefix('evento_') if papel.startswith('evento_') else None
            cor=QColor(SIMBOLOS[categoria][0]) if categoria in SIMBOLOS else {
                'tubo':QColor(0,150,210,230),'evento':QColor(235,120,20,240),'local':QColor(180,70,210,240),
                'equipamento':QColor(30,185,130,240),'vinculo':QColor(80,140,170,230),
                'inicio_corredor':QColor(15,137,98,245),'fim_corredor':QColor(208,87,15,245),
                'ramificacao':QColor(134,65,192,250),
                'correcao_original':QColor(78,91,108,230),'correcao_segmento':QColor(13,155,135,240),
            }[papel]
            b=QgsRubberBand(self.canvas,g.type());b.setColor(cor);b.setFillColor(QColor(0,0,0,0));b.setWidth(4 if papel=='tubo' else 3)
            if papel in ('vinculo','correcao_segmento'):
                from qgis.PyQt.QtCore import Qt
                b.setLineStyle(Qt.DashLine)
            if papel=='correcao_original':b.setWidth(7)
            icones={'REVISAR':QgsRubberBand.ICON_CROSS,'INCONSISTENCIA_IDENTIFICADA':QgsRubberBand.ICON_DIAMOND,'INDETERMINADA':QgsRubberBand.ICON_BOX}
            por_papel={'local':QgsRubberBand.ICON_BOX,'equipamento':QgsRubberBand.ICON_BOX,
                       'inicio_corredor':QgsRubberBand.ICON_BOX,'fim_corredor':QgsRubberBand.ICON_DIAMOND,
                       'ramificacao':QgsRubberBand.ICON_CROSS}
            b.setIcon(icones.get(categoria,por_papel.get(papel,QgsRubberBand.ICON_CIRCLE)))
            b.setIconSize(12 if papel=='local' else 9);b.setToGeometry(g,None)
            self.itens.append(b);self.caixas.append(g.boundingBox())
            if papel!='local':caixas.append(geom.boundingBox())
        if aproximar and self.itens:
            caixas=caixas or [g.boundingBox() for _,g in itens if g is not None]
            caixa=QgsRectangle(caixas[0])
            for c in caixas[1:]:caixa.combineExtentWith(c)
            eventos=[g.boundingBox() for papel,g in itens if papel.startswith('evento') and g is not None and not g.isEmpty()]
            if eventos and not toda_extensao:
                local=QgsRectangle(eventos[0])
                for c in eventos[1:]:local.combineExtentWith(c)
                # Um tubo extenso não deve afastar a vista do ponto investigado.
                # O desenho continua integral; somente o enquadramento é local.
                janela=max(200,4*max(local.width(),local.height()))
                if max(caixa.width(),caixa.height())>janela:
                    caixa=local
                    self.mensagem.emit('Aproximação focada nas ocorrências. Tubulações extensas continuam destacadas; use Ver toda a extensão para enquadrá-las integralmente.')
            if foco is not None and not foco.isEmpty():
                caixa=foco.boundingBox()
            # O CRS dos trabalhos é métrico validado; mínimo de 30 m antes da margem.
            centro=caixa.center();w=max(30,caixa.width());h=max(30,caixa.height())
            caixa=QgsRectangle(centro.x()-w/2,centro.y()-h/2,centro.x()+w/2,centro.y()+h/2);caixa.scale(1.15)
            self.canvas.setExtent(trans.transformBoundingBox(caixa));self.canvas.refresh()
        return bool(self.itens)
