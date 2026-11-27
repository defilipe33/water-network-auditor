"""Regressões do fluxo guiado com divisões próximas e revisões concorrentes."""

from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

import test_grafo_gis as gis
from test_modelbuilder_119 import perfil
from auditoria_aplicacao import cadastro_exportavel as cadastro
from auditoria_aplicacao import correcao_modelbuilder as fila
from auditoria_aplicacao import persistencia_grafo_gis as pg
from auditoria_aplicacao import resolver_conexoes_modelbuilder as resolver


def linhas():
    rs=[gis.linha('tronco',(0,0),(20,0)),gis.linha('b',(10,0),(10,-5)),gis.linha('c',(10.02,0),(10.02,5)),
        gis.linha('d',(10.04,0),(11,6)),gis.linha('isolado',(40,0),(50,0))]
    for r in rs:r.update(id=r['uid'],feicao=r['uid'],camada='Rede sintética',categoria='PIPE',fontes=['rede'])
    return rs


def relacoes(n=2):
    return [dict(uuid=f'c{i}',rev=f'r{i}',tipo='CONEXAO',nome=f'Ligação {i+1}',situacao='INFORMADA',
                 acompanhamento='VERIFICADO',decisao='CONFIRMADA',portas=[['tronco',.5+i/1000],[t,0.]])
            for i,t in enumerate(('b','c','d')[:n])]


def executar(ts,rs,*,inferir=True,uid='foto',hipotese=None):
    d=gis.construir(ts,inferir_proximas=inferir,conexoes=rs)
    return dict(d,participantes=rs,projeto_uid='projeto',uuid=uid,crs='EPSG:31983',algoritmo='sintetico',
                parametros=dict(tolerancia=.2),hipotese=hipotese)


def validar(ts,rs,**op):
    f=executar(ts,rs,**op)
    p=cadastro.preparar(f,(ts,[],[],[],[]))
    ps,m=cadastro.validar_modelbuilder(p,dict(perfil=perfil(),escopo='COMPLETO'))
    return f,p,ps,m


