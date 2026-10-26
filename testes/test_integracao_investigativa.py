"""Investigação integrada: regras explícitas, persistência, interface e exportação."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from test_auditoria_fronteiras import APP
from test_topologia_watergems import modelo,elemento
from test_inspecao_exportacao import preparar as geo_fixture
from qgis.core import QgsGeometry,QgsProject
from auditoria_topologica_watergems.topologia import analisar
from auditoria_topologica_watergems.investigacao import *
from auditoria_topologica_watergems.contexto_integrado import contexto_espacial,carregar_topologica
from auditoria_topologica_watergems.integracao import preparar
from auditoria_topologica_watergems.saidas import camadas,exportar_json,exportar_geografico
from auditoria_topologica_watergems.saidas_integracao import salvar_gpkg,reabrir,exportar_relatorios,camadas_integradas
from auditoria_fronteiras.persistencia import salvar_execucao
from auditoria_topologica_watergems.arquivos import hash_arquivo
from validar_estrutura_xlsx import validar_xlsx


def associacao(i,uid=None):return dict(gis_uid=uid or f'gis-{i}',situacao='INEQUIVOCA',candidatos=[i],nos=[])


class RegrasIntegradasTest(unittest.TestCase):
    def avaliar(self,m=None,a=10,b=11,modo='ESTRUTURAL',**kw):
        m=m or modelo();ctx=preparar_contexto(m,analisar(m,modo));return classificar_par(m,ctx,associacao(a),associacao(b),**kw)
    def test_conexao_direta_por_no(self):self.assertIn(DIRETA,self.avaliar()['classes'])
    def test_no_comum_dispositivo_necessario(self):
        r=self.avaliar();self.assertIn(DISPOSITIVO,r['classes']);self.assertEqual(r['nos_compartilhados'],[2])
    def test_mesmo_componente_sem_no_comum(self):
        m=modelo();m['elementos'][4]=elemento(4);m['elementos'][12]=elemento(12,'IdahoPipe','LINK',topologia={'HMITopologyStartNodeID':3,'HMITopologyStopNodeID':4})
        r=self.avaliar(m,a=10,b=12);self.assertIn(MESMO,r['classes']);self.assertNotIn(DIRETA,r['classes'])
    def separado(self):
        m=modelo();m['elementos'][4]=elemento(4);m['elementos'][5]=elemento(5)
        m['elementos'][20]=elemento(20,'IdahoPipe','LINK',topologia={'HMITopologyStartNodeID':4,'HMITopologyStopNodeID':5});return m
    def test_distancia_sozinha_nao_cria_classe_ausente(self):
        r=self.avaliar(self.separado(),b=20,distancia=0);self.assertIn(DIFERENTES,r['classes']);self.assertNotIn(AUSENTE,r['classes'])
    def test_continuidade_e_proximidade_mais_componentes_diferentes(self):
        r=self.avaliar(self.separado(),b=20,continuidade=True,distancia=1,limiar=2);self.assertIn(AUSENTE,r['classes'])
    def test_sem_crs_sem_prova_metrica(self):
        self.assertNotIn(AUSENTE,self.avaliar(self.separado(),b=20,continuidade=True,distancia=None)['classes'])
    def test_limiar_insuficiente(self):
        self.assertNotIn(AUSENTE,self.avaliar(self.separado(),b=20,continuidade=True,distancia=10,limiar=2)['classes'])
    def test_indevida_apenas_com_restricao_confirmada_no_mesmo_projeto(self):
        regra=dict(projeto='projeto',tubos=[10,11],confirmada=True,fonte='Confirmação técnica de teste')
        self.assertIn(INDEVIDA,self.avaliar(restricoes=[regra])['classes'])
        self.assertNotIn(INDEVIDA,self.avaliar(restricoes=[dict(regra,confirmada=False)])['classes'])
        self.assertNotIn(INDEVIDA,self.avaliar(restricoes=[dict(regra,projeto='outro')])['classes'])
    def test_correspondencia_multipla_nao_escolhe_candidato(self):
        m=modelo();a=associacao(10);a['candidatos']=[10,11]
        r=classificar_par(m,preparar_contexto(m,analisar(m)),a,associacao(11));self.assertEqual(r['classes'],[INSUFICIENTE])
    def test_bomba_bloqueada_na_hipotese_nao_nega_no_compartilhado(self):
        m=modelo();m['elementos'][2]['tipo']='StandardPump'
        r=self.avaliar(m,modo='TODAS_VALVULAS_ABERTAS');self.assertIn(DIRETA,r['classes']);self.assertIn(DISPOSITIVO,r['classes']);self.assertIsNone(r['caminho_ab'])
    def test_retencao_direcional_nao_e_vazao(self):
        r=self.avaliar(modo='TODAS_VALVULAS_ABERTAS');self.assertIsNotNone(r['caminho_ab']);self.assertIsNone(r['caminho_ba'])
    def test_alternativa_que_nao_usa_no_compartilhado(self):
        m=modelo();m['elementos'][12]=elemento(12,'IdahoPipe','LINK',topologia={'HMITopologyStartNodeID':1,'HMITopologyStopNodeID':3})
        r=self.avaliar(m);self.assertTrue(r['alternativa_sem_nos_compartilhados']);self.assertFalse(r['dependencia_dispositivos'])
    def test_bomba_nao_e_fonte_de_agua(self):
        m=modelo();m['elementos'][2]['tipo']='StandardPump';inv,ms,fs=inventariar_componentes(m,analisar(m))
        self.assertFalse(fs[0]['fonte_agua']);self.assertFalse(inv[0]['caminho_estrutural_ate_fonte'])
    def test_reservatorio_e_tanque_diferenciados(self):
        m=modelo();m['elementos'][1]['tipo']='IdahoReservoir';m['elementos'][3]['tipo']='ConventionalTank'
        inv,ms,fs=inventariar_componentes(m,analisar(m));self.assertEqual(inv[0]['reservatorios'],[1]);self.assertEqual(inv[0]['tanques'],[3])
    def test_distancia_exata_entre_componentes_nao_e_conexao(self):
        cs=[dict(uid='a',nos=[1],tubos=[],vizinhos=[],areas=[]),dict(uid='b',nos=[2],tubos=[],vizinhos=[],areas=[])]
        g={1:QgsGeometry.fromWkt('POINT(0 0)'),2:QgsGeometry.fromWkt('POINT(3 4)')}
        r=contexto_espacial(cs,g);self.assertEqual(len(r),2);self.assertAlmostEqual(cs[0]['distancia_m'],5)
    def test_contexto_desconhecido_nao_mede(self):self.assertEqual(contexto_espacial([],None),[])
    def test_entrada_e_grafo_aprovado_nao_sao_modificados(self):
        m=modelo();antes=copy.deepcopy(m);r=analisar(m);n=r['grafo'].number_of_edges();self.avaliar(m);self.assertEqual(m,antes);self.assertEqual(r['grafo'].number_of_edges(),n)


class IntegracaoPersistidaTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.p=Path(self.tmp.name)
        r,a,d,redes,pol=geo_fixture();self.d=d;self.geo=self.p/'geo.gpkg';salvar_execucao(self.geo,d)
        m=modelo();m['referencia_espacial']=dict(crs='EPSG:31983',fator=1,fonte='Geometrias sintéticas métricas')
        t=analisar(m);t['associacoes']=[dict(associacao(i,x['uid']),origem=x['origem'],erro_xy_m=0,chave_cadastral=x['id_bruto']) for i,x in zip((10,11),d['tubulacoes'])]
        self.json=self.p/'topo.json';exportar_json(m,t,self.json,completo=False)
        exportar_geografico(camadas(m,t,crs='EPSG:31983'),self.p/'topo','GPKG');self.gpkg=self.p/'topo/TOPOLOGIA.gpkg'
        self.antes=[hash_arquivo(x) for x in (self.geo,self.json,self.gpkg)]
    def tearDown(self):QgsProject.instance().removeAllMapLayers();self.tmp.cleanup()
    def executar(self):return preparar(self.geo,self.d['execucao_uid'],self.json,self.gpkg)
    def test_recupera_grafo_da_execucao_persistida(self):
        t=carregar_topologica(self.json,self.gpkg);self.assertEqual(t['estrutural']['resumo']['conexoes'],2)
    def test_origens_preservadas(self):
        p=self.executar();self.assertEqual(self.antes,[hash_arquivo(x) for x in (self.geo,self.json,self.gpkg)])
    def test_json_e_gpkg_de_execucoes_diferentes_rejeitados(self):
        d=json.loads(self.json.read_text());d['modelo']['projeto']='outro';f=self.p/'incompativel.json';f.write_text(json.dumps(d))
        with self.assertRaises(ValueError):carregar_topologica(f,self.gpkg)
    def test_salvar_reabrir_e_integridade_relacional(self):
        p=self.executar();f=salvar_gpkg(p,self.p/'integrada.gpkg');q=reabrir(f)
        self.assertEqual(p['resultado']['meta']['uid'],q['resultado']['meta']['uid'])
        with sqlite3.connect(f) as c:self.assertFalse(c.execute('pragma foreign_key_check').fetchall());self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok')
    def test_exportacoes_xlsx_shp(self):
        p=self.executar();exportar_relatorios(p,self.p/'saidas')
        self.assertTrue(validar_xlsx(self.p/'saidas/INVESTIGACAO_INTEGRADA.xlsx')['valido'])
        self.assertTrue((self.p/'saidas/SHP/IG_LOCAIS_ESTRUTURAL.prj').exists())
        dic=json.loads((self.p/'saidas/SHP/DICIONARIO_INTEGRACAO.json').read_text(encoding='utf8'))
        for camada in camadas_integradas(p):
            for campo in camada.fields():
                self.assertLessEqual(len(campo.name()),10)
                self.assertIn(campo.name(),dic['campos'])
    def test_destino_existente_nao_e_sobrescrito(self):
        p=self.executar();f=salvar_gpkg(p,self.p/'integrada.gpkg');h=hash_arquivo(f)
        with self.assertRaises(FileExistsError):salvar_gpkg(p,f)
        self.assertEqual(hash_arquivo(f),h)
    def test_cancelamento_sem_resultado_publicado(self):
        p=self.executar();f=self.p/'cancelada.gpkg'
        with self.assertRaises(InterruptedError):salvar_gpkg(p,f,cancelar=lambda:True)
        self.assertFalse(f.exists());self.assertEqual(self.antes[0],hash_arquivo(self.geo))
    def test_nova_versao_preserva_integracao_anterior(self):
        p=self.executar();f=salvar_gpkg(p,self.p/'v1.gpkg');anterior=hash_arquivo(f)
        q=preparar(f,self.d['execucao_uid'],self.json,self.gpkg)
        g=salvar_gpkg(q,self.p/'v2.gpkg')
        with sqlite3.connect(g) as c:self.assertEqual(c.execute('select count(*) from IG_EXECUCOES').fetchone()[0],2)
        self.assertEqual(hash_arquivo(f),anterior)
        self.assertEqual(reabrir(g,p['resultado']['meta']['uid'])['resultado']['meta']['uid'],p['resultado']['meta']['uid'])
    def test_painel_enriquecido_sem_alterar_gis(self):
        from auditoria_topologica_watergems.painel_integrado import abrir_painel,DialogComponentes
        p=self.executar();f=salvar_gpkg(p,self.p/'integrada.gpkg');j=abrir_painel(p,f)
        j.locais.setCurrentIndex(1);APP.processEvents()
        self.assertTrue(any('WaterGEMS' in j.arvore.topLevelItem(i).text(0) for i in range(j.arvore.topLevelItemCount())))
        c=DialogComponentes(j);c.porte.setCurrentText('TODOS');APP.processEvents();self.assertGreater(c.componentes.count(),0);c.close();j.close()
    def test_reabrir_painel_na_mesma_base_nao_duplica_camadas(self):
        from auditoria_topologica_watergems.painel_integrado import abrir_painel
        p=self.executar();f=salvar_gpkg(p,self.p/'integrada.gpkg')
        j=abrir_painel(p,f);n=len(QgsProject.instance().mapLayers());j.close();j.desativar()
        outro=abrir_painel(reabrir(f),f);self.assertEqual(len(QgsProject.instance().mapLayers()),n);outro.close()
    def test_snapshot_reabre_sem_origens_disponiveis(self):
        p=self.executar();f=salvar_gpkg(p,self.p/'integrada.gpkg')
        with patch('auditoria_topologica_watergems.contexto_integrado.carregar_topologica',side_effect=AssertionError('Não consultar origens')):
            q=reabrir(f)
        self.assertEqual(q['resultado']['meta']['uid'],p['resultado']['meta']['uid'])


if __name__=='__main__':unittest.main()
