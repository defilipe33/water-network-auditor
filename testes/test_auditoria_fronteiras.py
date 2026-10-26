"""Regressões sintéticas usando o GEOS/PyQGIS efetivamente instalado."""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from qgis.core import (QgsApplication, QgsFeature, QgsGeometry, QgsProject,
                       QgsVectorLayer, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform)
from auditoria_fronteiras import CamadaEntrada, Modo, Parametros, auditar

APP = QgsApplication.instance() or QgsApplication([], False)
APP.initQgis()


def camada(tipo, wkts, ids=None, crs='EPSG:31983', nome='entrada'):
    c = QgsVectorLayer(f'{tipo}?crs={crs}&field=id:integer&field=nome:string', nome, 'memory')
    fs = []
    for i, wkt in enumerate(wkts):
        f = QgsFeature(c.fields())
        f.setAttributes([ids[i] if ids else i+1, f'regiao_{i+1}'])
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        fs.append(f)
    c.dataProvider().addFeatures(fs)
    c.updateExtents()
    return c


def quadrado(x=0, y=0, tamanho=10):
    b, d = x+tamanho, y+tamanho
    return f'POLYGON(({x} {y},{b} {y},{b} {d},{x} {d},{x} {y}))'


class AuditoriaTest(unittest.TestCase):
    def executar(self, linhas, poligonos=None, modo=Modo.PERIMETRO, **kwargs):
        rede = camada('MultiLineString' if any('MULTI' in s for s in linhas) else 'LineString', linhas)
        limite = camada('Polygon', poligonos or [quadrado()])
        resultado = auditar([CamadaEntrada(rede, 'id')],
            [CamadaEntrada(limite, 'id', 'nome', modo)],
            Parametros(distancia_continuidade=kwargs.pop('continuidade', 0), **kwargs))
        self.assertEqual(resultado.problemas, [])
        return resultado

    def eventos(self, r, classe):
        return [o for o in r.ocorrencias if o.classificacao == classe]

    def test_entrada_saida_poligono_isolado(self):
        r = self.executar(['LINESTRING(-2 5,12 5)'])
        self.assertEqual(len(self.eventos(r, 'TRAVESSIA')), 2)

    def test_transicao_exterior_e_regiao_sem_cobertura(self):
        r = self.executar(['LINESTRING(-2 5,12 5)'], modo=Modo.TRANSICAO)
        a,b = r.ocorrencias
        self.assertEqual(a.regiao_antes, [])
        self.assertEqual(len(a.regiao_depois), 1)
        self.assertEqual(len(b.regiao_antes), 1)
        self.assertEqual(b.regiao_depois, [])
        self.assertTrue(a.lado_antes_disponivel)

    def test_fronteira_compartilhada_transicao_unica(self):
        r = self.executar(['LINESTRING(5 5,15 5)'], [quadrado(), quadrado(10)], Modo.TRANSICAO)
        self.assertEqual(len(r.ocorrencias), 1)
        o = r.ocorrencias[0]
        self.assertEqual(o.classificacao, 'TRAVESSIA')
        self.assertEqual(len(o.poligonos), 2)
        self.assertEqual(o.regiao_antes[0]['id_original'], 1)
        self.assertEqual(o.regiao_depois[0]['id_original'], 2)

    def test_compartilhada_perimetro_preserva_dois(self):
        r = self.executar(['LINESTRING(5 5,15 5)'], [quadrado(), quadrado(10)])
        self.assertEqual(len(r.ocorrencias), 2)

    def test_aninhados_independentes(self):
        r = self.executar(['LINESTRING(-2 5,12 5)'], [quadrado(), quadrado(2,2,6)])
        self.assertEqual(len(self.eventos(r, 'TRAVESSIA')), 4)
        self.assertEqual(len({o.id for o in r.ocorrencias}), 4)

    def test_sobrepostos_preservam_candidatos(self):
        r = self.executar(['LINESTRING(-2 5,17 5)'], [quadrado(), quadrado(5)], Modo.TRANSICAO)
        self.assertEqual(len(r.ocorrencias), 4)
        self.assertTrue(any(len(o.regiao_antes) == 2 for o in r.ocorrencias))
        self.assertTrue(any(len(o.regiao_depois) == 2 for o in r.ocorrencias))
        self.assertTrue(any(o.ambigua for o in r.ocorrencias))

    def test_camadas_coincidentes_nao_eliminadas(self):
        rede = camada('LineString', ['LINESTRING(-2 5,12 5)'])
        a,b = camada('Polygon', [quadrado()]), camada('Polygon', [quadrado()])
        r = auditar([CamadaEntrada(rede)], [CamadaEntrada(a), CamadaEntrada(b)])
        self.assertEqual(len(r.ocorrencias), 4)

    def test_tangencia_vertice(self):
        r = self.executar(['LINESTRING(-2 2,0 0,2 -2)'])
        self.assertEqual([o.classificacao for o in r.ocorrencias], ['TANGENCIA'])

    def test_travessia_vertice(self):
        r = self.executar(['LINESTRING(-2 -2,5 5)'])
        self.assertEqual([o.classificacao for o in r.ocorrencias], ['TRAVESSIA'])

    def test_extremidade_nao_inventa_lado(self):
        r = self.executar(['LINESTRING(0 5,5 5)'], modo=Modo.TRANSICAO)
        o = r.ocorrencias[0]
        self.assertEqual(o.classificacao, 'EXTREMIDADE')
        self.assertFalse(o.lado_antes_disponivel)
        self.assertTrue(o.lado_depois_disponivel)

    def test_coincidencia_sem_pontos_artificiais(self):
        r = self.executar(['LINESTRING(-2 0,5 0,12 0)'])
        self.assertEqual([o.classificacao for o in r.ocorrencias], ['COINCIDENCIA'])
        self.assertAlmostEqual(r.ocorrencias[0].geometria.length(), 10)

    def test_coincidencia_compartilhada(self):
        r = self.executar(['LINESTRING(10 2,10 8)'], [quadrado(), quadrado(10)], Modo.TRANSICAO)
        self.assertEqual(len(r.ocorrencias), 1)
        self.assertEqual(len(r.ocorrencias[0].poligonos), 2)

    def test_multiplas_travessias_mesmo_poligono(self):
        r = self.executar(['LINESTRING(-2 2,12 2,12 8,-2 8)'])
        self.assertEqual(len(self.eventos(r, 'TRAVESSIA')), 4)

    def test_multilinha(self):
        r = self.executar(['MULTILINESTRING((-2 2,12 2),(-2 8,12 8))'])
        self.assertEqual(len(r.ocorrencias), 4)
        self.assertEqual({o.parte for o in r.ocorrencias}, {0,1})

    def test_furo_poligonal(self):
        p = 'POLYGON((0 0,10 0,10 10,0 10,0 0),(3 3,3 7,7 7,7 3,3 3))'
        r = self.executar(['LINESTRING(-2 5,12 5)'], [p])
        self.assertEqual(len(self.eventos(r,'TRAVESSIA')), 4)

    def test_cruzamento_entre_tubos_nao_cria_conexao(self):
        r = self.executar(['LINESTRING(2 5,8 5)', 'LINESTRING(5 2,5 8)'], continuidade=1)
        self.assertEqual(r.ocorrencias, [])

    def test_continuidade_coincidente(self):
        r = self.executar(['LINESTRING(-2 5,0 5)', 'LINESTRING(0 5,5 5)'], continuidade=1)
        eventos = self.eventos(r, 'CONTINUIDADE_POTENCIAL')
        self.assertEqual(len(eventos), 1)
        self.assertEqual(len(eventos[0].tubulacoes), 2)
        self.assertEqual(len(self.eventos(r,'EXTREMIDADE')), 2)

    def test_continuidade_separada_e_limite_distancia(self):
        linhas = ['LINESTRING(-2 5,-0.2 5)', 'LINESTRING(0.2 5,5 5)']
        r = self.executar(linhas, continuidade=.5)
        self.assertEqual(len(self.eventos(r,'CONTINUIDADE_POTENCIAL')), 1)
        r = self.executar(linhas, continuidade=.3)
        self.assertEqual(len(self.eventos(r,'CONTINUIDADE_POTENCIAL')), 0)

    def test_continuidade_mesmo_lado_rejeitada(self):
        r = self.executar(['LINESTRING(-2 5,-0.2 5)', 'LINESTRING(-0.3 5,-2 6)'], continuidade=1)
        self.assertEqual(self.eventos(r,'CONTINUIDADE_POTENCIAL'), [])

    def test_continuidade_transicao_compartilhada(self):
        r = self.executar(['LINESTRING(5 5,10 5)', 'LINESTRING(10 5,15 5)'],
            [quadrado(),quadrado(10)], Modo.TRANSICAO, continuidade=.5)
        e = self.eventos(r,'CONTINUIDADE_POTENCIAL')
        self.assertEqual(len(e), 1)
        self.assertEqual(len(e[0].poligonos), 2)

    def test_tolerancia_nao_funde_travessias_estreitas(self):
        r = self.executar(['LINESTRING(-1 0.002,1 0.002)'], [quadrado(0,0,.004)],
                         tolerancia_geometrica=.01)
        self.assertEqual(len(r.ocorrencias), 2)
        self.assertTrue(any(o.classificacao == 'AMBIGUA' for o in r.ocorrencias))

    def test_ids_repetidos_nulos_e_camadas_multiplas(self):
        a = camada('LineString',['LINESTRING(-2 2,12 2)','LINESTRING(-2 4,12 4)'],[7,7])
        b = camada('LineString',['LINESTRING(-2 6,12 6)'],[None])
        p = camada('Polygon',[quadrado()])
        r = auditar([CamadaEntrada(a,'id'),CamadaEntrada(b,'id')],[CamadaEntrada(p,'id')])
        self.assertEqual(len(r.ocorrencias),6)
        self.assertEqual(len({o.tubulacoes[0]['chave'] for o in r.ocorrencias}),3)
        self.assertTrue(any(o.tubulacoes[0]['id_original'] is None for o in r.ocorrencias))

    def test_preserva_entradas_e_selecao(self):
        a = camada('LineString',['LINESTRING(-2 5,12 5)'])
        p = camada('Polygon',[quadrado()])
        a.selectAll()
        antes = [(f.id(),bytes(f.geometry().asWkb()),f.attributes()) for f in a.getFeatures()]
        selecao = a.selectedFeatureIds()
        auditar([CamadaEntrada(a,'id')],[CamadaEntrada(p,'id')])
        self.assertEqual(antes,[(f.id(),bytes(f.geometry().asWkb()),f.attributes()) for f in a.getFeatures()])
        self.assertEqual(selecao,a.selectedFeatureIds())
        self.assertFalse(a.isEditable())

    def test_crs_graus_transformado(self):
        a = camada('LineString',['LINESTRING(-46.61 -23.5,-46.59 -23.5)'],crs='EPSG:4326')
        p = camada('Polygon',['POLYGON((-46.605 -23.51,-46.595 -23.51,-46.595 -23.49,-46.605 -23.49,-46.605 -23.51))'],crs='EPSG:4326')
        r = auditar([CamadaEntrada(a)],[CamadaEntrada(p)])
        self.assertEqual(r.problemas,[])
        self.assertEqual(len(r.ocorrencias),2)
        self.assertTrue(all(o.geometria.asPoint().x()>100000 for o in r.ocorrencias))

    def test_crs_processamento_invalido_e_nao_metrico(self):
        a,p = camada('LineString',['LINESTRING(1 1,2 2)']),camada('Polygon',[quadrado()])
        for crs in ('EPSG:4326','EPSG:2227','EPSG:4978','INVALIDO'):
            with self.assertRaises(ValueError):
                auditar([CamadaEntrada(a)],[CamadaEntrada(p)],Parametros(crs=crs))

    def test_campo_ausente(self):
        a,p = camada('LineString',['LINESTRING(1 1,2 2)']),camada('Polygon',[quadrado()])
        with self.assertRaises(ValueError):
            auditar([CamadaEntrada(a,'ausente')],[CamadaEntrada(p)])

    def test_geometria_invalida_reportada(self):
        a = camada('LineString',['LINESTRING(-2 5,12 5)'])
        p = camada('Polygon',['POLYGON((0 0,10 10,0 10,10 0,0 0))',quadrado()])
        r = auditar([CamadaEntrada(a)],[CamadaEntrada(p)])
        self.assertEqual(len(r.problemas),1)
        self.assertEqual(len(r.ocorrencias),2)

    def test_cancelamento(self):
        a,p = camada('LineString',['LINESTRING(-2 5,12 5)']),camada('Polygon',[quadrado()])
        r = auditar([CamadaEntrada(a)],[CamadaEntrada(p)],cancelar=lambda:True)
        self.assertTrue(r.cancelado)

    def test_parametro_negativo(self):
        with self.assertRaises(ValueError):
            Parametros(distancia_continuidade=-1).validar()

    def test_inversao_orientacao_geometrica(self):
        a = self.executar(['LINESTRING(5 5,15 5)'],[quadrado(),quadrado(10)],Modo.TRANSICAO)
        b = self.executar(['LINESTRING(15 5,5 5)'],[quadrado(),quadrado(10)],Modo.TRANSICAO)
        self.assertEqual(a.ocorrencias[0].regiao_antes[0]['id_original'],
                         b.ocorrencias[0].regiao_depois[0]['id_original'])
        self.assertEqual(a.ocorrencias[0].regiao_depois[0]['id_original'],
                         b.ocorrencias[0].regiao_antes[0]['id_original'])

    def test_revisita_mesma_coordenada_preserva_eventos(self):
        r = self.executar(['LINESTRING(-2 5,5 5,-2 5)'])
        self.assertEqual(len(r.ocorrencias),2)
        self.assertNotEqual(r.ocorrencias[0].distancia_linha,r.ocorrencias[1].distancia_linha)
        self.assertNotEqual(r.ocorrencias[0].id,r.ocorrencias[1].id)

    def test_multipoligono(self):
        a = camada('LineString',['LINESTRING(-2 5,32 5)'])
        p = camada('MultiPolygon',['MULTIPOLYGON(((0 0,10 0,10 10,0 10,0 0)),((20 0,30 0,30 10,20 10,20 0)))'])
        r = auditar([CamadaEntrada(a)],[CamadaEntrada(p)])
        self.assertEqual(r.problemas,[])
        self.assertEqual(len(self.eventos(r,'TRAVESSIA')),4)

    def test_aninhamento_transicao_regiao_externa_preservada(self):
        r = self.executar(['LINESTRING(1 5,9 5)'],[quadrado(),quadrado(2,2,6)],Modo.TRANSICAO)
        self.assertEqual(len(r.ocorrencias),2)
        self.assertEqual(len(r.ocorrencias[0].regiao_antes),1)
        self.assertEqual(len(r.ocorrencias[0].regiao_depois),2)

    def test_copias_identicas_preservadas_com_aviso(self):
        a = camada('LineString',['LINESTRING(-2 5,12 5)']*2,[7,7])
        fs = list(a.getFeatures())
        # Igualar todos os atributos para testar cópias realmente indistinguíveis.
        a.dataProvider().changeAttributeValues({fs[1].id():{1:'regiao_1'}})
        p = camada('Polygon',[quadrado()])
        r = auditar([CamadaEntrada(a,'id')],[CamadaEntrada(p,'id')])
        self.assertEqual(len(r.ocorrencias),4)
        self.assertEqual(len({o.tubulacoes[0]['chave'] for o in r.ocorrencias}),2)
        self.assertTrue(any('idênticas' in x['mensagem'] for x in r.problemas))

    def test_ids_estaveis_em_reexecucao(self):
        a,p = camada('LineString',['LINESTRING(-2 5,12 5)']),camada('Polygon',[quadrado()])
        args = ([CamadaEntrada(a,'id')],[CamadaEntrada(p,'id')])
        self.assertEqual([o.id for o in auditar(*args).ocorrencias],
                         [o.id for o in auditar(*args).ocorrencias])

    def test_crs_incompativeis_harmonizados(self):
        a = camada('LineString',['LINESTRING(-46.61 -23.5,-46.59 -23.5)'],crs='EPSG:4326')
        p = camada('Polygon',['POLYGON((-46.605 -23.51,-46.595 -23.51,-46.595 -23.49,-46.605 -23.49,-46.605 -23.51))'],crs='EPSG:4326')
        t = QgsCoordinateTransform(p.crs(),QgsCoordinateReferenceSystem('EPSG:31983'),QgsProject.instance())
        f = next(p.getFeatures())
        g = f.geometry()
        g.transform(t)
        b = camada('Polygon',[g.asWkt()])
        r = auditar([CamadaEntrada(a)],[CamadaEntrada(b)])
        self.assertEqual(r.problemas,[])
        self.assertEqual(len(r.ocorrencias),2)

    def test_fonte_vazia_e_geometria_vazia(self):
        a,p = camada('LineString',[]),camada('Polygon',[quadrado()])
        r = auditar([CamadaEntrada(a)],[CamadaEntrada(p)])
        self.assertTrue(any('Fonte vazia' == x['mensagem'] for x in r.problemas))
        a = camada('LineString',['LINESTRING EMPTY','LINESTRING(-2 5,12 5)'])
        r = auditar([CamadaEntrada(a)],[CamadaEntrada(p)])
        self.assertEqual(len(r.problemas),1)
        self.assertEqual(len(r.ocorrencias),2)

    def test_rejeita_tipo_errado_e_crs_ausente(self):
        a,p = camada('LineString',['LINESTRING(1 1,2 2)']),camada('Polygon',[quadrado()])
        with self.assertRaises(ValueError):
            auditar([CamadaEntrada(p)],[CamadaEntrada(p)])
        a.setCrs(QgsCoordinateReferenceSystem())
        with self.assertRaises(ValueError):
            auditar([CamadaEntrada(a)],[CamadaEntrada(p)])

    def test_mil_tubulacoes_sinteticas(self):
        linhas = [f'LINESTRING(-2 {i/100+0.001},12 {i/100+0.001})' for i in range(1000)]
        r = self.executar(linhas)
        self.assertEqual(len(r.ocorrencias),2000)
        self.assertEqual(len({o.id for o in r.ocorrencias}),2000)

    def test_linha_fechada_na_fronteira_sem_extremidade_artificial(self):
        r = self.executar(['LINESTRING(0 5,5 5,5 8,0 5)'])
        self.assertEqual(len(r.ocorrencias),1)
        self.assertEqual(r.ocorrencias[0].classificacao,'TANGENCIA')

    def test_continuidade_perimetros_aninhados_sem_precedencia(self):
        r = self.executar(['LINESTRING(-2 5,0 5)','LINESTRING(0 5,5 5)'],
            [quadrado(),quadrado(-5,-5,20)],continuidade=.5)
        self.assertEqual(len(self.eventos(r,'CONTINUIDADE_POTENCIAL')),1)

    def test_modos_distintos_camadas_simultaneas(self):
        a = camada('LineString',['LINESTRING(5 5,15 5)'])
        p = camada('Polygon',[quadrado(),quadrado(10)])
        q = camada('Polygon',[quadrado(),quadrado(10)])
        r = auditar([CamadaEntrada(a)], [CamadaEntrada(p,modo=Modo.TRANSICAO),CamadaEntrada(q)])
        self.assertEqual(len([o for o in r.ocorrencias if o.modo==Modo.TRANSICAO]),1)
        self.assertEqual(len([o for o in r.ocorrencias if o.modo==Modo.PERIMETRO]),2)

    def test_progresso_e_cancelamento_parcial(self):
        a = camada('LineString',['LINESTRING(-2 3,12 3)','LINESTRING(-2 7,12 7)'])
        p = camada('Polygon',[quadrado()])
        avanco=[]
        r = auditar([CamadaEntrada(a)],[CamadaEntrada(p)],
            cancelar=lambda: bool(avanco),progresso=lambda n,total: avanco.append((n,total)))
        self.assertTrue(r.cancelado)
        self.assertEqual(avanco,[(1,2)])
        self.assertEqual(len(r.ocorrencias),2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