class Decisoes(unittest.TestCase):
    def setUp(self):
        self.ts=linhas()
        self.rs=relacoes()
        self.f,p,ps,_=validar(self.ts,self.rs)
        self.pend=next(r for r in ps if r.get('codigo')=='MESMO_NO_PONTAS_DISTINTAS' and r['parte']=='tronco')
        self.pipe=next(r for r in p['pipes'] if r['uid']==self.pend['uid'])
        self.analise=resolver.investigar(self.f,self.pipe,self.rs)
        self.assertEqual([x['letra'] for x in self.analise['ligacoes']],['A','B'])
        self.assertAlmostEqual(self.analise['comprimento_m'],.02)
        self.assertAlmostEqual(self.analise['ligacoes'][0]['distancia_m'],.02)
        self.assertEqual({x['situacao'] for x in self.analise['ligacoes']},{'APLICADA'})

    def _testar(self,escolhas,**kw):
        p=resolver.planejar(self.f,self.analise,escolhas,**kw)
        f,_,ps,m=validar(self.ts,p['participantes'],uid='outra')
        return p,f,ps,m

    def test_manter_so_a_ou_b_preserva_vinculo_historico_e_permita_exportar(self):
        for manter,fora in (('c0','c1'),('c1','c0')):
            with self.subTest(manter=manter):
                p,f,ps,m=self._testar({manter:resolver.MANTER,fora:resolver.EXCLUIR})
                self.assertEqual(set(f['resolucoes_conexoes']),{manter})
                self.assertEqual([r['decisao'] for r in self.rs],['CONFIRMADA','CONFIRMADA'])
                self.assertIsNone(p['operacoes'][fora]['dados'])
                self.assertFalse(m['excluidos'])
                self.assertFalse(any(r['gravidade']=='CRITICA' for r in ps))
                self.assertEqual(len(f['componentes']),len(self.f['componentes']))
        with TemporaryDirectory() as t:
            dst=cadastro.exportar(cadastro.preparar(f,(self.ts,[],[],[],[])),t,'CSV',
                                 modelbuilder=dict(perfil=perfil(),escopo='COMPLETO'))
            self.assertTrue((dst/'pipes.csv').is_file())

    def test_manter_as_duas_exibe_efeito_real_e_preserva_curto_legitimo(self):
        escolhas={u:resolver.MANTER for u in ('c0','c1')}
        p,_,_,m=self._testar(escolhas)
        self.assertFalse(p['operacoes'])
        self.assertTrue(m['excluidos'])
        _,_,pend,m=validar(self.ts,self.rs,inferir=False)
        self.assertFalse(m['excluidos'])
        self.assertTrue(any(r.get('codigo')=='SEGMENTO_CURTO_LIGACOES' for r in pend))

    def test_consolidacao_preserva_ramos_e_rejeicao_separa_componentes(self):
        p,f,_,m=self._testar({'c0':resolver.MANTER,'c1':resolver.MANTER},consolidar='c0')
        self.assertFalse(m['excluidos'])
        r=next(r for r in p['participantes'] if r['uuid']=='c1')
        self.assertEqual(r['portas'],[['tronco',.5],['c',0.]])
        self.assertEqual(f['resolucoes_conexoes'],{'c0':'APLICADA','c1':'APLICADA'})
        p,f,_,m=self._testar({'c0':resolver.REJEITAR,'c1':resolver.REJEITAR})
        self.assertEqual(set(f['resolucoes_conexoes'].values()),{'SEPARADA'})
        self.assertFalse(m['excluidos'])
        eq=dict(uid='res',declaracoes=[dict(portas=[['c',0.]])])
        efeito=resolver.impacto(dict(self.f,equipamentos=[eq]),f,self.analise,
                               [dict(nome='Referência',membros=[dict(parte='tronco')])])
        self.assertGreater(len(efeito['componentes_depois']),len(efeito['componentes_antes']))
        self.assertEqual(efeito['equipamentos'],[eq])
        self.assertEqual(efeito['conjuntos'],['Referência'])

    def test_tres_relacoes_duplicata_e_referencia_alterada(self):
        terceira=deepcopy(self.rs[0])
        terceira.update(uuid='dup',rev='rd')
        alterada=dict(terceira,uuid='alt',rev='ra',portas=[['tronco',.5],['antigo',0.]])
        dados=resolver.investigar(self.f,self.pipe,[*self.rs,terceira,alterada])
        self.assertEqual(len(dados['ligacoes']),4)
        self.assertTrue(any(x['tipo']=='EXATA' for x in dados['duplicatas']))
        estados={r['registro']['uuid']:r['situacao'] for r in dados['ligacoes']}
        self.assertEqual((estados['dup'],estados['alt']),('FORA_DA_HIPOTESE','REFERENCIA_ALTERADA'))
        op={'c0':resolver.MANTER,'c1':resolver.EXCLUIR,'dup':resolver.MANTER,'alt':resolver.EXCLUIR}
        p=resolver.planejar(self.f,dados,op,consolidar='c0')
        self.assertEqual(p['escolhas']['dup'],resolver.EXCLUIR)
        op['alt']=resolver.MANTER
        with self.assertRaisesRegex(ValueError,'referência alterada'):
            resolver.planejar(self.f,dados,op)
        p=resolver.planejar(self.f,dados,op,edicoes={'alt':[('tronco',.5),('b',0.)]})
        self.assertEqual(p['operacoes']['alt']['dados']['portas_anteriores'],alterada['portas'])
        with self.assertRaisesRegex(ValueError,'tolerância'):
            resolver.planejar(self.f,dados,op,edicoes={'alt':[('tronco',.5),('isolado',0.)]})


