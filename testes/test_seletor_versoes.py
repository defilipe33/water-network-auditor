"""Apresentação compacta; seleção não altera o contexto antes da confirmação."""
import unittest
from test_auditoria_fronteiras import APP
from qgis.PyQt.QtWidgets import QDialog,QLabel
from auditoria_fronteiras.seletor_versoes import SeletorVersoes


def registros(n):
    return [dict(execucao_uid=f'execucao-{i:04d}',nome='Auditoria '+str(i),projeto='Município',
        data='2026-10-25',eventos=615,locais=459,ativa=i!=1,operacao='REAGRUPAMENTO',
        origem='execucao-0000' if i else None,base='C:/projeto/resultados/auditoria.gpkg',
        agrupamento=dict(distancia=5,extensao_maxima=10)) for i in range(n)]


class SeletorVersoesTest(unittest.TestCase):
    def test_uma_tres_e_muitas_versoes_respeitam_tela(self):
        for n in (1,3,70):
            with self.subTest(n=n):
                j=SeletorVersoes(registros(n));j.show();APP.processEvents()
                self.assertEqual(j.lista.count(),n)
                self.assertLessEqual(j.width(),750)
                self.assertLessEqual(j.height(),APP.primaryScreen().availableGeometry().height())
                if n==70:
                    self.assertGreater(j.lista.verticalScrollBar().maximum(),0)
                j.close()

    def test_nomes_e_caminhos_longos_nao_alargam_janela(self):
        r=registros(1);r[0]['nome']='Nome extenso '*100;r[0]['base']='C:/'+('diretorio_muito_longo/'*45)+'auditoria.gpkg'
        j=SeletorVersoes(r);j.show();APP.processEvents()
        self.assertLessEqual(j.width(),750)
        self.assertIn(r[0]['base'],j.detalhes.toPlainText())
        self.assertEqual(j._caminhos[0][0].toolTip(),r[0]['base'])
        self.assertNotEqual(j._caminhos[0][0].text(),r[0]['base']);j.close()

    def test_selecionar_e_cancelar_sem_modificar_registros(self):
        r=registros(3);j=SeletorVersoes(r)
        j.lista.setCurrentRow(2);self.assertIs(j.selecionada(),r[2])
        j.reject();self.assertEqual(j.result(),QDialog.Rejected)
        self.assertEqual(r[2]['execucao_uid'],'execucao-0002')

    def test_confirmacao_retorna_identidade_nao_texto_formatado(self):
        r=registros(3);j=SeletorVersoes(r)
        j.lista.setCurrentRow(1);j.confirmar()
        self.assertEqual(j.result(),QDialog.Accepted)
        self.assertIs(j.selecionada(),r[1])

    def test_historicas_substituidas_e_ativas(self):
        r=registros(3);j=SeletorVersoes(r)
        texto='\n'.join(l.text() for l in j.findChildren(QLabel))
        for termo in ('HISTÓRICA','SUBSTITUÍDA','ATIVA','Busca: 5','Extensão: 10'):
            self.assertIn(termo,texto)
        j.close()

    def test_sem_registros_nao_confirma(self):
        j=SeletorVersoes([]);j.confirmar();self.assertIsNone(j.selecionada())
        self.assertEqual(j.result(),QDialog.Rejected);j.close()


if __name__=='__main__':
    unittest.main(verbosity=2)
