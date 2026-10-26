"""Demonstra atualização apenas em SQLite sintético criado pelo próprio ensaio."""
import argparse
import json
from pathlib import Path
import sqlite3
from test_bases_plugin import banco_nativo
from auditoria_topologica_watergems import bases
from auditoria_topologica_watergems.arquivos import hash_arquivo

def executar(destino):
    pasta=Path(destino).resolve();pasta.mkdir(parents=True,exist_ok=True)
    fonte=pasta/'CONTROLE_SINTETICO.sqlite';banco_nativo(fonte)
    ref=dict(crs='EPSG:31983',fator=1,fonte='Coordenadas sintéticas métricas; não é o modelo operacional')
    a=bases.criar(fonte,pasta/'Controle_TopologiaWG_v001.gpkg',nome='CONTROLE SINTÉTICO',projeto='Ensaio sintético',referencia=ref);h=hash_arquivo(a)
    with sqlite3.connect(fonte) as c:c.execute('update BaseDirectedNode_HMIActiveTopology_Data set HMIActiveTopologyIsActive=0 where DomainElementID=2')
    b=bases.criar(fonte,pasta/'Controle_TopologiaWG_v002.gpkg',nome='CONTROLE SINTÉTICO',projeto='Ensaio sintético',referencia=ref,anterior=a)
    r=bases.comparar(a,b);r.update(natureza='CONTROLE_SINTETICO — nenhuma intervenção no modelo real',anterior_preservada=hash_arquivo(a)==h)
    (pasta/'COMPARACAO.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
    assert r['anterior_preservada'] and r['alterados']['ativo']==[2]
    print(json.dumps(r,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('pasta');a=p.parse_args();executar(a.pasta)
