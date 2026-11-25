"""Benchmark sintético de um grafo em malha. Executar com Python do QGIS."""

import argparse
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))

from qgis.core import Qgis, QgsGeometry, QgsPointXY
from auditoria_aplicacao.grafo_gis import construir


def medir(lado, repeticoes):
    tubos=[]
    for y in range(lado):
        for x in range(lado):
            for a,b in ((x+1,y),(x,y+1)):
                tubos.append(dict(uid=str(len(tubos)),diametro_mm=250,
                                  geom=QgsGeometry.fromPolylineXY([QgsPointXY(10*x,10*y),QgsPointXY(10*a,10*b)])))
    ts=[]
    for _ in range(repeticoes):
        t=time.perf_counter()
        d=construir(tubos,origens=[dict(uuid='fonte',portas=[('0',0.)])])
        ts.append(time.perf_counter()-t)
        assert len(d['componentes'])==1 and d['componentes'][0]['origens']==['fonte']
        assert d['componentes'][0]['comprimento_m']==10*len(tubos)
    return dict(tubos=len(tubos),nos=len(d['nos']),mediana_s=statistics.median(ts),pior_s=max(ts),medicoes_s=ts)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--lado',type=int,default=100)
    p.add_argument('--repeticoes',type=int,default=3)
    a=p.parse_args()
    print(json.dumps(dict(qgis=Qgis.QGIS_VERSION,python=sys.version.split()[0],**medir(a.lado,a.repeticoes))))
