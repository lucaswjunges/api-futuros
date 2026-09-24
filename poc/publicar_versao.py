"""Gera o versao.json que vai para o site junto com o .exe (ver atualizacao.py).

  python publicar_versao.py "Novidades em uma frase"      # lê dist\\AlertaFuturos.exe

Grava dist\\versao.json. No site, os dois arquivos ficam em:
  /versao.json                 <- o app consulta este
  /assets/AlertaFuturos.exe    <- e baixa este
Suba SEMPRE os dois juntos: se o JSON anunciar um SHA-256 que não bate com o .exe publicado, os
apps instalados recusam o download (de propósito) e ninguém atualiza.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from atualizacao import DOMINIO_PERMITIDO
from versao import VERSAO


def gerar(exe: Path, novidades: str = "", hoje: date | None = None) -> dict:
    dados = exe.read_bytes()
    if dados[:2] != b"MZ":
        raise SystemExit(f"{exe} não parece um .exe do Windows")
    return {
        "versao": VERSAO,
        "data": (hoje or date.today()).strftime("%d/%m/%Y"),
        "url": DOMINIO_PERMITIDO + "assets/AlertaFuturos.exe",
        "sha256": hashlib.sha256(dados).hexdigest(),
        "tamanho": len(dados),
        "novidades": novidades,
    }


def main() -> None:
    pasta = Path(__file__).with_name("dist")
    info = gerar(pasta / "AlertaFuturos.exe", " ".join(sys.argv[1:]))
    (pasta / "versao.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
