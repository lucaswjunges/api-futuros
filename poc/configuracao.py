"""
Configuração persistida da janela (Opção B — Completa).
=========================================================

Guarda os campos que o cliente pediu na janela (item 4.5-d e Seção 5 da proposta):
limites do RSI, tamanho dos setores A/C, tamanho mínimo da vela 15m, fator de
ajuste do preço-alvo, e a opção de iniciar junto com o Windows.

Ficam de fora deste módulo, de propósito, tudo que precisa de Tkinter ou do
Monitor (rede/UI) — assim dá pra testar carregar/salvar/validar sem display e
sem internet, como o resto da lógica pura do projeto.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from alerta_futuros import LIMITE_PARES, PARES, Parametros

log = logging.getLogger("alerta.configuracao")

NOME_ARQUIVO = "config.json"
NOME_PASTA = "AlertaFuturos"

# Símbolo de Futuros USDⓈ-M: letras e números, como BTCUSDT ou 1000PEPEUSDT.
_SIMBOLO = re.compile(r"^[A-Z0-9]{4,20}$")


@dataclass
class Configuracao:
    parametros: Parametros = field(default_factory=Parametros)
    iniciar_com_windows: bool = False
    # Pares acompanhados, na ordem em que aparecem no quadro. Editável na janela desde
    # 23/09/2026 (o cliente pediu para subir de 8 para 16) — antes disso era fixo no código,
    # e trocar um par exigia gerar um .exe novo.
    pares: list[str] = field(default_factory=lambda: list(PARES))


def pasta_configuracao() -> Path:
    """%APPDATA%\\AlertaFuturos no Windows; ~/.alerta_futuros fora dele (dev/testes/Linux)."""
    base = os.environ.get("APPDATA")
    return Path(base) / NOME_PASTA if base else Path.home() / ".alerta_futuros"


def arquivo_configuracao() -> Path:
    return pasta_configuracao() / NOME_ARQUIVO


def _parametros_de_dict(dados: dict) -> Parametros:
    """Usa só os campos conhecidos de Parametros; ignora campos novos/removidos entre versões
    e mantém o padrão de fábrica pra qualquer campo ausente (config de uma versão mais velha)."""
    validos = {f.name for f in fields(Parametros)}
    return Parametros(**{k: v for k, v in dados.items() if k in validos})


def _pares_de_dict(dados) -> list[str]:
    """Lista de pares vinda do config.json. Config de antes de 23/09/2026 não tem a chave, e
    config estragado pode ter qualquer coisa ali — nos dois casos volta a tabela original de 8
    pares, que é o que o cliente já conhece. Nunca levanta exceção (ver docstring de carregar)."""
    if not isinstance(dados, list):
        return list(PARES)
    pares = [s.strip().upper() for s in dados if isinstance(s, str) and s.strip()]
    return pares if pares and not validar_pares(pares) else list(PARES)


def salvar(config: Configuracao, caminho: Path | None = None) -> None:
    """Grava de forma atômica (escreve em arquivo temporário e substitui): uma queda de energia
    ou o app fechado à força no meio da gravação não deve corromper a configuração salva."""
    caminho = caminho or arquivo_configuracao()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados = {"parametros": asdict(config.parametros), "iniciar_com_windows": config.iniciar_com_windows,
             "pares": list(config.pares)}
    fd, tmp_nome = tempfile.mkstemp(dir=caminho.parent, prefix=".tmp-config-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arq:
            json.dump(dados, arq, indent=2, ensure_ascii=False)
        os.replace(tmp_nome, caminho)
    finally:
        Path(tmp_nome).unlink(missing_ok=True)


def carregar(caminho: Path | None = None) -> Configuracao:
    """Nunca levanta exceção: arquivo ausente ou corrompido volta como configuração padrão
    (o app deve sempre conseguir abrir, mesmo com um config.json quebrado)."""
    caminho = caminho or arquivo_configuracao()
    if not caminho.exists():
        return Configuracao()
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return Configuracao(
            parametros=_parametros_de_dict(dados.get("parametros", {})),
            iniciar_com_windows=bool(dados.get("iniciar_com_windows", False)),
            pares=_pares_de_dict(dados.get("pares")),
        )
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as e:
        log.warning("Configuração salva em %s inválida (%s); usando padrão.", caminho, e)
        return Configuracao()


def validar(p: Parametros) -> list[str]:
    """Mensagens de erro para exibir na janela; lista vazia = tudo válido.
    As faixas aceitam ajustes como os citados na proposta (ex.: RSI 95/3, setores de 25%)."""
    erros = []
    if not (0 < p.rsi_abaixo < p.rsi_acima <= 100):
        erros.append("RSI: o limite “Abaixo” deve ser menor que o “Acima”, e o “Acima” até 100.")
    if not (0 < p.setor_pct < 50):
        erros.append("Tamanho dos setores A/C deve ficar entre 0% e 50% (sobra espaço pro setor B do meio).")
    if p.tamanho_min_pct < 0:
        erros.append("Tamanho mínimo da vela de 15m não pode ser negativo.")
    if p.ajuste_pct <= 0:
        erros.append("Fator de ajuste do preço-alvo deve ser maior que zero.")
    return erros


def validar_pares(pares) -> list[str]:
    """Mensagens de erro do campo de pares; lista vazia = tudo válido. Confere só o que dá pra
    conferir sem rede (quantidade, repetição e formato do símbolo) — se o par não existir na
    Binance, quem avisa é o motor, com o par aparecendo sem dados no quadro."""
    erros = []
    if not pares:
        erros.append("Escolha pelo menos um par para acompanhar.")
        return erros
    if len(pares) > LIMITE_PARES:
        erros.append(f"São {len(pares)} pares; o máximo é {LIMITE_PARES}. Tire "
                     f"{len(pares) - LIMITE_PARES} da lista.")
    repetidos = sorted({s for s in pares if pares.count(s) > 1})
    if repetidos:
        erros.append(f"Par repetido na lista: {', '.join(repetidos)}.")
    invalidos = [s for s in dict.fromkeys(pares) if not _SIMBOLO.match(s)]
    if invalidos:
        erros.append(f"Não parece nome de par da Binance: {', '.join(invalidos)}. "
                     "Use o símbolo como ele aparece lá, por exemplo BTCUSDT.")
    return erros
