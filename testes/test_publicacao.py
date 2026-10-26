"""A barreira pública é complementar à revisão humana de conteúdo."""
import unittest
from ferramentas.auditar_publicacao import verificar

class PublicacaoTest(unittest.TestCase):
    def test_fonte_simples_permitida(self):self.assertEqual(verificar('scripts/exemplo.py',b'x=1\n','100644',{}),[])
    def test_dados_fora_da_politica_bloqueados(self):self.assertTrue(verificar('dados_gis/rede.shp',b'conteudo','100644',{}))
    def test_token_simulado_detectado_sem_literal_completo(self):
        dado=('ghp_'+'x'*40).encode();self.assertTrue(verificar('scripts/exemplo.py',dado,'100644',{}))
    def test_pdf_alterado_bloqueado(self):self.assertTrue(verificar('documentacao/planejamento.pdf',b'pdf','100644',{'documentacao/planejamento.pdf':'outro'}))
    def test_caminho_pessoal_simulado_detectado(self):
        dado=('C:'+ '/'+'Users/'+'usuario_teste/projeto').encode();self.assertTrue(verificar('scripts/exemplo.py',dado,'100644',{}))

if __name__=='__main__':unittest.main()
