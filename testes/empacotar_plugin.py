"""Gera ZIP autônomo a partir dos módulos canônicos, sem instalar no perfil."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

def empacotar(raiz,destino):
    raiz=Path(raiz);destino=Path(destino)
    if destino.exists():raise FileExistsError(destino)
    manifesto={}
    with zipfile.ZipFile(destino,'x',zipfile.ZIP_DEFLATED) as z:
        for p in (raiz/'complemento_qgis/auditoria_redes').rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:
                nome='auditoria_redes/'+str(p.relative_to(raiz/'complemento_qgis/auditoria_redes')).replace('\\','/');z.write(p,nome);manifesto[nome]=hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (raiz/'scripts').rglob('*.py'):
            if '__pycache__' in p.parts:continue
            nome='auditoria_redes/_biblioteca/'+str(p.relative_to(raiz/'scripts')).replace('\\','/');z.write(p,nome);manifesto[nome]=hashlib.sha256(p.read_bytes()).hexdigest()
        z.writestr('auditoria_redes/MANIFESTO.json',json.dumps(manifesto,indent=2))
    return destino
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('destino');args=a.parse_args();empacotar(Path(__file__).resolve().parents[1],args.destino)
