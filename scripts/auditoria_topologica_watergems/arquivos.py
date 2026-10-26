"""Inspeção seletiva de ZIP/RAR, caminhos validados e extração sem sobrescrita."""
from hashlib import sha256
from pathlib import Path,PurePosixPath
import json
import shutil
import stat
import subprocess
import zipfile


def caminho_seguro(nome):
    p=PurePosixPath(nome.replace('\\','/'))
    if not p.parts or p.is_absolute() or '..' in p.parts or any(':' in parte for parte in p.parts):
        raise ValueError('Caminho interno inseguro: '+nome)
    return p


def hash_arquivo(p):
    h=sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):
            h.update(b)
    return h.hexdigest()


def listar_pacote(pacote,sete_zip=None):
    p=Path(pacote).resolve(strict=True)
    if zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as z:
            saida=[]
            for f in z.infolist():
                caminho_seguro(f.filename)
                if stat.S_ISLNK(f.external_attr>>16) or f.flag_bits&1:
                    raise ValueError('ZIP com link ou membro criptografado: '+f.filename)
                if not f.is_dir():
                    saida.append(dict(nome=f.filename,tamanho=f.file_size,crc=f'{f.CRC:08X}'))
            return saida
    if p.suffix.lower()!='.rar' or not sete_zip:
        raise ValueError('RAR exige caminho do 7-Zip já instalado; nenhum pacote será instalado')
    r=subprocess.run([str(sete_zip),'l','-slt','-sccUTF-8',str(p)],capture_output=True,check=True)
    texto=r.stdout.decode('utf-8').replace('\r\n','\n').split('----------',1)[-1]
    saida=[]
    for bloco in texto.strip().split('\n\n'):
        dados={linha.split(' = ',1)[0].strip():linha.split(' = ',1)[1].strip()
            for linha in bloco.splitlines() if ' = ' in linha}
        nome=dados.get('Path')
        if not nome:
            continue
        caminho_seguro(nome)
        if any(dados.get(k) for k in ('Symbolic Link','Hard Link','Copy Link')) or dados.get('Encrypted')=='+':
            raise ValueError('RAR com link ou membro criptografado: '+nome)
        if dados.get('Folder')!='+':
            saida.append(dict(nome=nome,tamanho=int(dados['Size']),crc=dados.get('CRC')))
    return saida


def extrair_modelo(pacote,pasta,sete_zip=None,reserva=2*1024**3):
    p=Path(pacote).resolve(strict=True);pasta=Path(pasta).resolve()
    membros=listar_pacote(p,sete_zip)
    escolhidos=[m for m in membros if m['nome'].lower().endswith(('.wtg','.wtg.sqlite'))]
    nomes=[caminho_seguro(m['nome']).name.casefold() for m in escolhidos]
    if len(nomes)!=len(set(nomes)) or not any(n.endswith('.wtg.sqlite') for n in nomes):
        raise ValueError('Modelo ausente ou nomes de saída ambíguos; selecione pacote inequívoco')
    if any(m['nome'].lower().endswith(('-wal','-journal')) for m in membros):
        raise ValueError('Pacote contém journal/WAL; snapshot precisa ser consolidado pelo produtor')
    if pasta.exists():
        raise FileExistsError('Escolha diretório de trabalho novo')
    if sum(m['tamanho'] for m in escolhidos)+reserva>shutil.disk_usage(pasta.parent).free:
        raise ValueError('Espaço insuficiente para seleção e reserva de segurança')
    antes=hash_arquivo(p);pasta.mkdir()
    saidas=[]
    for m in escolhidos:
        alvo=pasta/caminho_seguro(m['nome']).name
        with alvo.open('xb') as destino:
            if zipfile.is_zipfile(p):
                with zipfile.ZipFile(p) as z,z.open(m['nome']) as fonte:
                    shutil.copyfileobj(fonte,destino,1024*1024)
            else:
                r=subprocess.run([str(sete_zip),'x','-so','-spd',str(p),m['nome']],stdout=destino,stderr=subprocess.PIPE)
                if r.returncode:
                    raise ValueError('Extração falhou: '+r.stderr.decode('utf-8',errors='replace'))
        if alvo.stat().st_size!=m['tamanho']:
            raise ValueError('Tamanho extraído divergente: '+str(alvo))
        saidas.append(dict(**m,saida=str(alvo),sha256=hash_arquivo(alvo)))
    if hash_arquivo(p)!=antes:
        raise ValueError('Pacote original alterado durante a leitura')
    manifesto=dict(pacote=str(p),sha256_pacote=antes,membros=membros,extraidos=saidas,
        integridade='CRC verificado pelo leitor ZIP/7-Zip; SHA-256 das cópias e pacote',original_preservado=True)
    (pasta/'EXTRACAO.json').write_text(json.dumps(manifesto,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifesto
