"""Regressões da visão integral sobre fotografias sintéticas."""

import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from test_grafo_gis import linha
from test_redes_estruturantes_gis import executar, rede_arestas
from auditoria_aplicacao.macro_origem_gis import analisar, caminho, influencia, acessos_comparados, alternativa, trabalho
from auditoria_aplicacao.mapa_macro_origem import plano
from auditoria_aplicacao.revisao_macro_gis import revisar
from auditoria_aplicacao.exportar_macro_origem import exportar
from auditoria_aplicacao import persistencia_grafo_gis as pg


def rede():
    arestas = [('a', 'x', 'entrada', 10), ('x', 'y', 'tronco', 20), ('x', 'r', 'ramal', 15),
               ('x', 's', 'curto', 1), ('y', 'z', 'saída', 10), ('z', 'x', 'anel', 40),
               ('k', 'l', 'independente', 9)]
    return rede_arestas(arestas, [('A', 'a'), ('B', 'l')])


class MacroOrigem(unittest.TestCase):
    def test_cobertura_integral_e_exclusiva(self):
        foto = rede()
        m = analisar(foto, ['A'], minimo_m=8)
        self.assertEqual(m['alcancaveis'], list(range(6)))
        c = m['cobertura']
        self.assertEqual((c['alcancavel_m'], c['pipes_alcancaveis'], c['pipes_sem_acesso']), (96, 6, 1))
        self.assertAlmostEqual(c['alcancavel_m'], c['corredores_m'] + c['rede_restante_m'])
        self.assertEqual(c['alcancavel_m'], c['blocos_m'])
        self.assertEqual(sorted(i for b in m['blocos'] for i in b['segmentos']), list(range(6)))
        self.assertEqual(sum(len(b['pipes_principais']) for b in m['blocos']), 6)
        self.assertEqual(m['alternativas'], [5])
        for modo in ('AMBOS', 'COMPLETA', 'BLOCOS'):
            ids = [i for _, _, _, es in plano(foto, m, modo, m['blocos']) for i in es]
            self.assertEqual(sorted(ids), list(range(7 if modo == 'COMPLETA' else 6)))
        self.assertEqual(len({r[1] for r in plano(foto, m, 'CORREDORES', m['blocos'])}), 1)

    def test_sem_origem_e_duas_fontes(self):
        foto = rede()
        sem = analisar(foto, [])
        self.assertIsNone(sem['cobertura']['pipes_sem_acesso'])
        self.assertFalse(sem['corredores'])
        self.assertTrue(sem['pontes'])
        self.assertEqual(sum(len(b['segmentos']) for b in sem['detalhados']), 7)
        m = analisar(foto, ['A', 'B'], comparar=True)
        self.assertEqual(dict(acessos_comparados(m)), {('A',): list(range(6)), ('B',): [6]})
        self.assertEqual(caminho(foto, m, [4, 2], 'A'), [0, 1, 2, 4])
        self.assertEqual(caminho(foto, m, [4, 2], 'B'), [])

    def test_empate_e_compartilhamento(self):
        foto = rede_arestas([('a', 'x', 'ax', 1), ('b', 'x', 'bx', 1), ('x', 'y', 'xy', 2)],
                            [('A', 'a'), ('B', 'b')])
        m = analisar(foto, comparar=True)
        self.assertEqual(dict(acessos_comparados(m)), {('A', 'B'): [0, 1, 2]})
        self.assertEqual(influencia(foto, m)['EMPATE'], [0, 1, 2])

    def test_alternativa_sem_pipe_em_comum(self):
        foto = rede_arestas([('a', 'b', 't1', 2), ('b', 'd', 't2', 2),
                             ('a', 'c', 't3', 3), ('c', 'd', 't4', 3)], [('A', 'a')])
        m = analisar(foto)
        r = alternativa(foto, m, [1], None)
        self.assertEqual(r['referencia'], [0, 1])
        self.assertEqual(r['alternativa']['segmentos'], [2, 3])

    def test_revisao_preserva_original_e_particao(self):
        foto = rede()
        d = trabalho(foto, analisar(foto, ['A'], minimo_m=8))
        c = d['macro_origem']['corredores'][0]
        r = revisar(d, 'RENOMEAR_CORREDOR', c['uid'], 'Tronco norte')
        self.assertEqual(r['referencia'], d['uuid'])
        self.assertEqual(r['automatico_macro'], d['uuid'])
        self.assertNotEqual(c['nome'], r['macro_origem']['corredores'][0]['nome'])
        b = d['macro_origem']['blocos'][0]
        with self.assertRaises(ValueError):
            revisar(d, 'DIVIDIR', b['uid'], b['segmentos'])

    def test_dividir_e_reagrupar_com_continuidade(self):
        foto = rede_arestas([('a', 'b', 'p1', 20), ('b', 'c', 'p2', 20), ('c', 'd', 'p3', 20)], [('A', 'a')])
        d = trabalho(foto, analisar(foto))
        b, = d['macro_origem']['blocos']
        with self.assertRaises(ValueError):
            revisar(d, 'DIVIDIR', b['uid'], [1])
        r = revisar(d, 'DIVIDIR', b['uid'], [2])
        a, b = r['macro_origem']['blocos']
        unido = revisar(r, 'AGRUPAR', a['uid'], b['uid'])
        self.assertEqual(unido['automatico_macro'], d['uuid'])
        self.assertEqual(unido['macro_origem']['blocos'][0]['segmentos'], [0, 1, 2])

    def test_area_preserva_caminho_externo(self):
        from qgis.core import QgsGeometry
        foto = executar([linha('a', (0, 0), (10, 0)), linha('b', (10, 0), (20, 0)),
                         linha('c', (20, 0), (30, 0))], [('A', [('a', 0.)])])
        area1 = QgsGeometry.fromWkt('POLYGON ((21 -1, 29 -1, 29 1, 21 1, 21 -1))')
        area2 = QgsGeometry.fromWkt('POLYGON ((27 -2, 31 -2, 31 2, 27 2, 27 -2))')
        foto['areas'] = [dict(uid='setor', wkb=bytes(area1.asWkb()).hex(), fonte='S'),
                         dict(uid='zona', wkb=bytes(area2.asWkb()).hex(), fonte='Z')]
        m = analisar(foto, orientar_areas=True)
        i = next(i for i, e in enumerate(foto['arestas']) if e['tubo'] == 'c')
        self.assertEqual(m['areas_segmentos'][str(i)], {'setor': 8., 'zona': 3.})
        self.assertEqual(caminho(foto, m, [i]), [0, 1, 2])
        self.assertEqual(m['cobertura']['alcancavel_m'], 30.)

    def test_pipe_fisico_dividido_contado_uma_vez(self):
        foto = rede_arestas([('a', 'b', 'p1', 7), ('b', 'x', 'p2', 13), ('b', 'y', 'p3', 9)],
                            [('A', 'a')])
        for t in foto['tubos'][:2]:
            t['feicao'] = 'fisico'
        m = analisar(foto, minimo_m=1)
        self.assertEqual(m['cobertura']['pipes_alcancaveis'], 2)
        self.assertEqual(sum(len(b['pipes_principais']) for b in m['blocos']), 2)
        self.assertEqual(sum(b['comprimento_m'] for b in m['blocos']), 29.)

    def test_rede_municipal_e_cancelamento(self):
        from medir_estrutura_gis import foto_municipal
        from auditoria_fronteiras.modelos import Cancelado
        foto = foto_municipal(100)
        with self.assertRaises(Cancelado):
            analisar(foto, cancelar=lambda: True)
        m = analisar(foto, ['A'])
        self.assertEqual(m['cobertura']['arestas_alcancaveis'], 19800)
        self.assertEqual(sum(len(b['segmentos']) for b in m['blocos']), 19800)
        self.assertGreater(len(m['alternativas']), 1000)

    def test_exportacao_tres_formatos_e_reabertura(self):
        from osgeo import ogr
        f = executar([linha('a', (0, 0), (10, 0)), linha('b', (10, 0), (20, 0))],
                     [('A', [('a', 0.)])])
        d = trabalho(f, analisar(f))
        alvo = next(i for i, e in enumerate(f['arestas']) if e['tubo'] == 'b')
        with TemporaryDirectory() as raiz:
            for fmt in ('CSV', 'GPKG', 'ESRI Shapefile'):
                p = exportar(d, raiz, fmt, [alvo], tipo='Bloco', incluir_referencia=fmt != 'CSV')
                j = json.loads((p / 'validacao.json').read_text(encoding='utf-8'))
                self.assertEqual(len(j['segmentos_referencia_externos']), 1)
                self.assertEqual(j['conjunto_parcial'], fmt == 'CSV')
                if fmt != 'CSV':
                    ds = ogr.Open(str(p / ('rede_macro.gpkg' if fmt == 'GPKG' else 'pipes.shp')))
                    self.assertEqual(ds.GetLayerByName('pipes').GetFeatureCount(), 2)
                    ds.Destroy()
            g = Path(raiz) / 'resultado.gpkg'
            pg.salvar_estrutura(g, d)
            salvo = pg.carregar_estrutura(g, d['uuid'], f['projeto_uid'])
            self.assertEqual(salvo['macro_origem'], d['macro_origem'])
