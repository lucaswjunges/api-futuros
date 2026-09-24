"""
Leitura e validação dos campos da janela — lógica pura, sem Tkinter.
=====================================================================

Fica de fora deste módulo tudo que depende de display: assim a conversão de
texto digitado para os parâmetros do motor (e os erros amigáveis de cada
campo) são testáveis sem abrir janela nenhuma, do mesmo jeito que o resto da
lógica pura do projeto (RSI, setores, cruzamento).
"""

from __future__ import annotations

import re
from dataclasses import replace

from alerta_futuros import Parametros

# Ordem em que os campos aparecem na janela (Seção 5 da proposta, Opção B).
CAMPOS = ("rsi_acima", "rsi_abaixo", "setor_pct", "tamanho_min_pct", "ajuste_pct")

# Separadores aceitos no campo de pares: vírgula, ponto e vírgula, barra ou qualquer espaço.
# O cliente pode colar a lista do jeito que tiver na mão (de um e-mail, de uma planilha) sem
# ter que arrumar a pontuação — e "btc usdt" separado por espaço vira dois pares, não um.
_SEPARADORES = re.compile(r"[,;/\s]+")

ROTULOS = {
    "rsi_acima": "RSI — limite Acima",
    "rsi_abaixo": "RSI — limite Abaixo",
    "setor_pct": "Tamanho dos setores A/C",
    "tamanho_min_pct": "Tamanho mínimo da vela 15m",
    "ajuste_pct": "Fator de ajuste do preço-alvo",
}


class CampoInvalido(ValueError):
    """Erro de um campo específico — a mensagem já vem pronta pra mostrar na janela. `campo` é a
    chave em CAMPOS do campo que falhou (None quando o erro não é de um campo só), pra janela
    poder destacar o campo em vermelho além de mostrar a mensagem."""

    def __init__(self, mensagem: str, campo: str | None = None):
        super().__init__(mensagem)
        self.campo = campo


def texto_do_parametro(valor: float) -> str:
    """90.0 -> '90' · 0.02 -> '0,02' (padrão brasileiro, sem zeros à direita)."""
    texto = f"{valor:.10f}".rstrip("0").rstrip(".")
    return (texto or "0").replace(".", ",")


def textos_de(p: Parametros) -> dict[str, str]:
    """Os 5 campos editáveis de Parametros, como texto pronto pra preencher a janela."""
    return {campo: texto_do_parametro(getattr(p, campo)) for campo in CAMPOS}


def _numero(texto: str, campo: str) -> float:
    bruto = texto.strip().replace(".", "").replace(",", ".") if "," in texto else texto.strip()
    try:
        return float(bruto)
    except ValueError:
        raise CampoInvalido(f"{ROTULOS[campo]}: “{texto}” não é um número válido.", campo) from None


def parametros_dos_textos(textos: dict[str, str], base: Parametros) -> Parametros:
    """Converte o texto digitado nos 5 campos em um novo Parametros, mantendo em `base` os
    campos que a janela não edita (rsi_periodo, popup_segundos, velas_aquecimento).
    Aceita tanto vírgula quanto ponto decimal (ex.: "0,020" ou "0.020")."""
    faltando = [c for c in CAMPOS if c not in textos]
    if faltando:
        raise CampoInvalido(f"Campo ausente no formulário: {', '.join(ROTULOS[c] for c in faltando)}.")
    valores = {campo: _numero(textos[campo], campo) for campo in CAMPOS}
    return replace(base, **valores)


def pares_do_texto(texto: str) -> list[str]:
    """"btcusdt, eth usdt-perp" -> ['BTCUSDT', 'ETHUSDT-PERP'] — só separa e normaliza para
    maiúsculas, sem julgar se o par existe (isso é papel de configuracao.validar_pares, que é
    quem monta a mensagem de erro da janela). Duplicatas são preservadas de propósito: quem
    valida precisa enxergá-las para poder avisar."""
    return [pedaco.upper() for pedaco in _SEPARADORES.split(texto.strip()) if pedaco]


def texto_dos_pares(pares) -> str:
    """Lista de pares como o cliente vê e edita no campo da janela."""
    return " ".join(pares)
