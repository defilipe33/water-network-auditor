"""Destaques efêmeros de fontes cadastradas, sem alterar seleção ou renderer."""
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry,
    QgsProject, QgsRectangle, QgsVariantUtils, QgsVectorLayer, QgsVectorLayerFeatureSource,
)
from qgis.gui import QgsRubberBand

from .modelo_gis import expressao, identificar


def ler_destaque(fonte, filtro, ids, campos, cancelar, limite=500):
    request = QgsFeatureRequest().setSubsetOfAttributes(campos, fonte.fields()).setLimit(limite + 1)
    if ids is not None:
        request.setFilterFids(ids)
    if filtro:
        request.combineFilterExpression(filtro)
    dados, amostras = [], []
    for i, f in enumerate(fonte.getFeatures(request)):
        if cancelar():
            raise InterruptedError('Destaque cancelado.')
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

    def __init__(self, app, parent):
        super().__init__(parent)
        self.app = app
        self.canvas = app.iface.mapCanvas() if hasattr(app.iface, 'mapCanvas') else None
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

    def destacar(self, fonte, ids=None):
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
                                                  fonte['campos_mapeados'].get('label'))
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
