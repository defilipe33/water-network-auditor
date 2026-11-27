"""Regressões de correção guiada, integridade multielemento e destino."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from qgis.core import QgsGeometry

import test_grafo_gis as gis
from test_modelbuilder_119 import perfil
from test_modelbuilder_1191 import linhas
from test_redes_estruturantes_gis import executar
from auditoria_aplicacao import cadastro_exportavel as cadastro
from auditoria_aplicacao import conjuntos_modelagem as cm
from auditoria_aplicacao import correcao_modelbuilder as correcao
from auditoria_aplicacao import destino_modelbuilder as destino
from auditoria_aplicacao import modelbuilder_gis as mb
from auditoria_aplicacao import persistencia_grafo_gis as pg


class Equipamentos(unittest.TestCase):
    def setUp(self):
        self.ts=[gis.linha('a',(0,0),(20,0)),gis.linha('b',(20,0),(40,0)),gis.linha('c',(80,0),(90,0))]
        for t in self.ts:
            u=t['uid']
            t.update(id=u.upper(),feicao=u,fontes=['redes'],camada='Rede de ensaio',
                categoria='PIPE',atributos_originais={'id':u.upper()})
        self.foto=executar(self.ts,[],[])
        self.eqs=[]
        self.areas=[]
        self.cfg=dict(perfil=perfil(),escopo='COMPLETO')

    def equipamento(self,tipo,x,*,portas=(),receptor=None,**atributos):
        from auditoria_fronteiras.entradas import digest
        uid=digest(['eq',tipo,x])
        g=QgsGeometry.fromWkt(f'POINT({x} 0)')
        e=dict(uid=uid,feicao=uid+'_1',categoria=tipo,id='ID-'+tipo,label='EQ-'+tipo,
               wkb=bytes(g.asWkb()).hex(),atributos_originais=atributos,declaracoes=[dict(
               uuid='d'+uid,portas=portas,posicao='INTERMEDIARIA' if receptor else 'INICIO',
               tubos_uid=[receptor] if receptor else [])])
        self.eqs.append(e)
        if tipo in mb.PROPRIEDADES:
            self.cfg['perfil']['tipos'].append(tipo)
            self.cfg['perfil']['campos'][tipo]={k:dict(campo=k,unidade=prop[1]) for k,prop in mb.PROPRIEDADES[tipo].items()}
        return e

    def previa(self):
        return cadastro.preparar(self.foto,(self.ts,[],self.eqs,self.areas,[]),atividades={'c':'INATIVO'})

    def test_tipagem_direcional_e_labels_em_csv_shp_e_gpkg(self):
        import osgeo.ogr as ogr
        for tipo in ('PRV','PSV','TCV','FCV','PBV','PUMP'):
            with self.subTest(tipo=tipo), TemporaryDirectory() as t:
                self.eqs=[]
                self.cfg['perfil']=perfil()
                self.equipamento(tipo,20,portas=[['b',0.]],mb_cota=86.,mb_ajuste=5.,mb_def='Curva ensaio',
                                 mb_mont='A',mb_jus='B',mb_estado='ABERTO')
                p=self.previa()
                for fmt in ('CSV','GPKG','ESRI Shapefile') if tipo=='PRV' else ('CSV',):
                    d=cadastro.exportar(p,t,fmt,modelbuilder=self.cfg)
                    meta,rs=mb.ler_pacote(d)
                    eq=next(r for r in rs if r['tipo']==tipo)
                    tubos=linhas(d,'pipes.csv')
                    a=next(r for r in tubos if r['gis_id']=='A')
                    b=next(r for r in tubos if r['gis_id']=='B')
                    self.assertEqual((a['label_no_B'],a['no_b'],a['mb_tipo_b']),(eq['label'],eq['uid'],tipo))
                    self.assertEqual((b['label_no_A'],b['no_a'],b['mb_tipo_a']),(eq['label'],eq['uid'],tipo))
                    self.assertEqual((a['label_no_B'],b['label_no_A']),(a['mb_fim'],b['mb_inicio']))
                    self.assertFalse(any(r['tipo']=='JUNCTION' and r['uid']==eq['uid'] for r in rs))
                    dado=linhas(d,mb.CAMADAS[tipo]+'.csv')[0]
                    self.assertEqual((dado['mb_mont'],dado['mb_jus']),(a['WNA_LABEL'],b['WNA_LABEL']))
                    self.assertEqual(meta['validacao_nativa'],'PENDENTE_NO_WATERGEMS')
                    self.assertEqual(next(r for r in tubos if r['gis_id']=='C')['atividade'],'INATIVO')
                    if fmt!='CSV':
                        ds=ogr.Open(str(d/('pipes.shp' if fmt=='ESRI Shapefile' else 'cadastro_modelagem.gpkg')))
                        camada=ds.GetLayerByName('pipes')
                        f=camada.GetNextFeature()
                        self.assertTrue(f.GetField('label_no_A'))
                        self.assertTrue(f.GetField('label_no_B'))
                        f=camada=None
                        ds.Destroy()

    def test_hidrante_ventosa_e_registro_associado_com_areas(self):
        self.equipamento('HYDRANT',0,portas=[['a',0.]],mb_cota=89.)
        self.equipamento('AIR_VALVE',20,portas=[['a',1.]],mb_cota=91.)
        self.equipamento('REGISTRO',10,mb_pipe='A',mb_estado='FECHADO')
        self.equipamento('BOOSTER',100)
        g=QgsGeometry.fromWkt('POLYGON((0 0,1 0,1 1,0 0))')
        self.areas.append(dict(uid='zona',feicao='zona',categoria='SETOR',id='ZA',wkb=bytes(g.asWkb()).hex()))
        with TemporaryDirectory() as t:
            d=cadastro.exportar(self.previa(),t,'ESRI Shapefile',modelbuilder=self.cfg)
            m,_=mb.ler_pacote(d)
            p=linhas(d,'pipes.csv')
            self.assertEqual(len(p),3)
            self.assertEqual(m['quantidades'],dict(HYDRANT=1,AIR_VALVE=1,REGISTRO=1,JUNCTION=3,PIPE=3))
            r=linhas(d,'isolation_valves.csv')[0]
            self.assertEqual(r['posicao_pipe'],'0.5')
            self.assertEqual(r['mb_pipe'],next(a['WNA_LABEL'] for a in p if a['gis_id']=='A'))
            for n in ('hydrants','air_valves','isolation_valves','inventario_booster','referencia_setor'):
                self.assertTrue((d/(n+'.shp')).is_file())
            c={r['tipo']:r for r in m['cobertura']}
            self.assertEqual((c['BOOSTER']['cadastrados'],c['BOOSTER']['exportados']),(1,0))

    def test_orientacao_conflitante_nao_substitui_equipamento_por_junction(self):
        self.equipamento('TCV',20,portas=[['a',1.]],mb_cota=90.,mb_ajuste=5.,
                        mb_mont='A',mb_jus='A',mb_estado='ABERTO')
        r,m=cadastro.validar_modelbuilder(self.previa(),self.cfg)
        self.assertIn('EQUIPAMENTO_NO_NAO_PREPARADO',{p.get('codigo') for p in r})
        self.assertEqual(m['quantidades']['PIPE'],1)
        self.assertEqual(m['estado'],'EXPORTACAO_PARCIAL')
        self.assertNotIn('TCV',m['quantidades'])

    def test_insercao_declarada_remapeia_selection_set_sem_mudar_pipe(self):
        e=self.equipamento('PRV',10,receptor='a',mb_cota=86.,mb_ajuste=8.,
                          mb_mont='PORTA_B',mb_jus='PORTA_A',mb_estado='ATIVO')
        p=self.previa()
        a=next(r for r in p['pipes'] if r['parte']=='a')
        chaves={('PIPE',a['uid']),('EQUIPAMENTO',e['uid'])}
        s=dict(cm.compor(p,chaves,nome='Trecho e equipamento',categoria='PERSONALIZADOS',origem='MANUAL'),uuid='teste')
        anterior=deepcopy(p['pipes'])
        with TemporaryDirectory() as t:
            d=cadastro.exportar(p,t,'CSV',selecoes=[s],modelbuilder=self.cfg)
            m,_=mb.ler_pacote(d)
            a1,a2=sorted((r for r in linhas(d,'pipes.csv') if r['parte']=='a'),key=lambda r:r['inicio'])
            self.assertEqual(sum(float(r['comprimento_m']) for r in (a1,a2)),20.)
            self.assertEqual(a1['no_b'],a2['no_a'])
            self.assertEqual(a1['label_no_B'],a2['label_no_A'])
            eq=linhas(d,'prvs.csv')[0]
            self.assertEqual((eq['mb_jus'],eq['mb_mont']),(a1['WNA_LABEL'],a2['WNA_LABEL']))
            assoc=linhas(d,'WNA_ELEMENTO_CONJUNTO.csv')
            self.assertEqual({r['elemento_uid'] for r in assoc},{a1['WNA_UID'],a2['WNA_UID'],eq['WNA_UID']})
            self.assertEqual(m['segmentos_substituidos'],[a['uid']])
            self.assertEqual(p['pipes'],anterior)
            d=cadastro.exportar(p,t,'GPKG',selecoes=[s],somente_conjuntos=True)
            aux=linhas(d,'WNA_ELEMENTO_CONJUNTO.csv')
            self.assertTrue(any(r['situacao_participacao']=='SOMENTE_INVENTARIO' for r in aux))

    def test_booster_com_composicao_referencia_bomba_preparada(self):
        self.equipamento('PUMP',20,portas=[['a',1.]],mb_cota=90.,mb_def='Definição teste',
                       mb_mont='A',mb_jus='B',mb_estado='ABERTO')
        e=self.equipamento('BOOSTER',44)
        p=self.previa()
        por_tubo={x['parte']:x['uid'] for x in p['pipes']}
        u=next(n['uid'] for n in p['nos'] if ['a',1.] in list(map(list,n['portas'])))
        a,b=por_tubo['a'],por_tubo['b']
        e['atributos_originais']['composicao']=dict(bombas=[u],pipes=[a,b],succao=a,recalque=b)
        _,m=cadastro.validar_modelbuilder(self.previa(),self.cfg)
        self.assertEqual(m['composicoes_booster'][0]['situacao'],'COMPONENTES_REFERENCIADOS')
        self.assertNotIn('BOOSTER',m['quantidades'])
        e['atributos_originais']['composicao']['recalque']='referencia-ausente'
        pend,m=cadastro.validar_modelbuilder(self.previa(),self.cfg)
        self.assertEqual(m['composicoes_booster'][0]['situacao'],'COMPOSICAO_PENDENTE')
        self.assertIn('COMPOSICAO_PENDENTE',{r.get('codigo') for r in pend})

    def test_equipamentos_conflitantes_na_mesma_posicao_persistem_no_inventario(self):
        self.equipamento('HYDRANT',20,portas=[['a',1.]],mb_cota=89.)
        self.equipamento('AIR_VALVE',20,portas=[['a',1.]],mb_cota=91.)
        r,m=cadastro.validar_modelbuilder(self.previa(),self.cfg)
        self.assertEqual(sum(x.get('codigo')=='EQUIPAMENTOS_NO_CONFLITANTES' for x in r),2)
        self.assertEqual(m['quantidades']['PIPE'],1)
        self.assertNotIn('HYDRANT',m['quantidades'])

    def test_cinco_pendencias_equivalentes_separam_os_tres_e_os_dois_casos(self):
        linhas_gis=[gis.linha(f'p{i}',(i*5,0),(i*5+2,0)) for i in range(5)]
        for t in linhas_gis:
            t.update(id=t['uid'],feicao=t['uid'],fontes=['fonte'],categoria='PIPE')
        f=executar(linhas_gis,[],[])
        p=cadastro.preparar(f,(linhas_gis,[],[],[],[]))
        nos={n['uid']:n for n in p['nos']}
        for i,r in enumerate(p['pipes']):
            r['no_b']=r['no_a']
            if i>=3:
                x,y=nos[r['no_a']]['xy']
                g=QgsGeometry.fromWkt(f'LINESTRING({x} {y},{x+1} {y},{x+1} {y+1},{x} {y})')
                r.update(wkb=bytes(g.asWkb()),comprimento_m=g.length())
        pend,_=cadastro.validar_modelbuilder(p,dict(perfil=perfil(),escopo='COMPLETO'))
        self.assertEqual(sum(x.get('codigo')=='MESMO_NO_PONTAS_DISTINTAS' for x in pend),3)
        self.assertEqual(sum(x.get('codigo')=='ANEL_MESMO_NO' for x in pend),2)


class CorrecaoEDestino(unittest.TestCase):
    def test_separacao_isolada_transacional_reexecuta_sem_mudar_revisao_anterior(self):
        t=gis.linha('p',(0,0),(.1,0))
        t.update(id='SINT',feicao='p',fontes=['a'],categoria='PIPE')
        args=dict(inferir_proximas=True,tolerancia=.2)
        f=gis.construir([t],**args)
        p={'uid':'p_export','parte':'p','inicio':0.,'fim':1.,
           'no_a':f['nos'][0]['uid'],'no_b':f['nos'][0]['uid'],'wkb':f['tubos'][0]['wkb']}
        with TemporaryDirectory() as pasta:
            base=Path(pasta)/'complementos.gpkg'
            pg.criar_complementos(base,'pj')
            h=pg.salvar_revisao(base,'pj','HIPOTESE',dict(nome='Original',formato=2,projeto_uid='pj',
                                vinculos={},selecionados=[]))
            ref={k:h[k] for k in ('uuid','rev')}
            f['hipotese']=ref
            plano=correcao.separacao(p,f,f['nos'][0])
            d=dict(elemento_uid=p['uid'],codigo='MESMO_NO_PONTAS_DISTINTAS',projeto_uid='pj',topologia_uid='exec',
                   estado='APLICADA',operacao='SEPARACAO')
            r=pg.salvar_separacao_modelbuilder(base,'pj',ref,d,plano['relacao'],'corr',None)
            reg=pg.vigentes(base,'pj')
            self.assertEqual(reg[h['uuid']],h)
            self.assertEqual(reg[r['nova_hipotese']['uuid']]['vinculos'],{r['relacao_uid']:reg[r['relacao_uid']]['rev']})
            f2=gis.construir([t],conexoes=[reg[r['relacao_uid']]],**args)
            self.assertEqual(len(f2['nos']),2)
            self.assertEqual(len(f2['componentes']),len(f['componentes']))
            with self.assertRaisesRegex(ValueError,'outra sessão'):
                pg.salvar_separacao_modelbuilder(base,'pj',ref,d,plano['relacao'],'corr',None)
            self.assertEqual(len(pg.vigentes(base,'pj')),4)
            n=dict(f['nos'][0],portas=[*f['nos'][0]['portas'],['ligacao_legitima',1.]])
            with self.assertRaisesRegex(ValueError,'outras portas'):
                correcao.separacao(p,f,n)

    def test_destino_digitado_criacao_conflito_e_permissao(self):
        with TemporaryDirectory() as pasta:
            p=Path(pasta)/'Pasta de teste'/'Nova pasta'
            n=destino.nome_pacote('aaaaaaaaaaaaaaaaabbb')
            self.assertEqual(destino.caminho_pasta(f'"{p}"'),p)
            with self.assertRaisesRegex(ValueError,'indisponível'):
                destino.preparar(p,n)
            self.assertEqual(destino.preparar(p,n,criar=True),p/n)
            self.assertEqual(list(p.iterdir()),[])
            with patch.object(destino,'TemporaryFile',side_effect=PermissionError('negado')):
                with self.assertRaisesRegex(OSError,'Sem acesso de gravação'):
                    destino.preparar(p,n)
            (p/n).mkdir()
            with self.assertRaises(FileExistsError):
                destino.preparar(p,n)

    def test_relacao_exclusiva_e_substituida_somente_na_hipotese_derivada(self):
        t=gis.linha('p',(0,0),(5,0))
        t.update(id='SINT',feicao='p',fontes=['a'],categoria='PIPE')
        with TemporaryDirectory() as pasta:
            base=Path(pasta)/'complementos.gpkg'
            pg.criar_complementos(base,'pj')
            r=pg.salvar_revisao(base,'pj','CONEXAO',dict(nome='União exclusiva',situacao='INFORMADA',
                                decisao='CONFIRMADA',portas=[['p',0.],['p',1.]]))
            h=pg.salvar_revisao(base,'pj','HIPOTESE',dict(nome='Original',formato=2,projeto_uid='pj',
                                vinculos={r['uuid']:r['rev']},selecionados=[r['uuid']]))
            ref={k:h[k] for k in ('uuid','rev')}
            f=gis.construir([t],conexoes=[r])
            f.update(hipotese=ref,participantes=[r])
            n=f['nos'][0]
            p=dict(uid='p_export',parte='p',inicio=0.,fim=1.,no_a=n['uid'],no_b=n['uid'],wkb=f['tubos'][0]['wkb'])
            plano=correcao.separacao(p,f,n)
            d=dict(elemento_uid=p['uid'],codigo='MESMO_NO_PONTAS_DISTINTAS',projeto_uid='pj',topologia_uid='exec',
                   estado='APLICADA',operacao='SEPARACAO')
            c=pg.salvar_separacao_modelbuilder(base,'pj',ref,d,plano['relacao'],'corr',None)
            reg=pg.vigentes(base,'pj')
            self.assertEqual(reg[r['uuid']],r)
            self.assertEqual(reg[h['uuid']],h)
            self.assertEqual(reg[c['nova_hipotese']['uuid']]['selecionados'],[c['relacao_uid']])
