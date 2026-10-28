"""Executa todos os test_*.py em processos separados, sem ocultar falhas nativas.

O Python deve ser o do QGIS, com seu ambiente carregado. Isola estado global Qt e
provedores entre módulos; não substitui testes de interação dentro de cada módulo.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def modulo(arquivo):
    """Finaliza explicitamente widgets/provedores antes do runtime PyQGIS."""
    import unittest,gc
    testes=Path(__file__).resolve().parent;sys.path.insert(0,str(testes))
    suite=unittest.defaultTestLoader.discover(str(testes),pattern=arquivo)
    resultado=unittest.TextTestRunner(verbosity=2).run(suite);aprovado=resultado.wasSuccessful();del suite,resultado
    from qgis.core import QgsApplication,QgsProject
    from qgis.PyQt.QtCore import QCoreApplication,QEvent,QThread
    from qgis.PyQt.QtWidgets import QApplication
    from qgis.PyQt import sip
    app=QApplication.instance()
    if app:
        for w in list(QApplication.topLevelWidgets()):
            if sip.isdeleted(w):continue
            for t in w.findChildren(QThread):
                if not sip.isdeleted(t) and t.isRunning() and t is not QThread.currentThread():
                    t.requestInterruption()
                    if not t.wait(10000):raise RuntimeError('Thread de teste não encerrou cooperativamente; limpeza não aprovada')
            w.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);QCoreApplication.processEvents()
        QgsProject.instance().removeAllMapLayers();gc.collect();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        QgsApplication.exitQgis()
    return aprovado


def executar(destino):
    raiz=Path(__file__).resolve().parents[1];testes=raiz/'testes';destino=Path(destino).resolve();destino.mkdir(parents=True,exist_ok=False);resultados=[];inicio=time.monotonic()
    env=os.environ.copy();env['QT_QPA_PLATFORM']='offscreen';env['TEMP']=env['TMP']=str(destino)
    for arquivo in sorted(testes.glob('test_*.py')):
        log=destino/(arquivo.stem+'.log');t=time.monotonic();timeout=False
        with log.open('w',encoding='utf8') as out:
            try:r=subprocess.run([sys.executable,'-X','faulthandler',str(Path(__file__).resolve()),'--modulo',arquivo.name],cwd=raiz,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=240);codigo=r.returncode
            except subprocess.TimeoutExpired:codigo=None;timeout=True
        texto=log.read_text(encoding='utf8',errors='replace');m=re.search(r'Ran (\d+) tests? in ',texto)
        d=dict(modulo=arquivo.name,codigo=codigo,timeout=timeout,testes=int(m[1]) if m else 0,aprovado=codigo==0 and bool(m) and bool(re.search(r'^OK\s*$',texto,re.M)),segundos=round(time.monotonic()-t,2))
        resultados.append(d);print(json.dumps(d,ensure_ascii=False),flush=True)
        (destino/'RESULTADO.json').write_text(json.dumps(dict(modulos=resultados,testes=sum(x['testes'] for x in resultados),aprovado=all(x['aprovado'] for x in resultados),segundos=round(time.monotonic()-inicio,2)),ensure_ascii=False,indent=2),encoding='utf8')
    return all(x['aprovado'] for x in resultados)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destino',nargs='?');p.add_argument('--modulo');args=p.parse_args()
    if not args.modulo and not args.destino:p.error('Informe um diretório novo de resultados')
    sys.exit(0 if (modulo(args.modulo) if args.modulo else executar(args.destino)) else 1)
