"""Regressões dos defeitos demonstrados na validação com o Composer."""
import copy
import unittest
from qgis.core import QgsGeometry
from test_topologia_watergems import modelo,elemento
import test_topologia_watergems as base
from auditoria_topologica_watergems.topologia import analisar,alcancaveis
from auditoria_topologica_watergems.resolucao import resolver_extremidades,auditar_jusantes
from auditoria_topologica_watergems.validacao import provar_correspondencia,associar_dossie


class ResolucaoComposerTest(unittest.TestCase):
    def test_jusante_nulo_nao_cria_componente_estrutural_artificial(self):
        m=modelo();m['elementos'][2]['topologia']['HMITopologyDownstreamLinkID']=None
        a=analisar(m);self.assertEqual(a['resumo']['componentes'],1)
        self.assertIn('JUSANTE_NAO_INFORMADO',a['resumo']['diagnosticos'])
    def test_dispositivo_isolado_so_um_componente(self):
        m=modelo();m['elementos'][99]=elemento(99,'TCV','DISPOSITIVO')
        a=analisar(m);self.assertEqual(a['resumo']['componentes'],2)
    def test_tcv_aberta_jusante_nulo_nao_inventa_porta(self):
        m=modelo();m['elementos'][2]['tipo']='TCV';m['elementos'][2]['topologia']={}
        self.assertEqual(analisar(m,'TODAS_VALVULAS_ABERTAS')['resumo']['componentes'],1)
    def test_retencao_sem_orientacao_nao_permite_passagem(self):
        m=modelo();m['elementos'][2]['topologia']={}
        self.assertNotIn(3,alcancaveis(analisar(m,'TODAS_VALVULAS_ABERTAS'),1))
    def test_bomba_sem_orientacao_nao_permite_passagem(self):
        m=modelo();m['elementos'][2]['tipo']='StandardPump';m['elementos'][2]['topologia']={}
        self.assertNotIn(3,alcancaveis(analisar(m,'TODAS_VALVULAS_ABERTAS'),1))
    def test_downstream_unico_supre_start_nulo(self):
        m=modelo();m['elementos'][11]['topologia']['HMITopologyStartNodeID']=None
        r=resolver_extremidades(m)[11];self.assertEqual(r['inicio'],2)
        self.assertEqual(r['inicio_fonte'],'DIRECTED_DOWNSTREAM_EXPLICITO')
        self.assertEqual(analisar(m)['resumo']['componentes'],1)
    def test_start_preenchido_inconsistente_nao_e_substituido(self):
        m=modelo();m['elementos'][11]['topologia']['HMITopologyStartNodeID']=999
        r=resolver_extremidades(m)[11];self.assertEqual(r['inicio'],999);self.assertTrue(r['conflito'])
    def test_dois_proprietarios_nao_escolhe_primeiro(self):
        m=modelo();m['elementos'][11]['topologia']['HMITopologyStartNodeID']=None
        m['elementos'][4]=elemento(4,'TCV','DISPOSITIVO',topologia={'HMITopologyDownstreamLinkID':11})
        r=resolver_extremidades(m)[11];self.assertIsNone(r['inicio']);self.assertTrue(r['conflito'])
    def test_dois_dispositivos_em_extremos_explicitos_nao_sao_ambiguos(self):
        m=modelo();m['elementos'][3]=elemento(3,'TCV','DISPOSITIVO',topologia={'HMITopologyDownstreamLinkID':11})
        r=resolver_extremidades(m)[11];self.assertFalse(r['conflito'])
        self.assertTrue(all(r['classificacao']=='VALIDA_EXPLICITA' for r in auditar_jusantes(m)))
    def test_jusante_valido_inativo_nao_e_referencia_invalida(self):
        m=modelo();m['elementos'][11]['ativo']=False
        a=analisar(m,'TODAS_VALVULAS_ABERTAS')
        self.assertIn('JUSANTE_ELEMENTO_INATIVO',a['resumo']['diagnosticos']);self.assertNotIn('JUSANTE_INVALIDO',a['resumo']['diagnosticos'])
    def test_stop_existente_nao_repete_no_start(self):
        m=modelo();m['elementos'][11]['topologia']={'HMITopologyStartNodeID':None,'HMITopologyStopNodeID':2}
        self.assertIsNone(resolver_extremidades(m)[11]['inicio'])
    def test_excluido_nao_supre_endpoint(self):
        m=modelo();m['elementos'][2]['excluido']=True;m['elementos'][11]['topologia']['HMITopologyStartNodeID']=None
        self.assertIsNone(resolver_extremidades(m)[11]['inicio'])
    def test_inativo_nao_e_reativado_por_resolucao(self):
        m=modelo();m['elementos'][2]['ativo']=False;m['elementos'][11]['topologia']['HMITopologyStartNodeID']=None
        self.assertEqual(analisar(m,'TODAS_VALVULAS_ABERTAS')['resumo']['conexoes'],0)
    def test_categorias_jusante_distintas(self):
        for valor,esperado in [(None,'REFERENCIA_NAO_INFORMADA'),(999,'REFERENCIA_INEXISTENTE'),(10,'POSSIVEL_INCONSISTENCIA_CADASTRAL')]:
            m=modelo();m['elementos'][2]['topologia']['HMITopologyDownstreamLinkID']=valor
            if valor==10:m['elementos'][10]['topologia']['HMITopologyStopNodeID']=3
            self.assertEqual(auditar_jusantes(m)[0]['classificacao'],esperado)
    def test_link_excluido_e_inativo_preservados(self):
        m=modelo();m['elementos'][11].update(excluido=True,ativo=False)
        r=auditar_jusantes(m)[0];self.assertEqual(r['classificacao'],'ELEMENTO_EXCLUIDO');self.assertIn('ELEMENTO_INATIVO',r['indicadores'])
    def test_uid_componente_estavel_ordem_independente(self):
        m=modelo();a=analisar(m);m['elementos']=dict(reversed(list(m['elementos'].items())))
        self.assertEqual(a['componentes'][0]['uid'],analisar(m)['componentes'][0]['uid'])
    def test_componentes_preservam_todos_os_tubos(self):
        a=analisar(modelo());self.assertEqual(sorted(i for c in a['componentes'] for i in c['tubulacoes']),[10,11])
        self.assertEqual(sum(c['proporcao_tubos'] for c in a['componentes']),1)
    def test_resolucao_nao_modifica_entrada(self):
        m=modelo();antes=copy.deepcopy(m);resolver_extremidades(m);analisar(m);self.assertEqual(m,antes)
    def test_chave_geom_inequivoca_e_inconsistente(self):
        m=modelo();regs=[dict(uid='a',origem='GIS-A',chave_cadastral='E-10',geometria=QgsGeometry.fromWkt('LINESTRING(0 0,1 0)'))]
        r,e=provar_correspondencia(m,regs,1,.01);self.assertEqual(r[0]['situacao'],'INEQUIVOCA')
        regs[0]['geometria']=QgsGeometry.fromWkt('LINESTRING(0 9,1 9)')
        self.assertEqual(provar_correspondencia(m,regs,1,.01)[0][0]['situacao'],'INCONSISTENTE')
    def test_chave_duplicada_no_gis_nao_e_inequivoca(self):
        m=modelo();r=dict(uid='a',origem='GIS-A',chave_cadastral='E-10',geometria=QgsGeometry.fromWkt('LINESTRING(0 0,1 0)'))
        out,_=provar_correspondencia(m,[r,dict(r,uid='b',origem='GIS-B')],1,.01)
        self.assertTrue(all(x['situacao']=='MULTIPLAS_CANDIDATAS' for x in out))
    def test_chave_gis_repetida_sem_candidato_wg_e_nao_encontrada(self):
        r=dict(uid='a',origem='GIS-A',chave_cadastral='ausente',geometria=QgsGeometry.fromWkt('LINESTRING(0 0,1 0)'))
        out,_=provar_correspondencia(modelo(),[r,dict(r,uid='b')],1,.01)
        self.assertTrue(all(x['situacao']=='NAO_ENCONTRADA' and 'CHAVE_GIS_REPETIDA' in x['indicadores'] for x in out))
    def test_vinculo_local_evento_no_sem_uid_sequencial(self):
        d=dict(evento_rede=[dict(evento_uid='evt',tubo_uid='gis')],local_evento=[dict(evento_uid='evt',local_uid='loc')])
        c=[dict(gis_uid='gis',situacao='INEQUIVOCA',candidatos=[10],nos=[dict(tubo=10,inicio=1,fim=2)])]
        r=associar_dossie(d,c);self.assertEqual(r[0]['nos'][0]['inicio'],1);self.assertEqual(r[0]['evento_uid'],'evt')
    def test_uid_componente_preservado_nas_tabelas(self):
        from auditoria_topologica_watergems.saidas import camadas
        m=modelo();a=analisar(m);cs={c.name():c for c in camadas(m,a)}
        uid=a['componentes'][0]['uid']
        self.assertTrue(all(f['COMP_UID']==uid for f in cs['WG_COMPONENTES'].getFeatures()))
        self.assertEqual(next(cs['WG_COMP_INFO'].getFeatures())['COMP_UID'],uid)
    def test_correspondencias_nulas_e_nao_encontradas_separadas(self):
        g=QgsGeometry.fromWkt('LINESTRING(0 0,1 0)')
        regs=[dict(uid='a',origem='GIS-A',chave_cadastral=None,geometria=g),dict(uid='b',origem='GIS-A',chave_cadastral='nao existe',geometria=g)]
        r,_=provar_correspondencia(modelo(),regs,1,.01)
        self.assertEqual([x['situacao'] for x in r],['INCONSISTENTE','NAO_ENCONTRADA'])


class HerancaCenarioComposerTest(unittest.TestCase):
    setUp=base.LeituraWatergemsTest.setUp
    tearDown=base.LeituraWatergemsTest.tearDown
    def test_alternativa_pai_do_cenario_mesmo_sem_parent_alt(self):
        self.b.alternativas[11]['ParentID']=None
        self.assertEqual(list(self.b.cadeia_alternativas(2,2)),[11,10])
        r=self.b.resolver('BaseLink_HMIDataSetTopology_Data',2,2)
        self.assertEqual(r[101]['AlternativeID'],10)
        self.assertEqual(r[101]['_origem_resolucao']['cenario_fonte'],1)
    def test_consulta_amostral_e_integral_equivalentes(self):
        integral=self.b.resolver('BaseLink_HMIDataSetTopology_Data',2,2)
        amostra=self.b.resolver('BaseLink_HMIDataSetTopology_Data',2,2,ids=[101])
        self.assertEqual(amostra,{101:integral[101]})


if __name__=='__main__':unittest.main()
