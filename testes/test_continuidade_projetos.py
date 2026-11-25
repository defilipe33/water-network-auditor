"""Persistência, continuidade de trabalhos e relocalização com dados sintéticos."""

from copy import deepcopy
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_grafo_gis as etapa2
from test_redes_estruturantes_gis import executar
from auditoria_aplicacao import estado_projeto as ep, manifesto_projeto as mp, persistencia_grafo_gis as pg
from auditoria_aplicacao import trabalhos_projeto as tp
from auditoria_aplicacao.contexto_trabalho import Projetos
from auditoria_aplicacao.corredores_gis import analisar
from auditoria_aplicacao.agrupamento_corredores_gis import parametros
from auditoria_fronteiras.modelos import Cancelado
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog


def foto(projeto, uid, hip='rev1', data='2026-08-11T10:00:00+00:00'):
    l=etapa2.linha
    d=executar([l('P1',(0,0),(10,0)),l('P2',(10,0),(60,0))],[('origem',[('P1',0.)])])
    d.update(projeto_uid=projeto,uuid=uid,nome='Execução '+uid,data_utc=data,
             hipotese=dict(uuid='hipotese',rev=hip,nome='Cadastro conhecido'))
    return d


class Persistencia(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.raiz=Path(temp.name)
        self.p=Projetos(self.raiz)

    def criar_topologia(self,p,uid,rev='rev1',*,arquivo=None):
        d=foto(p['uuid'],uid,rev)
        a=arquivo or self.raiz/(uid+'.gpkg')
        pg.salvar_execucao(a,d)
        return d,tp.identificar(a)[0]

    def novo_espaco(self,nome):
        r=self.raiz/nome
        r.mkdir()
        return r

    def test_novo_projeto_desde_o_inicio_e_pastas(self):
        a=self.novo_espaco('Registro')/'Registro.wna'
        p=self.p.salvar_manifesto(a,'Registro')
        self.assertTrue(a.is_file())
        self.assertEqual(mp.ler(a)['uuid'],p['uuid'])
        self.assertEqual(mp.pasta_projeto(p,'TOPOLOGIA_GIS',self.raiz),a.parent/'analises'/'conectividade')

    def test_organiza_referencia_e_atualiza_com_backup(self):
        p=self.p.criar('Registro')
        d,r=self.criar_topologia(p,'hist')
        sha=sha256(Path(r['base']).read_bytes()).hexdigest()
        self.p.vincular(r)
        antigo=deepcopy(self.p.atual())
        destino=self.raiz/'Registro.wna'
        caminho,avisos,novo=mp.organizar(antigo,destino)
        self.assertEqual((avisos,novo),([],None))
        self.p.adotar_organizado(caminho,antigo)
        adocao=deepcopy(self.p.atual())
        _,_,atualizado=mp.organizar(adocao,destino)
        self.p.atualizar_organizado(adocao,atualizado)
        self.assertEqual(self.p.atual()['uuid'],p['uuid'])
        self.assertEqual(pg.carregar(r['base'],r['uuid'],p['uuid'])['nome'],d['nome'])
        self.assertEqual(sha256(Path(r['base']).read_bytes()).hexdigest(),sha)
        self.assertEqual(len(list((self.raiz/'backups').glob('*.wna'))),2)

    def test_copia_portatil_e_sessao_nova_sem_fontes_gis(self):
        p=self.p.criar('Registro')
        d,r=self.criar_topologia(p,'old','r1')
        self.p.vincular(r)
        m=self.raiz/'complementos.gpkg'
        pg.criar_complementos(m,p['uuid'])
        origem=pg.salvar_revisao(m,p['uuid'],'ORIGEM',dict(situacao='INFORMADA',nome='Fonte declarada'))
        conexao=pg.salvar_revisao(m,p['uuid'],'CONEXAO',dict(situacao='INFORMADA',decisao='CONFIRMADA'))
        self.p.atual()['arquivo_complementos']=str(m)
        self.p.salvar()
        d=analisar(d,agrupamento=parametros('AUTOMATICO'))
        a=self.raiz/'estrutura.gpkg'
        pg.salvar_estrutura(a,d)
        self.p.vincular(tp.identificar(a)[0])
        anterior=deepcopy(self.p.atual())
        ep.guardar_trabalho(self.raiz,anterior,'ESTRUTURA_GIS',d['uuid'],visual={'categoria':'AGRUPADOS'})
        arquivo=ep.arquivo(self.raiz,anterior,ep.VISUAL)
        caminho,avisos,_=mp.organizar(anterior,self.raiz/'copiado'/'Registro.wna',True,
                                      extras=[(arquivo,ep.caminho_relativo(p,ep.VISUAL))])
        self.assertFalse(avisos)
        outra=self.raiz/'movido'
        caminho.parent.rename(outra)
        p2=Projetos(self.novo_espaco('perfil_novo'))
        salvo=p2.abrir_manifesto(outra/caminho.name)
        self.assertEqual(salvo['uuid'],p['uuid'])
        self.assertTrue(all(Path(b['base']).is_relative_to(outra) for b in salvo['bases']))
        self.assertTrue(Path(r['base']).is_file())
        ult=salvo['ultima']
        aberto=pg.carregar_estrutura(ult['base'],ult['uuid'],p['uuid'])
        self.assertEqual(aberto['agrupamento'],d['agrupamento'])
        self.assertEqual({r['uuid'] for r in pg.revisoes(salvo['arquivo_complementos'],p['uuid'])},
                         {origem['uuid'],conexao['uuid']})
        self.assertEqual(ep.ler(p2.path.parent,salvo,ep.VISUAL)['ESTRUTURA_GIS:'+d['uuid']]['categoria'],'AGRUPADOS')

    def test_manifestos_na_mesma_pasta_isolam_visualizacao_e_rascunho(self):
        a = self.p.salvar_manifesto(self.raiz/'A.wna','A')
        b = self.p.salvar_manifesto(self.raiz/'B.wna','B')
        ep.guardar_trabalho(self.raiz,a,'TOPOLOGIA_GIS','execucao',visual={'filtro':'A'})
        ep.guardar_trabalho(self.raiz,b,'TOPOLOGIA_GIS','execucao',visual={'filtro':'B'})
        self.assertEqual(ep.ler(self.raiz,a,ep.VISUAL)['TOPOLOGIA_GIS:execucao']['filtro'],'A')
        self.assertEqual(ep.ler(self.raiz,b,ep.VISUAL)['TOPOLOGIA_GIS:execucao']['filtro'],'B')
        self.assertNotEqual(ep.arquivo(self.raiz,a,ep.RASCUNHO),ep.arquivo(self.raiz,b,ep.RASCUNHO))

    def test_ausente_corrompido_relocalizado_e_uuid_divergente(self):
        p=self.p.criar('Registro')
        _,r=self.criar_topologia(p,'alvo')
        _,errado=self.criar_topologia(p,'outro')
        self.p.vincular(r)
        antigo=Path(r['base'])
        novo=self.raiz/'renomeado.gpkg'
        antigo.rename(novo)
        self.assertFalse(tp.registros(self.p.atual())[0]['disponivel'])
        with self.assertRaisesRegex(ValueError,'não contém'):
            tp.conferir(p['uuid'],r,errado['base'])
        ruim=self.raiz/'ruim.gpkg'
        ruim.write_bytes(b'arquivo incompleto')
        with self.assertRaises(sqlite3.Error):tp.conferir(p['uuid'],r,ruim)
        ok=tp.conferir(p['uuid'],r,novo)
        self.p.vincular(ok)
        self.assertEqual(Path(self.p.atual()['ultima']['base']),novo)
        self.assertEqual(self.p.atual()['ultima']['localizacoes'][0]['caminho'],str(antigo))

    def test_orfao_so_e_vinculado_por_identidade_e_ultima_preservada(self):
        p=self.p.criar('Registro')
        _,r=self.criar_topologia(p,'registrada')
        _,o=self.criar_topologia(p,'orfao')
        self.criar_topologia(dict(uuid='externo'),'outro-projeto')
        self.p.vincular(r)
        self.assertEqual([a['uuid'] for a in tp.descobrir(self.p.atual(),[self.raiz])],['orfao'])
        self.assertEqual(len(self.p.atual()['bases']),1)
        self.p.vincular(o,atualizar_ultimo=False)
        self.assertEqual(self.p.atual()['ultima']['uuid'],r['uuid'])

    def test_cancelamento_e_falha_de_copia_preservam_o_indice(self):
        p=self.p.criar('Registro')
        _,r=self.criar_topologia(p,'origem')
        self.p.vincular(r)
        antigo=deepcopy(self.p.atual())
        destino=self.raiz/'portatil'/'Registro.wna'
        with self.assertRaises(Cancelado):
            mp.organizar(antigo,destino,True,cancelar=lambda:True)
        self.assertFalse(destino.parent.exists())
        with patch('auditoria_aplicacao.manifesto_projeto.gravar',side_effect=OSError('falha de gravação')):
            with self.assertRaises(OSError):mp.organizar(antigo,destino,True)
        self.assertFalse(destino.parent.exists())
        self.assertEqual(Projetos(self.raiz).atual(),antigo)

    def test_lista_dezenas_com_metadados_sem_ler_fotos(self):
        p=self.p.criar('Registro')
        p['bases']=[dict(uuid=str(i),base=str(self.raiz/(str(i)+'.gpkg')),
                         tipo='TOPOLOGIA_GIS',nome='Trabalho',hipotese_uid='hipotese',
                         hipotese_rev='rev'+str(i//20),data=f'2026-08-10T{i//3:02}:00:00') for i in range(60)]
        p['bases'].append(dict(p['bases'][0]))
        with patch('auditoria_aplicacao.trabalhos_projeto.identificar',side_effect=AssertionError('Leu GeoPackage')):
            rs=tp.registros(p)
        self.assertEqual(len(rs),60)
        self.assertEqual({r['hipotese_rev'] for r in rs},{'rev0','rev1','rev2'})
        self.assertGreater(rs[0]['data'],rs[-1]['data'])
        p['bases'][-1]['base']=str(self.raiz/'duplicado.gpkg')
        self.assertTrue(any('dois caminhos' in r.get('erro','') for r in tp.registros(p)))

    def test_legacy_proveniencia_disponivel_sem_regravar_foto(self):
        p=self.p.criar('Registro')
        d,r=self.criar_topologia(p,'legado')
        with closing(sqlite3.connect(r['base'])) as con, con:
            con.execute('DROP TABLE TG_RESUMO')
            con.execute("DELETE FROM gpkg_contents WHERE table_name='TG_RESUMO'")
        bytes_antes=Path(r['base']).read_bytes()
        self.assertNotIn('hipotese_uid',tp.identificar(r['base'])[0])
        self.assertEqual(tp.metadados(p['uuid'],r,legado=True)['hipotese_rev'],'rev1')
        self.assertEqual(pg.carregar(r['base'],r['uuid'],p['uuid'])['uuid'],d['uuid'])
        self.assertEqual(Path(r['base']).read_bytes(),bytes_antes)


class Interface(unittest.TestCase):
    def setUp(self):
        self.f=etapa2.InterfaceGIS()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.c,self.t=self.f.c,self.f.t
        self.esperar=self.f.f.aguardar

    def test_retoma_filtros_e_selecao_da_execucao_sem_recalcular(self):
        t,c=self.t,self.c
        t._gravar_hipotese('Conhecida')
        self.esperar()
        primeira=t._hip_ativa
        t.iniciar(modo='salva')
        self.esperar()
        r=c.projetos.atual()['ultima']
        a=t.dados['componentes'][0]['uid']
        t.busca.setText(a)
        t.mudar_resultados()
        t.ordenar_resultados(2)
        c.show()
        c.salvar_estado_atual()
        t._gravar_hipotese('Atualizada',primeira)
        self.esperar()
        with patch('auditoria_aplicacao.topologia_gis_ui.executar',side_effect=AssertionError('Recalculou')):
            c.continuar_trabalho()
            self.esperar()
        self.assertEqual(t.dados['uuid'],r['uuid'])
        self.assertEqual(t._hip_ativa['rev'],primeira['rev'])
        self.assertEqual(t.busca.text(),a)
        self.assertEqual(t._ordem_coluna,(2,False))
        self.assertEqual(t._selecionado()['uid'],a)

    def test_rascunho_salvo_separadamente(self):
        t=self.t
        parametro=t.limite.value()
        t.limite.setValue(parametro+17)
        self.assertTrue(t.guardar_rascunho())
        t.limite.setValue(parametro)
        t.recuperar_rascunho()
        self.assertEqual(t.limite.value(),parametro+17)
        self.assertFalse(self.c.projetos.atual()['bases'])
        t.limite.setValue(parametro)

    def test_novo_projeto_ui_gera_manifesto(self):
        pasta=self.c.app.catalogo.raiz
        with patch.object(QInputDialog,'getText',return_value=('Registro',True)),\
             patch.object(QFileDialog,'getExistingDirectory',return_value=str(pasta)):
            self.c.novo_manifesto()
        p=self.c.projetos.atual()
        self.assertEqual(p['nome'],'Registro')
        self.assertEqual(Path(p['manifesto_wna']),Path(pasta)/'Registro'/'Registro.wna')
        self.assertTrue(self.c.detalhe_localizacao().startswith(p['manifesto_wna']))
