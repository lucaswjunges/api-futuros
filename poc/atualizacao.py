"""
Atualização automática do .exe (pedido do Lucas em 24/09/2026, aprovado pelo Hugo).
==================================================================================

Como funciona:
  1. Ao abrir, o app lê https://futuros.blumenauti.com.br/versao.json (poucos bytes, timeout curto,
     em segundo plano). Sem internet ou com qualquer erro, não acontece nada — o app segue normal.
  2. Se a versão publicada for mais nova que VERSAO (versao.py), a janela pergunta se o cliente
     quer atualizar.
  3. "Sim": baixa o .exe novo para %APPDATA%\\AlertaFuturos\\atualizacao, confere tamanho, SHA-256 e
     que é mesmo um executável do Windows. Qualquer divergência = descarta e avisa.
  4. Troca: o .exe em uso é MOVIDO para a pasta "Versões anteriores", ao lado dele (o Windows deixa
     renomear/mover um .exe em execução no mesmo disco, só não deixa sobrescrever), e o novo vai
     para o lugar exato do antigo — então o atalho, o "iniciar com o Windows" (que grava esse
     caminho no Registro) e o hábito do cliente continuam valendo. Se algo falhar no meio, desfaz.
  5. Abre o .exe novo e fecha este (parando o monitor e fechando o CSV como no "Sair").

A versão antiga fica guardada em "Versões anteriores" — era o que o Lucas pediu: se o cliente
quiser voltar, é só abrir o arquivo de lá.

Assinatura digital: o .exe continua sem certificado (decisão de 24/09: resolver na próxima
versão). Um arquivo baixado pelo próprio app não recebe a marca "veio da internet" que o navegador
põe, então em geral o SmartScreen não aparece de novo; um antivírus mais desconfiado ainda pode
reclamar de um programa sem assinatura que baixa um executável. Se a atualização falhar por
qualquer motivo, o app oferece abrir a página de download.

Publicar uma versão nova (ver publicar_versao.py): aumentar VERSAO em versao.py, buildar,
gerar o versao.json a partir do .exe e subir os dois no site.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from versao import VERSAO

log = logging.getLogger("alerta.atualizacao")

URL_VERSAO = "https://futuros.blumenauti.com.br/versao.json"
URL_PAGINA = "https://futuros.blumenauti.com.br/"
DOMINIO_PERMITIDO = "https://futuros.blumenauti.com.br/"
PASTA_ANTERIORES = "Versões anteriores"
TAMANHO_MAXIMO = 80 * 1024 * 1024  # um .exe nosso tem ~21 MB; muito acima disso é erro


@dataclass
class Publicada:
    versao: str
    url: str
    sha256: str
    tamanho: int
    data: str = ""
    novidades: str = ""


def versao_como_tupla(texto: str) -> tuple[int, ...]:
    """'2026.09.24.1' -> (2026, 9, 24, 1). Texto inválido -> () (nunca é "mais novo")."""
    try:
        return tuple(int(p) for p in str(texto).strip().split("."))
    except ValueError:
        return ()


def eh_mais_nova(publicada: str, atual: str = VERSAO) -> bool:
    p, a = versao_como_tupla(publicada), versao_como_tupla(atual)
    return bool(p) and bool(a) and p > a


def ler_publicada(dados: dict) -> Publicada:
    """Valida o versao.json. Levanta ValueError se faltar algo ou se a URL não for do nosso site
    (o app nunca baixa executável de outro endereço, mesmo que o JSON seja adulterado)."""
    try:
        p = Publicada(versao=str(dados["versao"]), url=str(dados["url"]),
                      sha256=str(dados["sha256"]).lower(), tamanho=int(dados["tamanho"]),
                      data=str(dados.get("data", "")), novidades=str(dados.get("novidades", "")))
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"versao.json incompleto: {e}") from e
    if not versao_como_tupla(p.versao):
        raise ValueError("versão inválida")
    if not p.url.startswith(DOMINIO_PERMITIDO):
        raise ValueError("URL fora do site da Blumenau TI")
    if len(p.sha256) != 64 or any(c not in "0123456789abcdef" for c in p.sha256):
        raise ValueError("sha256 inválido")
    if not (0 < p.tamanho <= TAMANHO_MAXIMO):
        raise ValueError("tamanho inválido")
    return p


def _abrir(url: str, timeout: float):
    pedido = urllib.request.Request(url, headers={"User-Agent": f"AlertaFuturos/{VERSAO}",
                                                  "Cache-Control": "no-cache"})
    return urllib.request.urlopen(pedido, timeout=timeout)  # noqa: S310 (https fixo, ver acima)


def verificar(abrir=_abrir, timeout: float = 6.0) -> Publicada | None:
    """Versão publicada se for mais nova que esta; None se não for, ou em qualquer erro (sem
    internet, site fora, JSON quebrado) — verificar atualização nunca pode atrapalhar o app."""
    try:
        with abrir(URL_VERSAO + f"?v={VERSAO}", timeout) as r:
            publicada = ler_publicada(json.loads(r.read(64 * 1024).decode("utf-8")))
    except Exception as e:
        log.info("Verificação de atualização não concluída: %s", e)
        return None
    return publicada if eh_mais_nova(publicada.versao) else None


def baixar(publicada: Publicada, destino: Path, progresso: Callable[[int, int], None] | None = None,
           abrir=_abrir, timeout: float = 30.0) -> Path:
    """Baixa para `destino` (arquivo .part e só renomeia no fim) e confere tamanho, SHA-256 e
    cabeçalho 'MZ'. Levanta OSError/ValueError com mensagem legível se algo não bater."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".part")
    h, total = hashlib.sha256(), 0
    try:
        with abrir(publicada.url, timeout) as r, parcial.open("wb") as f:
            while True:
                bloco = r.read(256 * 1024)
                if not bloco:
                    break
                total += len(bloco)
                if total > publicada.tamanho:
                    raise ValueError("o arquivo baixado é maior que o esperado")
                h.update(bloco)
                f.write(bloco)
                if progresso:
                    progresso(total, publicada.tamanho)
        if total != publicada.tamanho:
            raise ValueError(f"download incompleto ({total} de {publicada.tamanho} bytes)")
        if h.hexdigest() != publicada.sha256:
            raise ValueError("o arquivo baixado não confere (SHA-256 diferente)")
        with parcial.open("rb") as f:
            if f.read(2) != b"MZ":
                raise ValueError("o arquivo baixado não é um executável do Windows")
        if destino.exists():
            destino.unlink()
        parcial.replace(destino)
        return destino
    except BaseException:
        try:
            parcial.unlink()
        except OSError:
            pass
        raise


