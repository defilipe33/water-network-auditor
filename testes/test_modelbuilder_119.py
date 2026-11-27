"""Materialização ModelBuilder, reconciliação e prioridade de cruzamentos."""

import csv
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from qgis.core import QgsGeometry
from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog

import test_grafo_gis as gis
from test_consolidacao_1182 import catalogo_sintetico
from test_redes_estruturantes_gis import executar

from auditoria_aplicacao import cadastro_exportavel as cadastro
from auditoria_aplicacao import conjuntos_modelagem as cm
from auditoria_aplicacao import modelbuilder_conferencia as conf
from auditoria_aplicacao import modelbuilder_gis as mb
from auditoria_aplicacao import persistencia_grafo_gis as pg
from auditoria_aplicacao import prioridade_cruzamentos as pc
from auditoria_aplicacao.duplicatas_conexoes_gis import auditar

def perfil(**extra):
    return dict(versao=mb.VERSAO,nome='Perfil sintético',destino='2026',modo='NOVO',campos={},
                tipos=['PIPE','JUNCTION'],**extra)


def cruzar(aproximado=False,mesmo=False):
    ts=[gis.linha('a',(-5,0),(5,0)),gis.linha('b',(0,-.05 if aproximado else -5),(0,5))]
    if mesmo:
        ts.append(gis.linha('c',(5,0),(0,5)))
    return ts,gis.construir(ts,origens=[dict(uuid='fonte',portas=[['a',0.]])])


class Cruzamentos(unittest.TestCase):
    def test_prioriza_fora_do_componente_e_reduce_revisao_interna(self):
        _,r=cruzar(mesmo=True)
        c=next(x for x in r['diagnosticos'] if x['tipo']=='CRUZAMENTO')
        self.assertEqual(c['prioridade_cruzamento']['nivel'],'BAIXA')
        self.assertEqual(c['situacao'],'CANDIDATA')
        self.assertFalse(pc.atende(c['prioridade_cruzamento'],'PRIORITARIOS'))
        self.assertTrue(pc.atende(c['prioridade_cruzamento'],'TODOS'))
        _,r=cruzar()
        c=next(x for x in r['diagnosticos'] if x['tipo']=='CRUZAMENTO')
        self.assertEqual(c['prioridade_cruzamento']['nivel'],'ALTA')
        self.assertEqual(len(r['componentes']),2)
        self.assertEqual(len(r['arestas']),2)

    def test_reclassifica_sem_mutar_o_grafo_e_identifica_t_sem_mesclar(self):
        ts,r=cruzar(aproximado=True)
        c=next(x for x in r['diagnosticos'] if x['tipo']=='CRUZAMENTO')
        t=next(x for x in r['diagnosticos'] if x['tipo']=='CONEXAO_T')
        p=c['prioridade_cruzamento']
        self.assertEqual(p['referencia_t'],t['uid'])
        self.assertTrue(p['ponta'])
        self.assertFalse(pc.atende(p,'PRIORITARIOS'))
        self.assertTrue(pc.atende(p,'PONTAS'))
        d=deepcopy(r)
        self.assertFalse(pc.classificar(r,.001)[c['uid']]['ponta'])
        self.assertEqual(d,r)
        pares,_=auditar(r['diagnosticos'],[],{t['uid']:t for t in ts})
        self.assertIn('RELACIONADA_T',{a['tipo'] for a in pares})

    def test_veredito_separada_permanece_e_confirmacao_aplica(self):
        ts,a=cruzar()
        c=next(x for x in a['diagnosticos'] if x['tipo']=='CRUZAMENTO')
        d=dict(uuid='r',rev='r1',portas=c['portas'],candidato=c['uid'],decisao='SEPARADA')
        r=gis.construir(ts,conexoes=[d])
        self.assertEqual(len(r['componentes']),2)
        self.assertEqual(next(x for x in r['diagnosticos'] if x['uid']==c['uid'])['situacao'],'SEPARADA')
        r=gis.construir(ts,conexoes=[dict(d,decisao='CONFIRMADA')])
        self.assertEqual(len(r['componentes']),1)
        self.assertEqual(len(r['arestas']),4)


