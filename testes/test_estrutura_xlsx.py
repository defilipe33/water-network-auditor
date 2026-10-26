"""Regressões do pacote OOXML, independentes da tolerância do openpyxl."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

import test_apresentacao_relatorio as apresentacao_testes
from auditoria_fronteiras.relatorio import exportar_xlsx
from validar_estrutura_xlsx import validar_xlsx, S


class EstruturaXlsxTest(unittest.TestCase):
    resultado=apresentacao_testes.ApresentacaoTest.resultado

    def gerar(self,pasta,detalhes=False,resultado=None):
        return Path(exportar_xlsx(resultado or self.resultado(),Path(pasta)/'novo.xlsx',detalhes)['xlsx'])

    @staticmethod
    def adulterar(arquivo,parte,alterar):
        saida=BytesIO()
        with zipfile.ZipFile(arquivo) as z, zipfile.ZipFile(saida,'w',zipfile.ZIP_DEFLATED) as novo:
            for n in z.namelist():
                dados=z.read(n)
                if n==parte:
                    root=ET.fromstring(dados)
                    alterar(root)
                    dados=ET.tostring(root)
                novo.writestr(n,dados)
        saida.seek(0)
        return saida

    def test_tabelas_relacoes_cabecalhos_e_filtros_validos(self):
        with tempfile.TemporaryDirectory() as pasta:
            r=validar_xlsx(self.gerar(pasta))
            self.assertTrue(r['valido'],r['erros'])
            self.assertIsNone(r['abas'][0]['filtro_planilha'])
            self.assertIsNone(r['abas'][1]['filtro_planilha'])
            self.assertEqual(r['abas'][1]['tabelas'][0]['registros'],2)
            self.assertEqual(r['abas'][2]['filtro_planilha'],'A1:K1')

    def test_resumo_exclui_notas_fora_do_bloco(self):
        with tempfile.TemporaryDirectory() as pasta:
            p=self.gerar(pasta)
            with zipfile.ZipFile(p) as z:
                tabela=ET.fromstring(z.read('xl/tables/table1.xml'))
                sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
                self.assertIn(':F',tabela.get('ref'))
                self.assertIn(':H',sheet.find(f'{{{S}}}dimension').get('ref'))
                self.assertEqual(tabela.find(f'{{{S}}}autoFilter').get('ref'),tabela.get('ref'))

    def test_caminho_opcional_tecnico_tem_tabela_propria(self):
        with tempfile.TemporaryDirectory() as pasta:
            r=validar_xlsx(self.gerar(pasta,True))
            self.assertTrue(r['valido'],r['erros'])
            tecnica=next(a for a in r['abas'] if a['nome']=='DETALHES_TECNICOS')
            self.assertEqual(tecnica['tabelas'][0]['colunas'],4)

    def test_ausencia_eventos_nao_cria_tabela_sem_dados(self):
        with tempfile.TemporaryDirectory() as pasta:
            r=validar_xlsx(self.gerar(pasta,True,self.resultado(linhas=['LINESTRING(2 2,3 3)'])))
            self.assertTrue(r['valido'],r['erros'])
            vazias=[a for a in r['abas'] if a['nome'] not in ('RESUMO','PARAMETROS','DETALHAMENTO_LOCAIS')]
            self.assertTrue(all(not a['tabelas'] for a in vazias))
            self.assertTrue(all(a['filtro_planilha'] for a in vazias))

    def test_regressao_detecta_autofiltro_duplicado_sobreposto(self):
        with tempfile.TemporaryDirectory() as pasta:
            p=self.gerar(pasta)
            def mudar(root):
                ET.SubElement(root,f'{{{S}}}autoFilter',{'ref':'A1:K3'})
            r=validar_xlsx(self.adulterar(p,'xl/worksheets/sheet2.xml',mudar))
            self.assertFalse(r['valido'])
            self.assertTrue(any('sobreposto' in e for e in r['erros']))

    def test_detecta_cabecalho_xml_divergente(self):
        with tempfile.TemporaryDirectory() as pasta:
            p=self.gerar(pasta)
            def mudar(root):
                root.find(f'{{{S}}}tableColumns')[0].set('name','OUTRO')
            r=validar_xlsx(self.adulterar(p,'xl/tables/table2.xml',mudar))
            self.assertFalse(r['valido'])
            self.assertTrue(any('cabeçalho XML' in e for e in r['erros']))

    def test_detecta_contagem_de_colunas_divergente(self):
        with tempfile.TemporaryDirectory() as pasta:
            p=self.gerar(pasta)
            def mudar(root):
                root.find(f'{{{S}}}tableColumns').set('count','10')
            r=validar_xlsx(self.adulterar(p,'xl/tables/table2.xml',mudar))
            self.assertFalse(r['valido'])
            self.assertTrue(any('tableColumns' in e for e in r['erros']))

    def test_detecta_nomes_duplicados_e_filtro_fora_da_tabela(self):
        with tempfile.TemporaryDirectory() as pasta:
            p=self.gerar(pasta)
            def mudar(root):
                root.set('name','ResumoAuditoria')
                root.set('displayName','ResumoAuditoria')
                root.find(f'{{{S}}}autoFilter').set('ref','A1:J3')
            r=validar_xlsx(self.adulterar(p,'xl/tables/table2.xml',mudar))
            self.assertFalse(r['valido'])
            self.assertTrue(any('Nome de tabela' in e for e in r['erros']))
            self.assertTrue(any('filtro da tabela' in e for e in r['erros']))


if __name__=='__main__':
    unittest.main(verbosity=2)