class Persistencia(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.base=Path(t.name)/'projeto.gpkg'
        pg.criar_complementos(self.base,'projeto')
        self.ts=linhas()
        self.rs=[pg.salvar_revisao(self.base,'projeto','CONEXAO',r) for r in relacoes()]
        self.h=pg.salvar_revisao(self.base,'projeto','HIPOTESE',dict(nome='Original',formato=2,projeto_uid='projeto',
             vinculos={r['uuid']:r['rev'] for r in self.rs},selecionados=[r['uuid'] for r in self.rs]))
        self.f,self.p,self.ps,_=validar(self.ts,self.rs,hipotese=self.h)
        self.alvo=next(r for r in self.ps if r.get('codigo')=='MESMO_NO_PONTAS_DISTINTAS')
        self.uid=fila.identidade(self.f['uuid'],self.alvo)
        self.dados=dict(topologia_uid=self.f['uuid'],elemento_uid=self.alvo['uid'],codigo=self.alvo['codigo'],
                        estado='APLICADA',projeto_uid='projeto',diagnostico=self.alvo)
        alvo=next(r for r in self.p['pipes'] if r['uid']==self.alvo['uid'])
        a=resolver.investigar(self.f,alvo,self.rs)
        self.plano=resolver.planejar(self.f,a,{r['uuid']:resolver.REJEITAR for r in self.rs})

    def salvar(self,esperada=None):
        return pg.salvar_resolucao_modelbuilder(self.base,'projeto',self.h,self.dados,self.plano,self.uid,esperada)

    def test_preserva_revisoes_atualiza_fila_e_protege_aplicacao_duplicada(self):
        d=self.salvar()
        registros=pg.vigentes(self.base,'projeto')
        self.assertEqual(registros[self.h['uuid']],self.h)
        self.assertIn(self.uid,fila.fila(self.f,self.ps,{},{}))
        self.assertFalse(fila.fila(self.f,self.ps,{self.uid:d},{}))
        for r in self.rs:self.assertEqual(len(pg.revisoes(self.base,'projeto',r['uuid'])),2)
        with self.assertRaisesRegex(ValueError,'já foi aplicada'):
            self.salvar(d['rev'])
        h=registros[d['nova_hipotese']['uuid']]
        ps=[registros[u] for u in h['selecionados']]
        f,_,erros,_=validar(self.ts,ps,uid='derivada',hipotese=h)
        self.assertEqual(fila.estado_em_validacao(d,f,erros,{'tronco'},True),'VALIDADA')
        self.assertIsNone(fila.estado_em_validacao(d,f,[],set(),True))
        self.assertIsNone(fila.estado_em_validacao(d,self.f,[],{'tronco'},True))
        self.assertEqual(fila.estado_em_validacao(d,f,self.ps,{'tronco'},True,'VALIDADA'),'REABERTA')
        f2=dict(f,uuid='futura',hipotese=dict(h,rev='futura'))
        self.assertIsNone(fila.estado_em_validacao(d,f2,self.ps,{'tronco'},True,'VALIDADA'))
        estado=fila.estado_em_validacao(d,f2,self.ps,{'tronco'},True,'VALIDADA',linhagem={h['rev']})
        self.assertEqual(estado,'REABERTA')
        obs={self.uid:dict(estado=estado,parte='tronco',topologia_uid=f2['uuid'])}
        self.assertEqual(set(p['situacao_fila'] for p in fila.fila(f2,self.ps,{self.uid:d},obs).values()),{'REABERTA'})

    def test_pendente_preserva_fila_e_operacoes_da_hipotese(self):
        pendente=pg.salvar_revisao(self.base,'projeto',fila.TIPO,dict(self.dados,estado='PENDENTE',
                                   nota='Conhecimento de campo insuficiente'),self.uid)
        self.assertIn(self.uid,fila.fila(self.f,self.ps,{self.uid:pendente},{}))
        self.assertEqual(pg.revisoes(self.base,'projeto',tipo='HIPOTESE'),[self.h])
        self.assertEqual(pg.revisoes(self.base,'projeto',tipo='CONEXAO'),self.rs)

    def test_roll_back_transacional_e_concorrencia(self):
        with closing(sqlite3.connect(self.base)) as con, con:
            con.execute("""CREATE TRIGGER falha BEFORE INSERT ON TG_REVISOES WHEN NEW.tipo='HIPOTESE'
                           BEGIN SELECT RAISE(ABORT,'falha sintética'); END""")
        a=pg.revisoes(self.base,'projeto')
        with self.assertRaises(sqlite3.IntegrityError):self.salvar()
        self.assertEqual(pg.revisoes(self.base,'projeto'),a)
        r=self.rs[0]
        pg.salvar_revisao(self.base,'projeto','CONEXAO',dict(r,nota='Concorrente'),r['uuid'],r['rev'])
        with self.assertRaisesRegex(ValueError,'outra sessão'):self.salvar()
        self.assertFalse(pg.revisoes(self.base,'projeto',tipo=fila.TIPO))

    def test_materializacao_ainda_visivel_ate_validacao_e_historico_separado(self):
        d=dict(self.dados,operacao='ANEL',fracao=.5,assinatura='assinatura')
        r=pg.salvar_revisao(self.base,'projeto',fila.TIPO,d,self.uid)
        self.assertIn(self.uid,fila.fila(self.f,self.ps,{self.uid:r},{}))
        self.assertFalse(fila.fila(self.f,[],{self.uid:r},{}))
        self.assertEqual(len(pg.revisoes(self.base,'projeto',self.uid)),1)
        with self.assertRaisesRegex(ValueError,'já foi aplicada'):
            pg.salvar_revisao(self.base,'projeto',fila.TIPO,d,self.uid,r['rev'])