class Pacote(unittest.TestCase):
    def setUp(self):
        self.foto,self.inv=catalogo_sintetico()
        self.previa=cadastro.preparar(self.foto,self.inv,modo_atividade='FORA_INATIVO')

    def exportar(self,pasta,fmt='GPKG',config=None,**kw):
        return cadastro.exportar(self.previa,pasta,fmt,modelbuilder=config or dict(perfil=perfil(),escopo='COMPLETO'),**kw)

    def test_tres_formatos_start_stop_divisao_e_identidades_brutas(self):
        with TemporaryDirectory() as pasta:
            for fmt in ('GPKG','ESRI Shapefile','CSV'):
                dst=self.exportar(pasta,fmt)
                m,rs=mb.ler_pacote(dst)
                ps=[r for r in rs if r['tipo']=='PIPE']
                self.assertEqual(len(ps),5)
                self.assertEqual(len({r['label'] for r in rs}),len(rs))
                partes=sorted((p for p in ps if p['orig_uid']=='a'),key=lambda p:p['inicio'])
                self.assertEqual(partes[0]['no_b'],partes[1]['no_a'])
                self.assertEqual(partes[0]['gis_id'],'0')
                self.assertIsNone(next(p for p in ps if p['orig_uid']=='fora')['gis_id'])
                self.assertFalse(m['aceita_exclusao'])
                self.assertTrue((dst/'MINUTA_ATIVIDADE_INATIVO_001.txt').exists())
                with (dst/'pipes.csv').open(encoding='utf-8-sig',newline='') as a:
                    csv_pipes=list(csv.DictReader(a))
                self.assertTrue(all(p['mb_inicio'] and p['mb_fim'] for p in csv_pipes))
                if fmt=='ESRI Shapefile':
                    self.assertTrue(all((dst/('pipes'+x)).is_file() for x in ('.shp','.shx','.dbf','.prj','.cpg')))
                if fmt=='CSV':
                    self.assertTrue(csv_pipes[0]['mb_wkt'].startswith('LineString'))
                self.assertTrue(m['pendencias'])

    def test_equipamentos_exigem_atributos_e_no_declarado(self):
        p=self.previa['pipes'][0]
        n=next(n for n in self.previa['nos'] if n['uid']==p['no_a'])
        u='equipamento'
        g=QgsGeometry.fromWkt(f"POINT({n['xy'][0]} {n['xy'][1]})")
        a=dict(uid=u,categoria='RESERVOIR',feicao='original',id='01',wkb=bytes(g.asWkb()).hex(),
            atributos_originais={'carga':197},declaracoes=[dict(portas=[[p['parte'],p['inicio']]])])
        self.previa['equipamentos']=[a,dict(a,uid='bomba',categoria='PUMP')]
        self.previa['cadastro']+=self.previa['equipamentos']
        pe=perfil()
        pe.update(tipos=['PIPE','JUNCTION','RESERVOIR'],campos={'RESERVOIR':{'mb_carga':{'campo':'carga','unidade':'m'}}})
        with TemporaryDirectory() as pasta:
            dst=self.exportar(pasta,'ESRI Shapefile',dict(perfil=pe,escopo='COMPLETO'))
            m,rs=mb.ler_pacote(dst)
            self.assertEqual(m['quantidades']['RESERVOIR'],1)
            self.assertTrue((dst/'reservoirs.shp').is_file())
            self.assertEqual(next(r for r in rs if r['tipo']=='RESERVOIR')['uid'],n['uid'])
            pe['campos']={}
            dst=self.exportar(pasta,'CSV',dict(perfil=pe,escopo='COMPLETO'))
            self.assertNotIn('RESERVOIR',mb.ler_pacote(dst)[0]['quantidades'])
            self.assertIn('bomba',(dst/'WNA_EQUIPAMENTOS_INVENTARIO.csv').read_text(encoding='utf-8-sig'))

    def test_conferencia_exige_endpoints_e_nao_persiste_duplicatas(self):
        with TemporaryDirectory() as pasta:
            d=self.exportar(pasta,'CSV')
            m,rs=mb.ler_pacote(d)
            ids={r['uid']:str(i+100) for i,r in enumerate(rs)}
            prova=[]
            for r in rs:
                b={k:str(r[k]) if r.get(k) is not None else '' for k in mb.COLUNAS_EVIDENCIA}
                b.update(id_modelo=ids[r['uid']],no_a=ids.get(r.get('no_a'),''),no_b=ids.get(r.get('no_b'),''))
                prova.append(b)
            f=d/'observados.csv'
            with f.open('w',encoding='utf-8',newline='') as arq:
                w=csv.DictWriter(arq,mb.COLUNAS_EVIDENCIA)
                w.writeheader()
                w.writerows(prova)
            v=conf.ler_evidencia(f)
            r=conf.conferir(m,rs,v,'piloto','26',cenario='Teste')
            self.assertEqual(r['estado'],'IMPORTADO_E_CONFERIDO')
            p=next(x for x in v if x['tipo']=='PIPE')
            p['no_a'],p['no_b']=p['no_b'],p['no_a']
            v.append(dict(v[0],id_modelo='999'))
            r=conf.conferir(m,rs,v,'piloto','26',cenario='Teste')
            self.assertEqual(r['estado'],'IMPORTADO_COM_PENDENCIAS')
            self.assertNotIn(p['uid'],{x['uid'] for x in r['correspondencias']})
            gp=d/'correspondencias.gpkg'
            conf.salvar_tabela(gp,r,f,'2026-11-26')
            with closing(sqlite3.connect(gp)) as c:
                self.assertEqual(c.execute('SELECT count(*) FROM WNA_ELEMENTO_WATERGEMS').fetchone(),
                                 (len(r['correspondencias']),))

    def test_atualizacao_dividida_sem_exclusao_e_escopo_estrito(self):
        foto=executar(self.inv[0][:3],[('A',[('a',0.)])])
        foto['uuid']='primeira'
        p0=cadastro.preparar(foto,self.inv)
        with TemporaryDirectory() as pasta:
            ant=cadastro.exportar(p0,pasta,'CSV',modelbuilder=dict(perfil=perfil(),escopo='COMPLETO'))
            meta,linhas=mb.ler_pacote(ant)
            pe=dict(perfil(),modo='ATUALIZAR',modelo_destino='piloto')
            d=self.exportar(pasta,'CSV',dict(perfil=pe,escopo='COMPLETO',componentes_anteriores=linhas,
                referencia_anterior=meta['assinatura_csv']))
            texto=(d/'WNA_PLANO_ATUALIZACAO.csv').read_text(encoding='utf-8-sig')
            self.assertIn('DIVISAO_SUBSTITUICAO_MANUAL',texto)
            self.assertNotIn('EXCLUIR',texto)
            a=next(r for r in self.previa['pipes'] if r['parte']=='a')
            sel={('PIPE',a['uid'])}
            c=dict(cm.compor(self.previa,sel,nome='Setor',categoria='AREAS',origem='MANUAL'),uuid='setor')
            d=self.exportar(pasta,'CSV',dict(perfil=perfil(),escopo='CONJUNTOS'),selecoes=[c],escopo=sel)
            self.assertEqual(mb.ler_pacote(d)[0]['quantidades'],{'JUNCTION':2,'PIPE':1})

    def test_tank_invalido_e_tipos_do_modelo_preservados_no_plano(self):
        p=self.previa['pipes'][0]
        n=next(n for n in self.previa['nos'] if n['uid']==p['no_a'])
        g=QgsGeometry.fromWkt(f"POINT({n['xy'][0]} {n['xy'][1]})")
        a=dict(uid='tanque',categoria='TANK',feicao='tn',id='00',wkb=bytes(g.asWkb()).hex(),
               atributos_originais={'z':100,'nmin':0,'nini':1,'nmax':3,'d':150},
               declaracoes=[dict(portas=[[p['parte'],p['inicio']]])])
        self.previa['equipamentos']=[a]
        self.previa['cadastro'].append(a)
        pe=perfil()
        pe.update(tipos=['PIPE','JUNCTION','TANK'],
                  campos={'TANK':{k:dict(campo=v,unidade='cm' if k=='mb_diam' else 'm')
                            for k,v in zip(mb.PROPRIEDADES['TANK'],('z','nmin','nini','nmax','d'))}})
        pipes,nos,_,asos=cm.preparar_exportacao(self.previa,[])
        _,tipos,esperado,_,_=mb.preparar(self.previa,pipes,nos,asos,dict(perfil=pe,escopo='COMPLETO'))
        self.assertEqual(tipos['TANK'][0]['mb_diam'],1.5)
        item=next(x for x in esperado if x['tipo']=='PIPE')
        observados=[dict(uid=item['uid'],id_modelo='47',label='Renomeado',tipo='PIPE'),
                    dict(uid='',id_modelo='99',label='Outro',tipo='PIPE')]
        plano=conf.plano_atualizacao(esperado,esperado,observado=observados)
        self.assertTrue(any(x['acao']=='PRESERVAR_SOMENTE_NO_DESTINO' for x in plano))
        self.assertEqual(next(x for x in plano if x['uid']==item['uid'])['id_modelo'],'47')
        a['atributos_originais']['nini']=4
        _,tipos,_,pend,_=mb.preparar(self.previa,pipes,nos,asos,dict(perfil=pe,escopo='COMPLETO'))
        self.assertFalse(tipos['TANK'])
        self.assertTrue(any(r['uid']=='tanque' for r in pend))

    def test_perfil_e_exportacao_sao_revisoes_do_projeto(self):
        with TemporaryDirectory() as pasta:
            a=Path(pasta)/'complementos.gpkg'
            p=self.foto['projeto_uid']
            pg.criar_complementos(a,p)
            r=pg.salvar_revisao(a,p,'MODELBUILDER_PERFIL',perfil())
            self.assertEqual(pg.revisoes(a,p,r['uuid']),[r])
            d=self.exportar(pasta,'CSV')
            m,rs=mb.ler_pacote(d)
            e=pg.salvar_revisao(a,p,'MODELBUILDER_EXPORTACAO',dict(projeto_uid=p,topologia_uid=m['execucao'],
                pasta=str(d),assinatura=m['assinatura_csv'],estado=m['estado']))
            self.assertEqual(pg.revisoes(a,p,e['uuid']),[e])
            with (d/'WNA_TOPOLOGIA_ESPERADA.csv').open('a',encoding='utf-8') as f:
                f.write('modificado\n')
            with self.assertRaises(ValueError):
                mb.ler_pacote(d)