def _nome_livre(pasta: Path, base: str) -> Path:
    alvo = pasta / f"{base}.exe"
    n = 2
    while alvo.exists():
        alvo = pasta / f"{base} ({n}).exe"
        n += 1
    return alvo


def trocar_executavel(atual: Path, novo: Path, versao_atual: str = VERSAO) -> Path:
    """Move `atual` (em uso) para 'Versões anteriores' e põe `novo` no lugar dele. Devolve onde a
    versão antiga ficou. Se o segundo passo falhar, desfaz o primeiro (o cliente nunca fica sem
    executável no lugar de sempre)."""
    pasta_antigas = atual.parent / PASTA_ANTERIORES
    pasta_antigas.mkdir(exist_ok=True)
    guardada = _nome_livre(pasta_antigas, f"AlertaFuturos-{versao_atual}")
    if os.name != "nt":  # fora do Windows o arquivo baixado precisa do bit de execução
        os.chmod(novo, 0o755)
    os.replace(atual, guardada)
    try:
        os.replace(novo, atual)
    except OSError:
        os.replace(guardada, atual)
        raise
    return guardada


def abrir_novo(caminho: Path) -> None:
    """Abre o .exe novo como processo independente. PYINSTALLER_RESET_ENVIRONMENT faz o novo
    processo extrair os próprios arquivos em vez de reaproveitar a pasta temporária deste (que
    some quando este fecha) — sem isso o app novo pode abrir quebrado."""
    ambiente = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    ambiente.pop("_MEIPASS2", None)
    opcoes = {}
    if sys.platform == "win32":
        opcoes["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(caminho)], env=ambiente, cwd=str(caminho.parent), close_fds=True, **opcoes)


def disponivel_neste_ambiente() -> bool:
    """Só o .exe se atualiza; rodando do código-fonte (desenvolvimento) quem manda é o git."""
    return bool(getattr(sys, "frozen", False))
