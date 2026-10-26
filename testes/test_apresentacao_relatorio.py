"""Apresentação, rastreabilidade e XLSX no Python do QGIS."""
import builtins
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_auditoria_fronteiras import APP, camada, quadrado
import test_interface_fronteiras as interface_testes
from qgis.core import QgsProject
from auditoria_fronteiras import CamadaEntrada, Modo, Parametros, auditar
from auditoria_fronteiras.apresentacao import CAMPOS_PRINCIPAIS, preparar_apresentacao
from auditoria_fronteiras.visualizacao import criar_camadas_temporarias, carregar_no_projeto, resumir
from auditoria_fronteiras.relatorio import exportar_xlsx
from openpyxl import load_workbook


class ApresentacaoTest(unittest.TestCase):
    def resultado(self, modo=Modo.TRANSICAO, campo_nome='nome', poligonos=None, linhas=None):
        rede=camada('LineString',linhas or ['LINESTRING(-2 5,12 5)'])
        p=camada('Polygon',poligonos or [quadrado()])
        return auditar([CamadaEntrada(rede,'id')],[CamadaEntrada(p,'id',campo_nome,modo)],
                       Parametros(distancia_continuidade=0))

    def test_campos_principais_legiveis_e_curto_shp(self):
        r=self.resultado()
        pontos,tecnica=criar_camadas_temporarias(r)
        self.assertEqual(pontos.fields().names(),list(CAMPOS_PRINCIPAIS)+['EVT_UID'])
        self.assertTrue(all(len(n)<=10 for n in pontos.fields().names()))
        colunas={c.name:c.hidden for c in pontos.attributeTableConfig().columns()}
        self.assertTrue(colunas['EVT_UID'])
        self.assertTrue(all(not colunas[n] for n in CAMPOS_PRINCIPAIS))
        f=next(pontos.getFeatures())
        self.assertEqual(f['REG_DEPOIS'],'regiao_1')
        self.assertEqual(f['ID_REDE'],'1')
        self.assertEqual(f['AMBIGUO'],'Não')

    def test_id_numerico_intencional_nao_e_nome(self):
        r=self.resultado(Modo.PERIMETRO,'id')
        a=preparar_apresentacao(r)[0]
        self.assertEqual(a['registro']['AREA'],'1')
        self.assertEqual(a['registro']['REG_ANTES'],'')
        self.assertEqual(a['tecnico']['apresentacao']['substituicoes'],[])

    def test_sem_exibicao_utiliza_id_sem_adivinhar_nome(self):
        a=preparar_apresentacao(self.resultado(campo_nome=None))[0]
        self.assertEqual(a['registro']['REG_DEPOIS'],'1')
        self.assertEqual(a['tecnico']['apresentacao']['substituicoes'],[])

    def test_exibicao_vazia_fallback_registrado(self):
        for valor in (None,'','  '):
            r=self.resultado()
            r.ocorrencias[0].poligonos[0]['nome']=valor
            r.ocorrencias[0].regiao_depois[0]['nome']=valor
            a=preparar_apresentacao(r)[0]
            self.assertEqual(a['registro']['AREA'],'1')
            self.assertEqual(a['registro']['REG_DEPOIS'],'1')
            self.assertTrue(a['tecnico']['apresentacao']['substituicoes'])
            self.assertEqual(r.ocorrencias[0].poligonos[0]['nome'],valor)

    def test_identificacao_nula_indeterminado(self):
        r=self.resultado()
        for ref in r.ocorrencias[0].poligonos+r.ocorrencias[0].regiao_depois:
            ref['nome']=None
            ref['id_original']=None
        a=preparar_apresentacao(r)[0]
        self.assertEqual(a['registro']['AREA'],'Indeterminado')
        self.assertEqual(a['registro']['AMBIGUO'],'Sim')

    def test_exterior_indeterminado_extremidade_distintos(self):
        r=self.resultado()
        self.assertEqual(preparar_apresentacao(r)[0]['registro']['REG_ANTES'],'Fora das regiões cadastradas')
        r.ocorrencias[0].ambigua=True
        self.assertEqual(preparar_apresentacao(r)[0]['registro']['REG_ANTES'],'Indeterminado')
        r=self.resultado(linhas=['LINESTRING(0 5,5 5)'])
        self.assertEqual(preparar_apresentacao(r)[0]['registro']['REG_ANTES'],'Extremidade')

    def test_sobreposicoes_apresentam_todos_os_candidatos(self):
        r=self.resultado(poligonos=[quadrado(),quadrado(5)],linhas=['LINESTRING(-2 5,17 5)'])
        itens=preparar_apresentacao(r)
        self.assertTrue(any(i['registro']['REG_DEPOIS']=='regiao_1; regiao_2' for i in itens))
        self.assertTrue(any(i['registro']['AMBIGUO']=='Sim' for i in itens))
        self.assertEqual(len(itens),4)

    def test_duas_tubulacoes_e_ids_nulos(self):
        r=self.resultado(linhas=['LINESTRING(-2 5,0 5)','LINESTRING(0 5,5 5)'])
        evento=next(e for e in r.ocorrencias if e.classificacao=='CONTINUIDADE_POTENCIAL')
        evento.tubulacoes[0]['id_original']='001'
        evento.tubulacoes[1]['id_original']=None
        a=next(a for a in preparar_apresentacao(r) if a['uid']==evento.id)
        self.assertEqual(a['registro']['ID_REDE'],'001; Sem ID')
        self.assertEqual(a['tecnico']['tubulacoes'][0]['id_original'],'001')
        self.assertIsNone(a['tecnico']['tubulacoes'][1]['id_original'])

    def test_ids_iguais_em_camadas_diferentes_preservados(self):
        a=camada('LineString',['LINESTRING(-2 5,0 5)'],[7],nome='A')
        b=camada('LineString',['LINESTRING(0 5,5 5)'],[7],nome='B')
        p=camada('Polygon',[quadrado()])
        r=auditar([CamadaEntrada(a,'id'),CamadaEntrada(b,'id')],[CamadaEntrada(p,'id')])
        i=next(i for i in preparar_apresentacao(r) if i['registro']['CLASSIF']=='CONTINUIDADE_POTENCIAL')
        self.assertEqual(i['registro']['ID_REDE'],'7; 7')
        self.assertEqual(i['registro']['REDE'],'A; B')
        self.assertNotEqual(i['tecnico']['tubulacoes'][0]['chave'],i['tecnico']['tubulacoes'][1]['chave'])

    def test_vinculo_estavel_e_preservacao_integral(self):
        r=self.resultado()
        antes=deepcopy(r.ocorrencias[0].tubulacoes)
        camadas=criar_camadas_temporarias(r)
        f=next(camadas[0].getFeatures())
        t=next(camadas[1].getFeatures())
        self.assertEqual(f['EVT_UID'],t['ocorr_id'])
        dados=json.loads(t['registro'])
        self.assertEqual(dados['tubulacoes'],antes)
        self.assertEqual(dados['geometria_wkb_hex'],bytes(r.ocorrencias[0].geometria.asWkb()).hex())
        projeto=QgsProject()
        carregar_no_projeto(camadas,projeto)
        relacoes=list(projeto.relationManager().relations().values())
        self.assertEqual(len(relacoes),1)
        self.assertTrue(relacoes[0].isValid())
        self.assertEqual(relacoes[0].referencedLayerId(),camadas[1].id())
        projeto.clear()

    def test_resumo_sem_duplicar_fronteira_compartilhada(self):
        r=self.resultado(poligonos=[quadrado(),quadrado(10)],linhas=['LINESTRING(5 5,15 5)'])
        resumo=resumir(r)
        self.assertEqual(resumo['total'],1)
        self.assertEqual(resumo['transicoes'],1)
        self.assertEqual(resumo['perimetros'],0)
        self.assertEqual([a['total'] for a in resumo['areas']],[1,1])

    def test_id_evento_duplicado_rejeitado(self):
        r=self.resultado()
        r.ocorrencias.append(r.ocorrencias[0])
        with self.assertRaises(ValueError):
            preparar_apresentacao(r)

    def test_grupos_unicos_mesmo_instante_do_relogio(self):
        projeto=QgsProject()
        r=self.resultado()
        with patch('auditoria_fronteiras.visualizacao.datetime') as relogio:
            relogio.now.return_value.strftime.return_value='instante'
            a=carregar_no_projeto(criar_camadas_temporarias(r),projeto)
            b=carregar_no_projeto(criar_camadas_temporarias(r),projeto)
        self.assertNotEqual(a.name(),b.name())
        projeto.clear()


