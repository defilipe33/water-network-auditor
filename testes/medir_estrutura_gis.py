"""Mede a análise estrutural sobre fotografias de redes sintéticas no PyQGIS."""

import argparse
import json
import platform
import sys
from pathlib import Path
from time import perf_counter
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from auditoria_aplicacao.corredores_gis import analisar, novo_destino, testar_interrupcao


def foto_municipal(largura, *, ramificada=False):
    nos = []
    tubos = []
    arestas = []
    def ligar(a, b):
        u = f'p{len(tubos)}'
        tubos.append(dict(uid=u, comprimento_m=10.))
        arestas.append(dict(a=str(a), b=str(b), tubo=u, comprimento_m=10.))
    for y in range(largura):
        for x in range(largura):
            i = y*largura+x
            nos.append(dict(uid=str(i), portas=[], xy=[x*10., y*10.]))
            if x:
                ligar(i-1, i)
            if y and (not ramificada or x==0):
                ligar(i-largura, i)
    origens = []
    for nome,i in [('A',0),('B',largura*(largura-1))]:
        porta = [f'origem-{nome}',0.]
        nos[i]['portas'].append(porta)
        origens.append(dict(uuid=nome,tipo='ORIGEM',situacao='INFORMADA',portas=[porta],rev=nome+'-1'))
    return dict(uuid='execucao-sintetica',projeto_uid='medicao',crs='EPSG:31983',nos=nos,
                arestas=arestas,tubos=tubos,origens_validas=['A','B'],participantes=origens)


def medir(largura, agrupado=False):
    registros = []
    for ramificada in (False,True):
        foto = foto_municipal(largura,ramificada=ramificada)
        destinos = [novo_destino('NO',str(n)) for n in range(largura*largura-1,0,-largura*7)][:25]
        opcoes = dict(modo='AUTOMATICO',maximo=24,minimo_m=0) if agrupado else None
        tempos = []
        cortes = []
        ids = [foto['arestas'][0]['tubo'],foto['arestas'][-1]['tubo']]
        for _ in range(5):
            inicio = perf_counter()
            r = analisar(foto,destinos=destinos,agrupamento=opcoes)
            agora = perf_counter()
            testar_interrupcao(r,ids)
            tempos.append(agora-inicio)
            cortes.append(perf_counter()-agora)
        del r
        tracemalloc.start()
        r = analisar(foto,destinos=destinos,agrupamento=opcoes)
        _, pico = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        registros.append(dict(rede='ramificada' if ramificada else 'malhada',nos=len(foto['nos']),
            tubulacoes=len(r['tubulacoes']),destinos=len(r['destinos']),origens=len(r['fontes']),
            corredores=len(r.get('agrupamento',{}).get('corredores',())),
            analises_s=tempos,interrupcoes_s=cortes,pico_python_mib=pico/1048576,
            pontes=r['pontes_segmentos'],ligacoes_criticas=sum('CRITICA' in t['funcoes'] for t in r['tubulacoes'])))
    return dict(python=sys.version.split()[0],sistema=platform.platform(),medicoes=registros)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('saida',type=Path)
    p.add_argument('--largura',type=int,default=180)
    p.add_argument('--agrupado',action='store_true')
    args=p.parse_args()
    args.saida.write_text(json.dumps(medir(args.largura,args.agrupado),ensure_ascii=False,indent=2),encoding='utf-8')
