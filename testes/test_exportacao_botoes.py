"""Regressão clicked(bool): exportações reais com entradas exclusivamente sintéticas."""
import json,sqlite3,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import test_interface_fronteiras as fixture
from test_auditoria_fronteiras import APP
from qgis.PyQt import sip
from qgis.PyQt.QtWidgets import QDialog,QCheckBox,QPushButton
from qgis.core import QgsVectorLayer
from auditoria_fronteiras.atividade import sistema,acompanhada
from validar_estrutura_xlsx import validar_xlsx


class ExportacaoBotoesTest(unittest.TestCase):
    setUp=fixture.InterfaceTest.setUp
    tearDown=fixture.InterfaceTest.tearDown
    marcar=fixture.InterfaceTest.marcar
    configurar=fixture.InterfaceTest.configurar

    def preparar(self):
        self.configurar();self.janela.executar.click()
        self.assertIsNotNone(self.janela.dossie)
        self.assertTrue(self.janela.exportar_geo.isEnabled())

    def clicar(self,botao):
        erros=[]
        with patch.object(sys,'excepthook',side_effect=lambda *e:erros.append(e)):
            botao.click();APP.processEvents()
        self.assertEqual(erros,[],str(erros))

    def exportar(self,pasta,formatos):
        def escolher(d):
            for w in d.findChildren(QCheckBox):w.setChecked(w.text() in formatos)
            return QDialog.Accepted
        with patch.object(QDialog,'exec',escolher),patch('auditoria_fronteiras.interface.QFileDialog.getExistingDirectory',return_value=str(pasta)):
            self.clicar(self.janela.exportar_geo)

    def validar(self,pasta,formatos):
        destinos=list(Path(pasta).glob('AUDITORIA_*'));self.assertEqual(len(destinos),1)
        p=destinos[0];d=self.janela.dossie
        if 'GPKG' in formatos:
            from auditoria_fronteiras.exportacao import validar_gpkg
            validar_gpkg(p/'AUDITORIA_FRONTEIRAS.gpkg',d)
        if 'SHP' in formatos:
            for nome,chave in [('EVENTOS_FRONTEIRAS','eventos'),('PONTOS_INVESTIGACAO','locais')]:
                for ext in ('.shp','.shx','.dbf','.prj','.cpg'):self.assertTrue((p/'SHP'/ (nome+ext)).is_file())
                c=QgsVectorLayer(str(p/'SHP'/(nome+'.shp')),nome,'ogr')
                self.assertTrue(c.isValid());self.assertEqual(c.featureCount(),len(d[chave]));self.assertEqual(c.crs().authid(),self.janela.resultado.parametros.crs)
                self.assertTrue(all(len(f.name())<=10 for f in c.fields()));sip.delete(c)
        if 'XLSX' in formatos:self.assertTrue(validar_xlsx(p/'AUDITORIA_FRONTEIRAS.xlsx')['valido'])
        self.assertEqual(sistema(self.janela).ultima.estado,'CONCLUIDO')
        self.assertFalse(sistema(self.janela).em_execucao())

    def ensaio(self,formatos):
        self.preparar()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as p:self.exportar(p,formatos);self.validar(p,formatos)
    def test_gpkg(self):self.ensaio(['GPKG'])
    def test_shp(self):self.ensaio(['SHP'])
    def test_xlsx(self):self.ensaio(['XLSX'])
    def test_tres_formatos(self):self.ensaio(['GPKG','SHP','XLSX'])
    def test_excel_independente(self):
        self.preparar()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as p:
            alvo=Path(p)/'relatorio.xlsx'
            with patch('auditoria_fronteiras.interface.QFileDialog.getSaveFileName',return_value=(str(alvo),'')):self.clicar(self.janela.exportar)
            self.assertTrue(validar_xlsx(alvo)['valido']);self.assertEqual(sistema(self.janela).ultima.estado,'CONCLUIDO')
    def test_cancelar_formatos(self):
        self.preparar()
        with patch.object(QDialog,'exec',return_value=QDialog.Rejected):self.clicar(self.janela.exportar_geo)
        self.assertEqual(sistema(self.janela).ultima.estado,'CANCELADO')
    def test_cancelar_destino(self):
        self.preparar()
        self.exportar('',['GPKG'])
        self.assertEqual(sistema(self.janela).ultima.estado,'CANCELADO')
    def test_cancelar_excel(self):
        self.preparar()
        with patch('auditoria_fronteiras.interface.QFileDialog.getSaveFileName',return_value=('','')):self.clicar(self.janela.exportar)
        self.assertEqual(sistema(self.janela).ultima.estado,'CANCELADO')
    def test_permissao_e_repeticao(self):
        self.preparar()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as p:
            with patch('auditoria_fronteiras.persistencia.exportar_gpkg',side_effect=PermissionError('Destino sem permissão')):self.exportar(p,['GPKG'])
            self.assertEqual(sistema(self.janela).ultima.estado,'ERRO');self.assertFalse(sistema(self.janela).em_execucao())
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as p:self.exportar(p,['GPKG']);self.validar(p,['GPKG'])
    def test_apos_reabertura(self):
        self.preparar()
        from auditoria_fronteiras.persistencia import exportar_gpkg
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as p:
            base=Path(p)/'origem.gpkg';d=exportar_gpkg(base,self.janela.dossie)
            self.janela.abrir_auditoria(str(base),d['execucao_uid'])
            saida=Path(p)/'saida';saida.mkdir();self.exportar(saida,['GPKG','SHP','XLSX']);self.validar(saida,['GPKG','SHP','XLSX'])
    def test_decorador_preserva_argumentos_reais(self):
        @acompanhada('Contrato')
        def f(w,indice,texto,objeto=None):return indice,texto,objeto
        objeto=object();self.assertEqual(f(self.janela,3,'texto',objeto=objeto),(3,'texto',objeto))


if __name__=='__main__':unittest.main()