class RelatorioTest(unittest.TestCase):
    resultado = ApresentacaoTest.resultado
    def test_exportacao_tres_abas_e_json_completo(self):
        r=self.resultado()
        r.ocorrencias[0].tubulacoes[0]['id_original']='001234567890123456789'
        with tempfile.TemporaryDirectory() as pasta:
            saida=exportar_xlsx(r,Path(pasta)/'auditoria.xlsx')
            wb=load_workbook(saida['xlsx'])
            self.assertEqual(wb.sheetnames,['RESUMO','TRANSICOES_SETORES','TRAVESSIAS_PERIMETROS',
                'PONTOS_INVESTIGACAO','PARES_SETORES','SAIDAS_EXTERNAS','PARAMETROS','DETALHAMENTO_LOCAIS'])
            ws=wb['TRANSICOES_SETORES']
            self.assertEqual(ws.max_row-1,len(r.ocorrencias))
            self.assertEqual(ws['H2'].value,'001234567890123456789')
            self.assertEqual(ws['H2'].data_type,'s')
            self.assertIsInstance(ws['J2'].value,(float,int))
            self.assertEqual(ws.freeze_panes,'A2')
            self.assertIsNone(ws.auto_filter.ref)
            self.assertEqual(next(iter(ws.tables.values())).autoFilter.ref,'A1:K3')
            self.assertTrue(ws['A1'].font.bold)
            dados=json.loads(Path(saida['tecnico']).read_text(encoding='utf-8'))
            self.assertEqual(dados['ocorrencias'][0]['uid'],r.ocorrencias[0].id)
            self.assertEqual(dados['ocorrencias'][0]['tecnico']['tubulacoes'][0]['id_original'],'001234567890123456789')
            self.assertEqual(wb['RESUMO']['C2'].value,len(r.ocorrencias))
            wb.close()

    def test_excel_mesmos_valores_da_camada_principal(self):
        r=self.resultado(Modo.PERIMETRO,'id')
        features=list(criar_camadas_temporarias(r)[0].getFeatures())
        with tempfile.TemporaryDirectory() as pasta:
            s=exportar_xlsx(r,Path(pasta)/'a.xlsx')
            wb=load_workbook(s['xlsx'])
            rows=list(wb['TRAVESSIAS_PERIMETROS'].iter_rows(min_row=2,values_only=True))
            for row,f in zip(rows,features):
                self.assertEqual(row[:4],tuple(f[n] for n in CAMPOS_PRINCIPAIS[:4]))
                self.assertEqual(row[6:9],tuple(f[n] for n in CAMPOS_PRINCIPAIS[6:9]))
            self.assertEqual(len(rows),len(features))
            wb.close()

    def test_tecnico_longo_fragmentado_sem_perda(self):
        r=self.resultado()
        r.ocorrencias[0].detalhes['longo']='x'*40000
        with tempfile.TemporaryDirectory() as pasta:
            s=exportar_xlsx(r,Path(pasta)/'a.xlsx',True)
            wb=load_workbook(s['xlsx'])
            ws=wb['DETALHES_TECNICOS']
            partes=[row[3] for row in ws.iter_rows(min_row=2,values_only=True) if row[0]==1]
            self.assertGreater(len(partes),1)
            self.assertEqual(json.loads(''.join(partes))['detalhes']['longo'],'x'*40000)
            wb.close()

    def test_nao_sobrescreve_existentes(self):
        with tempfile.TemporaryDirectory() as pasta:
            p=Path(pasta)/'a.xlsx'
            p.write_bytes(b'original')
            with self.assertRaises(FileExistsError):
                exportar_xlsx(self.resultado(),p)
            self.assertEqual(p.read_bytes(),b'original')
            self.assertFalse(p.with_name('a_tecnico.json').exists())

    def test_cadastro_com_igual_nao_vira_formula(self):
        r=self.resultado()
        r.ocorrencias[0].tubulacoes[0]['id_original']='=1+2'
        with tempfile.TemporaryDirectory() as pasta:
            s=exportar_xlsx(r,Path(pasta)/'a.xlsx')
            wb=load_workbook(s['xlsx'])
            self.assertEqual(wb['TRANSICOES_SETORES']['H2'].data_type,'s')
            self.assertEqual(wb['TRANSICOES_SETORES']['H2'].value,'=1+2')
            wb.close()

    def test_resultado_cancelado_nao_exportado(self):
        r=self.resultado()
        r.cancelado=True
        with self.assertRaises(ValueError):
            exportar_xlsx(r,'nao_criar.xlsx')

    def test_sem_dependencia_nao_instala_nada(self):
        original=builtins.__import__
        def importar(nome,*args,**kwargs):
            if nome.startswith('openpyxl'):
                raise ImportError('Simulado')
            return original(nome,*args,**kwargs)
        with patch('builtins.__import__',side_effect=importar):
            with self.assertRaisesRegex(RuntimeError,'nenhum pacote foi instalado'):
                exportar_xlsx(self.resultado(),'nao_criar.xlsx')