class Interface(unittest.TestCase):
    def test_assistente_abre_salva_perfil_e_pacote_reaparece_no_historico(self):
        from auditoria_aplicacao.modelbuilder_ui import AssistenteModelBuilder
        f=gis.InterfaceGIS()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.t.iniciar()
        f.f.aguardar()
        self.assertTrue(f.c.abrir_estrutura(foto=f.t.dados))
        p=f.c.estrutura_gis
        with patch.object(QInputDialog,'getItem',return_value=('Manter atividade a definir',True)):
            p.prever_cadastro_completo(abrir_modelbuilder=True)
        f.f.aguardar()
        d=p.findChild(AssistenteModelBuilder)
        self.assertIsNotNone(d,p.status.text())
        self.assertEqual(d.escopo.currentData(),'COMPLETO')
        d.escopo.setCurrentIndex(d.escopo.findData('AREAS'))
        with self.assertRaisesRegex(ValueError,'Escolha os elementos'):
            d.proximo()
        d.escopo.setCurrentIndex(d.escopo.findData('COMPLETO'))
        d.proximo()
        d.nome.setText('Perfil de regressão')
        d._salvar_perfil()
        d.nome.clear()
        d._aplicar_perfil()
        self.assertEqual(d.nome.text(),'Perfil de regressão')
        d.voltar_b.click()
        self.assertEqual(d.tabs.currentIndex(),0)
        for _ in range(3):d.proximo()
        self.assertEqual(d.tabs.currentIndex(),3)
        d.validar()
        f.f.aguardar()
        self.assertIsNotNone(d._validado,d.status.text())
        with TemporaryDirectory() as destino:
            with patch.object(QFileDialog,'getExistingDirectory',return_value=destino):
                d.exportar()
            f.f.aguardar()
            d.reject()
            p.abrir_historico_modelbuilder()
            h=p._historico_modelbuilder
            self.assertEqual(len(h.registros),1,p.status.text())
            self.assertTrue(next(Path(destino).glob('*/pipes.shp')).is_file())
            h.reject()
