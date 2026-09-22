"""
Componentes desenhados da janela (Canvas): indicador de estado, diagrama da vela de 15 minutos e o
quadro de situação dos pares. Só desenho — nenhuma regra de negócio mora aqui (RSI, setor e
cruzamento continuam só em alerta_futuros.py). As funções puras do topo (alturas_setores,
posicao_no_eixo, estado_do_monitor, proxima_avaliacao) ficam fora das classes de propósito, pra
serem testadas sem um tk.Tk() real (ver test_componentes.py), como o resto da lógica do projeto.

Por que desenhar em vez de usar ttk.Treeview (versão anterior, até 22/09/2026): o cliente não é
técnico, e "RSI 47,3" como texto numa tabela não diz nada — um marcador andando num eixo cujas
pontas estão tingidas de vermelho ("Abaixo") e verde ("Acima") mostra o quanto falta pra condição
1 ficar verdadeira. A cor só aparece quando a condição É verdadeira: marcador verde/vermelho na
faixa, e a linha inteira tingida quando o último fechamento deu sinal.
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta

from alerta_futuros import MS_5M, Avaliacao, formatar_num
from tema import (
    BORDA, CAMPO, CIANO, FUNDO, OURO, PAINEL, TEXTO, TEXTO_APAGADO, TEXTO_FRACO, TRILHO,
    VERDE, VERDE_FAIXA, VERDE_LINHA, VERMELHO, VERMELHO_FAIXA, VERMELHO_LINHA, Tema,
)

# ───────────────────────────── lógica pura (testável) ─────────────────────────────


def alturas_setores(altura: int, setor_pct: float) -> tuple[int, int, int]:
    """Altura em px dos setores A (topo), B (meio) e C (base) de uma vela desenhada com `altura`
    px. Mesma definição de setor_vela15(): A e C ocupam setor_pct % de cada ponta, B é o que
    sobra. Sempre soma `altura` exatamente; percentuais fora de 0–50 são grampeados."""
    pct = min(max(setor_pct, 0.0), 50.0)
    ponta = int(round(altura * pct / 100.0))
    return ponta, altura - 2 * ponta, ponta


def posicao_no_eixo(rsi: float, x0: float, largura: float) -> float:
    """x do marcador de um RSI (0–100) num eixo que começa em x0 e mede `largura` px."""
    return x0 + largura * min(max(rsi, 0.0), 100.0) / 100.0


CORES_ESTADO = {
    "parado": TEXTO_APAGADO,
    "conectando": OURO,
    "conectado": CIANO,
    "reconectando": OURO,
    "encerrado": VERMELHO,
}


def estado_do_monitor(iniciado: bool, motor_vivo: bool, conectado: bool, reconexoes: int) -> tuple[str, str]:
    """(chave em CORES_ESTADO, texto do indicador) a partir do que o Monitor expõe."""
    if not iniciado:
        return "parado", "Parado"
    if not motor_vivo:
        return "encerrado", "Encerrado"
    if conectado:
        return "conectado", "Conectado"
    if reconexoes:
        return "reconectando", f"Reconectando… (tentativa {reconexoes})"
    return "conectando", "Conectando…"


def proxima_avaliacao(agora: datetime) -> datetime:
    """Próximo fechamento que também fecha uma vela de 15m (:00, :15, :30, :45) — item 4.5-b:
    é só nesses instantes que o quadro muda, então a janela avisa o horário em vez de deixar o
    cliente achando que travou nos primeiros minutos."""
    base = agora.replace(second=0, microsecond=0)
    minutos = (base.minute // 15 + 1) * 15
    return base.replace(minute=0) + timedelta(minutes=minutos)


# ───────────────────────────── widgets ─────────────────────────────


class Indicador(tk.Frame):
    """Bolinha colorida + texto ("Conectado", "Reconectando…"), no cabeçalho da janela."""

    def __init__(self, master, tema: Tema):
        super().__init__(master, bg=FUNDO)
        d = tema.px(10)
        self._canvas = tk.Canvas(self, width=d, height=d, bg=FUNDO, highlightthickness=0, bd=0)
        self._ponto = self._canvas.create_oval(1, 1, d - 1, d - 1, fill=CORES_ESTADO["parado"], outline="")
        self._canvas.pack(side="left", padx=(0, tema.px(8)))
        self.rotulo = tk.Label(self, text="Parado", bg=FUNDO, fg=TEXTO_FRACO, font=tema.texto(10))
        self.rotulo.pack(side="left")
        self.chave = "parado"

    def definir(self, chave: str, texto: str) -> None:
        if (chave, texto) == (self.chave, self.rotulo.cget("text")):
            return
        self.chave = chave
        self._canvas.itemconfigure(self._ponto, fill=CORES_ESTADO[chave])
        self.rotulo.configure(text=texto, fg=TEXTO if chave == "conectado" else TEXTO_FRACO)


class DiagramaVela15(tk.Canvas):
    """Vela de 15 minutos com os setores A (topo), B (meio) e C (base) na proporção do campo
    "setores" — a explicação visual do que o documento do cliente chama de setor. Redesenhada a
    cada tecla digitada no campo, pra mostrar o que o número significa."""

    LARGURA, ALTURA_CORPO, PAVIO, ROTULOS = 24, 56, 8, 22  # px de projeto

    def __init__(self, master, tema: Tema, setor_pct: float):
        self.tema = tema
        px = tema.px
        self.largura, self.corpo, self.pavio = px(self.LARGURA), px(self.ALTURA_CORPO), px(self.PAVIO)
        super().__init__(master, width=self.largura + px(self.ROTULOS), height=self.corpo + 2 * self.pavio,
                         bg=FUNDO, highlightthickness=0, bd=0)
        self.atualizar(setor_pct)

    def atualizar(self, setor_pct: float) -> None:
        self.delete("all")
        px = self.tema.px
        x0, x1, xc = 0, self.largura, self.largura / 2
        y0, y1 = self.pavio, self.pavio + self.corpo
        a, b, c = alturas_setores(self.corpo, setor_pct)
        self.create_line(xc, 0, xc, y0, fill=BORDA, width=px(2))
        self.create_line(xc, y1, xc, y1 + self.pavio, fill=BORDA, width=px(2))
        self.create_rectangle(x0, y0, x1, y0 + a, fill=VERDE_FAIXA, outline="")
        self.create_rectangle(x0, y0 + a, x1, y0 + a + b, fill=CAMPO, outline="")
        self.create_rectangle(x0, y1 - c, x1, y1, fill=VERMELHO_FAIXA, outline="")
        self.create_rectangle(x0, y0, x1, y1, outline=BORDA, width=1)
        xr, fonte = x1 + px(9), self.tema.numeros(9)
        if a:
            self.create_text(xr, y0 + a / 2, text="A", anchor="w", fill=TEXTO_FRACO, font=fonte)
        if b:
            self.create_text(xr, y0 + a + b / 2, text="B", anchor="w", fill=TEXTO_FRACO, font=fonte)
        if c:
            self.create_text(xr, y1 - c / 2, text="C", anchor="w", fill=TEXTO_FRACO, font=fonte)


class PainelPares(tk.Canvas):
    """Quadro de situação: uma linha por par com o RSI(2) como marcador num eixo (faixas "Abaixo"
    e "Acima" tingidas), o setor da vela de 15m, o último sinal (W/Z + alvo), o fechamento e a
    hora. O cabeçalho carrega o mesmo eixo com os números dos limites, alinhado às linhas — é a
    legenda e a régua ao mesmo tempo."""

    LARGURA, MARGEM = 588, 20  # px de projeto: conteúdo e margem interna (painel vai de borda a borda)
    ALTURA_CABECALHO, ALTURA_LINHA, RODAPE = 42, 25, 8
    X_PAR = 0                  # âncora w
    X_EIXO, L_EIXO = 92, 160   # início e comprimento do eixo de RSI
    X_RSI = 306                # âncora e
    X_SETOR = 340              # âncora center
    X_SINAL = 456              # âncora e
    X_FECH = 538               # âncora e
    X_HORA = 588               # âncora e
    RAIO_MARCADOR, ESPESSURA_EIXO = 5, 6

    def __init__(self, master, tema: Tema, pares, rsi_abaixo: float, rsi_acima: float):
        self.tema = tema
        px = tema.px
        self.margem = px(self.MARGEM)
        self.pares = list(pares)
        self.largura_total = px(self.LARGURA) + 2 * self.margem
        altura = px(self.ALTURA_CABECALHO) + px(self.ALTURA_LINHA) * len(self.pares) + px(self.RODAPE)
        super().__init__(master, width=self.largura_total, height=altura, bg=PAINEL, highlightthickness=0, bd=0)
        self.rsi_abaixo, self.rsi_acima = rsi_abaixo, rsi_acima
        self._linhas: dict[str, dict[str, int]] = {}
        self._montar()

    # coordenadas

    def _x(self, x_projeto: float) -> float:
        return self.margem + self.tema.px(x_projeto)

    def _x_rsi(self, rsi: float) -> float:
        return posicao_no_eixo(rsi, self._x(self.X_EIXO), self.tema.px(self.L_EIXO))

    # montagem

    def _montar(self) -> None:
        px, tema = self.tema.px, self.tema
        fraco, apagado = tema.texto(9), tema.numeros(8)
        y_nomes, y_numeros, y_eixo = px(12), px(27), px(37)
        self.create_text(self._x(self.X_PAR), y_nomes, text="Par", anchor="w", fill=TEXTO_FRACO, font=fraco)
        self.create_text(self._x(self.X_EIXO), y_nomes, text="RSI(2)", anchor="w", fill=TEXTO_FRACO, font=fraco)
        self.create_text(self._x(self.X_SETOR), y_nomes, text="Setor", anchor="center", fill=TEXTO_FRACO, font=fraco)
        self.create_text(self._x(self.X_SINAL), y_nomes, text="Sinal", anchor="e", fill=TEXTO_FRACO, font=fraco)
        self.create_text(self._x(self.X_FECH), y_nomes, text="Fechamento", anchor="e", fill=TEXTO_FRACO, font=fraco)
        self.create_text(self._x(self.X_HORA), y_nomes, text="Hora", anchor="e", fill=TEXTO_FRACO, font=fraco)

        # régua do cabeçalho: os dois limites sobre o mesmo eixo das linhas (as pontas são 0 e 100;
        # escrever isso colidia com os limites, que ficam justamente perto das pontas)
        self._legenda = {
            "abaixo": self.create_text(0, y_numeros, text="", anchor="center", fill=VERMELHO, font=apagado),
            "acima": self.create_text(0, y_numeros, text="", anchor="center", fill=VERDE, font=apagado),
        }
        self._legenda.update(self._eixo(y_eixo, px(4)))

        y = px(self.ALTURA_CABECALHO)
        for simbolo in self.pares:
            self._linhas[simbolo] = self._linha(simbolo, y + px(self.ALTURA_LINHA) / 2)
            y += px(self.ALTURA_LINHA)
        self.definir_faixas(self.rsi_abaixo, self.rsi_acima)

    def _eixo(self, y: float, espessura: int) -> dict[str, int]:
        """Trilho neutro + as duas faixas coloridas (coordenadas ajustadas em definir_faixas)."""
        x0, x1 = self._x(self.X_EIXO), self._x(self.X_EIXO + self.L_EIXO)
        return {
            "trilho": self.create_line(x0, y, x1, y, fill=TRILHO, width=espessura, capstyle="round"),
            "faixa_abaixo": self.create_line(x0, y, x0, y, fill=VERMELHO_FAIXA, width=espessura, capstyle="round"),
            "faixa_acima": self.create_line(x1, y, x1, y, fill=VERDE_FAIXA, width=espessura, capstyle="round"),
        }

    def _linha(self, simbolo: str, y: float) -> dict[str, int]:
        px, tema = self.tema.px, self.tema
        meia = px(self.ALTURA_LINHA) / 2
        r = px(self.RAIO_MARCADOR)
        itens = {
            "fundo": self.create_rectangle(0, y - meia, self.largura_total, y + meia, fill="", outline=""),
            "par": self.create_text(self._x(self.X_PAR), y, text=simbolo, anchor="w", fill=TEXTO_FRACO,
                                    font=tema.numeros(10, "bold")),
        }
        itens.update(self._eixo(y, px(self.ESPESSURA_EIXO)))
        itens["marcador"] = self.create_oval(-r, y - r, r, y + r, fill=TEXTO, outline=PAINEL,
                                             width=px(2), state="hidden")
        itens["rsi"] = self.create_text(self._x(self.X_RSI), y, text="—", anchor="e", fill=TEXTO_APAGADO,
                                        font=tema.numeros(10))
        itens["setor"] = self.create_text(self._x(self.X_SETOR), y, text="—", anchor="center", fill=TEXTO_APAGADO,
                                          font=tema.numeros(10))
        itens["sinal"] = self.create_text(self._x(self.X_SINAL), y, text="", anchor="e", fill=TEXTO,
                                          font=tema.numeros(10, "bold"))
        itens["fechamento"] = self.create_text(self._x(self.X_FECH), y, text="—", anchor="e", fill=TEXTO_APAGADO,
                                               font=tema.numeros(10))
        itens["hora"] = self.create_text(self._x(self.X_HORA), y, text="—", anchor="e", fill=TEXTO_APAGADO,
                                         font=tema.numeros(9))
        return itens

    # atualização

    def definir_faixas(self, rsi_abaixo: float, rsi_acima: float) -> None:
        """Reposiciona as faixas "Abaixo"/"Acima" (cabeçalho e todas as linhas) — chamado a cada
        edição válida dos campos de RSI, pra régua mostrar o que os números significam."""
        self.rsi_abaixo, self.rsi_acima = rsi_abaixo, rsi_acima
        x0, x1 = self._x(self.X_EIXO), self._x(self.X_EIXO + self.L_EIXO)
        x_abaixo, x_acima = self._x_rsi(rsi_abaixo), self._x_rsi(rsi_acima)
        self.itemconfigure(self._legenda["abaixo"], text=formatar_num(rsi_abaixo, 0))
        self.itemconfigure(self._legenda["acima"], text=formatar_num(rsi_acima, 0))
        y_numeros = self.coords(self._legenda["abaixo"])[1]
        self.coords(self._legenda["abaixo"], x_abaixo, y_numeros)
        self.coords(self._legenda["acima"], x_acima, y_numeros)
        for itens in (self._legenda, *self._linhas.values()):
            y = self.coords(itens["trilho"])[1]
            self.coords(itens["faixa_abaixo"], x0, y, x_abaixo, y)
            self.coords(itens["faixa_acima"], x_acima, y, x1, y)
            self.itemconfigure(itens["faixa_abaixo"], state="normal" if x_abaixo - x0 >= 1 else "hidden")
            self.itemconfigure(itens["faixa_acima"], state="normal" if x1 - x_acima >= 1 else "hidden")

    def atualizar(self, av: Avaliacao) -> None:
        itens = self._linhas.get(av.simbolo)
        if itens is None:
            return
        px = self.tema.px
        r = px(self.RAIO_MARCADOR)
        y = self.coords(itens["trilho"])[1]
        cor_faixa = VERDE if av.faixa == "ACIMA" else VERMELHO if av.faixa == "ABAIXO" else TEXTO
        self.itemconfigure(itens["par"], fill=TEXTO)
        if av.rsi is None:
            self.itemconfigure(itens["marcador"], state="hidden")
            self.itemconfigure(itens["rsi"], text="—", fill=TEXTO_APAGADO)
        else:
            x = self._x_rsi(av.rsi)
            self.coords(itens["marcador"], x - r, y - r, x + r, y + r)
            self.itemconfigure(itens["marcador"], fill=cor_faixa, state="normal")
            self.itemconfigure(itens["rsi"], text=formatar_num(av.rsi), fill=cor_faixa)
        if av.setor:
            self.itemconfigure(itens["setor"], text=av.setor, fill=TEXTO)
        else:
            self.itemconfigure(itens["setor"], text="pequena", fill=TEXTO_APAGADO)
        if av.sinal:
            cor, alvo = (VERDE, "W") if av.sinal == "X" else (VERMELHO, "Z")
            self.itemconfigure(itens["sinal"], text=f"{alvo} {av.alvo_texto}", fill=cor)
            self.itemconfigure(itens["fundo"], fill=VERDE_LINHA if av.sinal == "X" else VERMELHO_LINHA)
        else:
            self.itemconfigure(itens["sinal"], text="")
            self.itemconfigure(itens["fundo"], fill="")
        self.itemconfigure(itens["fechamento"], text=av.fechamento_texto, fill=TEXTO)
        try:
            hora = datetime.fromtimestamp((av.abertura_ms + MS_5M) / 1000).strftime("%H:%M")
        except (OverflowError, OSError, ValueError):  # nunca deixa uma falha de formatação derrubar a janela
            hora = "—"
        self.itemconfigure(itens["hora"], text=hora, fill=TEXTO_FRACO)