class RelatorioInterfaceTest(unittest.TestCase):
    setUp = interface_testes.InterfaceTest.setUp
    tearDown = interface_testes.InterfaceTest.tearDown
    marcar = interface_testes.InterfaceTest.marcar
    configurar = interface_testes.InterfaceTest.configurar
    def test_campo_exibicao_pode_ser_identificador(self):
        self.configurar()
        for linha in range(self.janela.limites.rowCount()):
            combo=self.janela.limites.cellWidget(linha,3)
            combo.setCurrentIndex(combo.findData('id'))
        self.assertTrue(all(c.campo_nome=='id' for c in self.janela.configuracoes()[1]))

    def test_botao_excel_opcional_e_destino_escolhido(self):
        self.assertFalse(self.janela.exportar.isEnabled())
        self.configurar()
        self.janela.executar_auditoria()
        self.assertTrue(self.janela.exportar.isEnabled())
        with tempfile.TemporaryDirectory() as pasta:
            p=str(Path(pasta)/'relatorio.xlsx')
            with patch('auditoria_fronteiras.interface.QFileDialog.getSaveFileName',return_value=(p,'')):
                self.janela.gerar_relatorio()
            self.assertTrue(Path(p).exists())
            self.assertEqual(len(self.janela.camadas_geradas),2)

    def test_falha_excel_preserva_camadas_temporarias(self):
        self.configurar()
        self.janela.executar_auditoria()
        ids=[c.id() for c in self.janela.camadas_geradas]
        with patch('auditoria_fronteiras.interface.QFileDialog.getSaveFileName',return_value=('a.xlsx','')):
            with patch('auditoria_fronteiras.relatorio.exportar_xlsx',side_effect=RuntimeError('falha simulada')):
                self.janela.gerar_relatorio()
        self.warning.assert_called_once()
        self.assertEqual(ids,[c.id() for c in self.janela.camadas_geradas])


if __name__=='__main__':
    unittest.main(verbosity=2)
