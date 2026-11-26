"""Publicação de uma pasta concluída, com recuperação de bloqueios transitórios no Windows."""

from time import sleep

from auditoria_fronteiras.modelos import verificar_cancelamento


def publicar(temporaria,destino,cancelar=None):
    for espera in (.05,.10,.20,.40,.80,0):
        verificar_cancelamento(cancelar)
        if destino.exists():
            raise FileExistsError(destino)
        try:
            temporaria.rename(destino)
        except PermissionError as erro:
            if not espera or getattr(erro,'winerror',None) not in (5,32,33):
                raise
            sleep(espera)
        else:
            return
