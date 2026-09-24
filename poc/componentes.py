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


def fracao_do_intervalo(agora: datetime) -> float:
    """Quanto do intervalo de 15 minutos atual já passou (0.0 logo após :00/:15/:30/:45, perto de
    1.0 logo antes do próximo). É o que a barra de espera mostra com o monitor conectado: o tempo
    até a próxima avaliação — NUNCA a chance de sair um sinal."""
    segundos = (agora.minute % 15) * 60 + agora.second + agora.microsecond / 1e6
    return min(max(segundos / 900.0, 0.0), 1.0)


def contagem_regressiva(agora: datetime, alvo: datetime) -> str:
    """'mm:ss' até `alvo` (nunca negativo)."""
    restante = max(0, int((alvo - agora).total_seconds()))
    return f"{restante // 60:02d}:{restante % 60:02d}"


def altura_visivel_das_linhas(n_pares: int, altura_linha: int, rodape: int,
                              altura_max: int | None) -> tuple[int, bool]:
    """(altura em px da área de linhas, precisa de rolagem?) do quadro de situação.

    Com o teto de 16 pares (pedido do cliente em 23/09/2026) o quadro dobra de altura e passa a
    caber em umas telas e não em outras. Quando não cabe, a área encolhe até `altura_max` e
    ganha rolagem — o que NÃO pode acontecer é a janela crescer além da tela e levar os botões
    Iniciar/Parar pra fora do alcance do cliente. Sempre sobra um número inteiro de linhas:
    meia linha cortada na borda inferior parece defeito."""
    natural = altura_linha * max(n_pares, 0) + rodape
    if altura_max is None or natural <= altura_max:
        return natural, False
    # Rolando, a área termina exatamente no fim de uma linha e SEM o respiro do rodapé: aqueles
    # px a mais seriam preenchidos pelo topo da linha seguinte, e uma fatia de 8 px de linha
    # aparecendo na borda parece quadro quebrado, não conteúdo que continua.
    return max(1, altura_max // altura_linha) * altura_linha, True


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


class PainelPares(tk.Frame):
    """Quadro de situação: uma linha por par com o RSI(2) como marcador num eixo (faixas "Abaixo"
    e "Acima" tingidas), o setor da vela de 15m, o último sinal (W/Z + alvo), o fechamento e a
    hora. O cabeçalho carrega o mesmo eixo com os números dos limites, alinhado às linhas — é a
    legenda e a régua ao mesmo tempo.

    São dois Canvas e não um só (mudança de 23/09/2026, junto com o teto de 16 pares): o
    cabeçalho fica parado e só as linhas rolam. Com 8 pares nada rolava e o cabeçalho ficava
    naturalmente no topo; com 16 numa tela baixa, rolar um Canvas único levaria a régua do RSI
    junto e o cliente perderia justamente a legenda que explica o eixo."""

    LARGURA, MARGEM = 588, 20  # px de projeto: conteúdo e margem interna (painel vai de borda a borda)
    ALTURA_CABECALHO, ALTURA_LINHA, RODAPE = 42, 25, 8
    LARGURA_BARRA = 12         # barra de rolagem, só aparece quando as linhas não cabem
    X_PAR = 0                  # âncora w
    X_EIXO, L_EIXO = 92, 160   # início e comprimento do eixo de RSI
    X_RSI = 306                # âncora e
    X_SETOR = 340              # âncora center
    X_SINAL = 456              # âncora e
    X_FECH = 538               # âncora e
    X_HORA = 588               # âncora e
    RAIO_MARCADOR, ESPESSURA_EIXO = 5, 6

    def __init__(self, master, tema: Tema, pares, rsi_abaixo: float, rsi_acima: float,
                 altura_max: int | None = None):
        super().__init__(master, bg=PAINEL)
        self.tema = tema
        px = tema.px
        self.margem = px(self.MARGEM)
        self.pares = list(pares)
        self.largura_total = px(self.LARGURA) + 2 * self.margem
        self.altura_natural = px(self.ALTURA_LINHA) * len(self.pares) + px(self.RODAPE)
        altura_linhas, self.rolagem = altura_visivel_das_linhas(
            len(self.pares), px(self.ALTURA_LINHA), px(self.RODAPE), altura_max)

        self.cabecalho = tk.Canvas(self, width=self.largura_total, height=px(self.ALTURA_CABECALHO),
                                   bg=PAINEL, highlightthickness=0, bd=0)
        self.corpo = tk.Canvas(self, width=self.largura_total, height=altura_linhas,
                               bg=PAINEL, highlightthickness=0, bd=0)
        self.cabecalho.grid(row=0, column=0, sticky="ew")
        self.corpo.grid(row=1, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.rsi_abaixo, self.rsi_acima = rsi_abaixo, rsi_acima
        self._linhas: dict[str, dict[str, int]] = {}
        self._montar()
        if self.rolagem:
            self._ligar_rolagem(altura_linhas)

    # coordenadas

    def _x(self, x_projeto: float) -> float:
        return self.margem + self.tema.px(x_projeto)

    def _x_rsi(self, rsi: float) -> float:
        return posicao_no_eixo(rsi, self._x(self.X_EIXO), self.tema.px(self.L_EIXO))

    # montagem

    def _montar(self) -> None:
        px, tema = self.tema.px, self.tema
        fraco, apagado = tema.texto(9), tema.numeros(8)
        cab = self.cabecalho
        y_nomes, y_numeros, y_eixo = px(12), px(27), px(37)
        cab.create_text(self._x(self.X_PAR), y_nomes, text="Par", anchor="w", fill=TEXTO_FRACO, font=fraco)
        cab.create_text(self._x(self.X_EIXO), y_nomes, text="RSI(2)", anchor="w", fill=TEXTO_FRACO, font=fraco)
        cab.create_text(self._x(self.X_SETOR), y_nomes, text="Setor", anchor="center", fill=TEXTO_FRACO, font=fraco)
        cab.create_text(self._x(self.X_SINAL), y_nomes, text="Sinal", anchor="e", fill=TEXTO_FRACO, font=fraco)
        cab.create_text(self._x(self.X_FECH), y_nomes, text="Fechamento", anchor="e", fill=TEXTO_FRACO, font=fraco)
        cab.create_text(self._x(self.X_HORA), y_nomes, text="Hora", anchor="e", fill=TEXTO_FRACO, font=fraco)

        # régua do cabeçalho: os dois limites sobre o mesmo eixo das linhas (as pontas são 0 e 100;
        # escrever isso colidia com os limites, que ficam justamente perto das pontas)
        self._legenda = {
            "abaixo": cab.create_text(0, y_numeros, text="", anchor="center", fill=VERMELHO, font=apagado),
            "acima": cab.create_text(0, y_numeros, text="", anchor="center", fill=VERDE, font=apagado),
        }
        self._legenda.update(self._eixo(cab, y_eixo, px(4)))

        y = 0
        for simbolo in self.pares:
            self._linhas[simbolo] = self._linha(simbolo, y + px(self.ALTURA_LINHA) / 2)
            y += px(self.ALTURA_LINHA)
        self.definir_faixas(self.rsi_abaixo, self.rsi_acima)

    def _ligar_rolagem(self, altura_visivel: int) -> None:
        """Barra de rolagem + roda do mouse, só quando as linhas não cabem na altura disponível."""
        px = self.tema.px
        self.corpo.configure(scrollregion=(0, 0, self.largura_total, self.altura_natural))
        self.barra = tk.Scrollbar(self, orient="vertical", command=self.corpo.yview,
                                  width=px(self.LARGURA_BARRA), bg=BORDA, troughcolor=FUNDO,
                                  activebackground=TEXTO_FRACO, borderwidth=0, highlightthickness=0)
        self.barra.grid(row=1, column=1, sticky="ns")
        self.corpo.configure(yscrollcommand=self.barra.set)
        # <MouseWheel> é Windows/macOS; Button-4/5 é X11 (o Ubuntu daqui). Ligados só no corpo
        # pra roda do mouse sobre os campos de cima continuar fazendo o que sempre fez.
        self.corpo.bind("<MouseWheel>", self._roda_mouse)
        self.corpo.bind("<Button-4>", lambda _e: self.corpo.yview_scroll(-1, "units"))
        self.corpo.bind("<Button-5>", lambda _e: self.corpo.yview_scroll(1, "units"))
        self.corpo.configure(yscrollincrement=px(self.ALTURA_LINHA))

    def _roda_mouse(self, evento) -> None:
        self.corpo.yview_scroll(-1 if evento.delta > 0 else 1, "units")

    def _eixo(self, canvas: tk.Canvas, y: float, espessura: int) -> dict[str, int]:
        """Trilho neutro + as duas faixas coloridas (coordenadas ajustadas em definir_faixas)."""
        x0, x1 = self._x(self.X_EIXO), self._x(self.X_EIXO + self.L_EIXO)
        return {
            "trilho": canvas.create_line(x0, y, x1, y, fill=TRILHO, width=espessura, capstyle="round"),
            "faixa_abaixo": canvas.create_line(x0, y, x0, y, fill=VERMELHO_FAIXA, width=espessura, capstyle="round"),
            "faixa_acima": canvas.create_line(x1, y, x1, y, fill=VERDE_FAIXA, width=espessura, capstyle="round"),
        }

    def _linha(self, simbolo: str, y: float) -> dict[str, int]:
        px, tema, corpo = self.tema.px, self.tema, self.corpo
        meia = px(self.ALTURA_LINHA) / 2
        r = px(self.RAIO_MARCADOR)
        itens = {
            "fundo": corpo.create_rectangle(0, y - meia, self.largura_total, y + meia, fill="", outline=""),
            "par": corpo.create_text(self._x(self.X_PAR), y, text=simbolo, anchor="w", fill=TEXTO_FRACO,
                                     font=tema.numeros(10, "bold")),
        }
        itens.update(self._eixo(corpo, y, px(self.ESPESSURA_EIXO)))
        itens["marcador"] = corpo.create_oval(-r, y - r, r, y + r, fill=TEXTO, outline=PAINEL,
                                              width=px(2), state="hidden")
        itens["rsi"] = corpo.create_text(self._x(self.X_RSI), y, text="—", anchor="e", fill=TEXTO_APAGADO,
                                         font=tema.numeros(10))
        itens["setor"] = corpo.create_text(self._x(self.X_SETOR), y, text="—", anchor="center", fill=TEXTO_APAGADO,
                                           font=tema.numeros(10))
        itens["sinal"] = corpo.create_text(self._x(self.X_SINAL), y, text="", anchor="e", fill=TEXTO,
                                           font=tema.numeros(10, "bold"))
        itens["fechamento"] = corpo.create_text(self._x(self.X_FECH), y, text="—", anchor="e", fill=TEXTO_APAGADO,
                                                font=tema.numeros(10))
        itens["hora"] = corpo.create_text(self._x(self.X_HORA), y, text="—", anchor="e", fill=TEXTO_APAGADO,
                                          font=tema.numeros(9))
        return itens

    # atualização

    def definir_faixas(self, rsi_abaixo: float, rsi_acima: float) -> None:
        """Reposiciona as faixas "Abaixo"/"Acima" (cabeçalho e todas as linhas) — chamado a cada
        edição válida dos campos de RSI, pra régua mostrar o que os números significam."""
        self.rsi_abaixo, self.rsi_acima = rsi_abaixo, rsi_acima
        x0, x1 = self._x(self.X_EIXO), self._x(self.X_EIXO + self.L_EIXO)
        x_abaixo, x_acima = self._x_rsi(rsi_abaixo), self._x_rsi(rsi_acima)
        cab = self.cabecalho
        cab.itemconfigure(self._legenda["abaixo"], text=formatar_num(rsi_abaixo, 0))
        cab.itemconfigure(self._legenda["acima"], text=formatar_num(rsi_acima, 0))
        y_numeros = cab.coords(self._legenda["abaixo"])[1]
        cab.coords(self._legenda["abaixo"], x_abaixo, y_numeros)
        cab.coords(self._legenda["acima"], x_acima, y_numeros)
        for canvas, itens in ((cab, self._legenda), *((self.corpo, i) for i in self._linhas.values())):
            y = canvas.coords(itens["trilho"])[1]
            canvas.coords(itens["faixa_abaixo"], x0, y, x_abaixo, y)
            canvas.coords(itens["faixa_acima"], x_acima, y, x1, y)
            canvas.itemconfigure(itens["faixa_abaixo"], state="normal" if x_abaixo - x0 >= 1 else "hidden")
            canvas.itemconfigure(itens["faixa_acima"], state="normal" if x1 - x_acima >= 1 else "hidden")

    def atualizar(self, av: Avaliacao) -> None:
        itens = self._linhas.get(av.simbolo)
        if itens is None:
            return
        px, corpo = self.tema.px, self.corpo
        r = px(self.RAIO_MARCADOR)
        y = corpo.coords(itens["trilho"])[1]
        cor_faixa = VERDE if av.faixa == "ACIMA" else VERMELHO if av.faixa == "ABAIXO" else TEXTO
        corpo.itemconfigure(itens["par"], fill=TEXTO)
        if av.rsi is None:
            corpo.itemconfigure(itens["marcador"], state="hidden")
            corpo.itemconfigure(itens["rsi"], text="—", fill=TEXTO_APAGADO)
        else:
            x = self._x_rsi(av.rsi)
            corpo.coords(itens["marcador"], x - r, y - r, x + r, y + r)
            corpo.itemconfigure(itens["marcador"], fill=cor_faixa, state="normal")
            corpo.itemconfigure(itens["rsi"], text=formatar_num(av.rsi), fill=cor_faixa)
        if av.setor:
            corpo.itemconfigure(itens["setor"], text=av.setor, fill=TEXTO)
        else:
            corpo.itemconfigure(itens["setor"], text="pequena", fill=TEXTO_APAGADO)
        if av.sinal:
            cor, alvo = (VERDE, "W") if av.sinal == "X" else (VERMELHO, "Z")
            corpo.itemconfigure(itens["sinal"], text=f"{alvo} {av.alvo_texto}", fill=cor)
            corpo.itemconfigure(itens["fundo"], fill=VERDE_LINHA if av.sinal == "X" else VERMELHO_LINHA)
        else:
            # "sem sinal" escrito, e não a célula vazia: vazia parece que o par nem foi avaliado. É a
            # resposta à dúvida mais comum no teste de usabilidade (21/09/2026) — "passou o
            # fechamento e não apareceu nada, travou?".
            corpo.itemconfigure(itens["sinal"], text="sem sinal", fill=TEXTO_APAGADO)
            corpo.itemconfigure(itens["fundo"], fill="")
        corpo.itemconfigure(itens["fechamento"], text=av.fechamento_texto, fill=TEXTO)
        try:
            hora = datetime.fromtimestamp((av.abertura_ms + MS_5M) / 1000).strftime("%H:%M")
        except (OverflowError, OSError, ValueError):  # nunca deixa uma falha de formatação derrubar a janela
            hora = "—"
        corpo.itemconfigure(itens["hora"], text=hora, fill=TEXTO_FRACO)


class BarraEspera(tk.Canvas):
    """Barra fina logo abaixo do status: mostra que o app está trabalhando mesmo quando o quadro
    não muda (definido no teste de usabilidade de 21/09/2026 e reintroduzido em 24/09/2026).

    - conectando/reconectando: um trecho dourado corre de um lado pro outro (animação);
    - conectado: a barra enche em ciano ao longo dos 15 minutos até a próxima avaliação;
    - parado: só o trilho.
    "Reduzir movimento" (na janela) troca a animação por barra parada — o texto de status continua
    dizendo a mesma coisa, então nada de informação depende do movimento."""

    ALTURA, PASSO_MS, TRECHO = 5, 40, 0.28  # px de projeto; intervalo da animação; largura do trecho

    def __init__(self, master, tema: Tema):
        px = tema.px
        super().__init__(master, height=px(self.ALTURA), bg=FUNDO, highlightthickness=0, bd=0)
        self._trilho = self.create_rectangle(0, 0, 0, 0, fill=TRILHO, outline="")
        self._barra = self.create_rectangle(0, 0, 0, 0, fill=CIANO, outline="")
        self.modo = "parado"
        self._fracao = 0.0
        self._fase = 0.0
        self._job: str | None = None
        self.bind("<Configure>", lambda _e: self._desenhar())

    def animar(self) -> None:
        if self.modo == "animando":
            return
        self.modo = "animando"
        self._tick()

    def progresso(self, fracao: float) -> None:
        self._parar_animacao()
        self.modo, self._fracao = "progresso", min(max(fracao, 0.0), 1.0)
        self._desenhar()

    def parado(self) -> None:
        self._parar_animacao()
        self.modo = "parado"
        self._desenhar()

    def _parar_animacao(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _tick(self) -> None:
        self._job = None
        if self.modo != "animando":
            return
        self._fase = (self._fase + 0.018) % (1.0 + self.TRECHO)
        self._desenhar()
        self._job = self.after(self.PASSO_MS, self._tick)

    def _desenhar(self) -> None:
        largura, altura = self.winfo_width(), int(self.cget("height"))
        if largura <= 1:
            return
        self.coords(self._trilho, 0, 0, largura, altura)
        if self.modo == "animando":
            x0 = (self._fase - self.TRECHO) * largura
            self.coords(self._barra, max(0, x0), 0, min(largura, x0 + self.TRECHO * largura), altura)
            self.itemconfigure(self._barra, fill=OURO, state="normal")
        elif self.modo == "progresso":
            self.coords(self._barra, 0, 0, self._fracao * largura, altura)
            self.itemconfigure(self._barra, fill=CIANO, state="normal")
        else:
            self.itemconfigure(self._barra, state="hidden")

    def destroy(self) -> None:
        self._parar_animacao()
        super().destroy()
