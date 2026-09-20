"""
PoC — Alertas de Trading para Binance Futuros USDⓈ-M
====================================================

Somente dados PÚBLICOS: sem conta, sem API key, sem senha e sem envio de ordens.

Fluxo:
  1. REST  (fapi.binance.com)         -> histórico de velas 5m p/ aquecer o RSI de Wilder
  2. WebSocket (fstream.binance.com/market) -> klines 5m e 15m em tempo real (8 pares, 1 conexão)
  3. A cada vela de 5m FECHADA (k.x == true), o RSI(2) de Wilder é sempre atualizado (precisa de
     todo fechamento de 5m pra ficar correto — pular um deixaria o valor divergente do gráfico).
     A CAPTAÇÃO (avaliação completa + pop-up + registro) só acontece nos fechamentos que também
     fecham uma vela de 15m (:00, :15, :30, :45 — confirmado com o cliente em 19/09/2026, item
     4.5-b: avaliar em fechamentos de 5m que não coincidem com o fechamento de 15m usaria a vela
     de 15m ainda "em formação", dando resultados mais móveis/menos confiáveis):
       Condição 1  RSI(2) >= 90 -> ACIMA   |  RSI(2) <= 5 -> ABAIXO
       Condição 2  vela de 15m (já fechada): tamanho = Máx - Mín (válida se > 0,020%)
                   Setor A = 30% superior  |  Setor C = 30% inferior  |  B = meio
       Cruzamento  X = ACIMA + A  -> alvo W = fechamento + 0,5%  (verde)
                   Y = ABAIXO + C -> alvo Z = fechamento - 0,5%  (vermelho)
  4. Pop-up no canto inferior direito por 10 s + registro em CSV.

Uso:
  python alerta_futuros.py               # monitora com pop-ups
  python alerta_futuros.py --sem-popup   # só console + CSV
  python alerta_futuros.py --demo        # mostra pop-ups de exemplo, sem internet
  python alerta_futuros.py --minutos 30  # encerra sozinho após 30 min (teste)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import queue
import statistics
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import websockets

REST_BASE = "https://fapi.binance.com"
# Desde 23/04/2026 os streams de kline de Futuros USDⓈ-M só são entregues na rota /market.
# As URLs antigas (/ws e /stream sem rota) conectam, mas não enviam velas.
WS_BASE = "wss://fstream.binance.com/market/stream"

# símbolo -> casas decimais exibidas no alerta (tabela do cliente)
PARES = {
    "BTCUSDT": 2,
    "ETHUSDT": 2,
    "SOLUSDT": 2,
    "BNBUSDT": 2,
    "XRPUSDT": 4,
    "LINKUSDT": 3,
    "LTCUSDT": 2,
    "DOGEUSDT": 5,
}

MS_5M = 5 * 60 * 1000
MS_15M = 15 * 60 * 1000
ATRASO_MAX_POPUP_MS = MS_5M  # sinais recuperados com mais atraso vão só para o CSV

log = logging.getLogger("alerta")


@dataclass
class Parametros:
    rsi_periodo: int = 2
    rsi_acima: float = 90.0  # faixa "Acima": 90–100
    rsi_abaixo: float = 5.0  # faixa "Abaixo": 0–5
    setor_pct: float = 30.0  # tamanho dos setores extremos A e C (% do tamanho da vela 15m)
    tamanho_min_pct: float = 0.020  # vela 15m válida se (Máx − Mín) / Mín > 0,020%
    ajuste_pct: float = 0.5  # fator de ajuste do preço-alvo
    popup_segundos: int = 10
    velas_aquecimento: int = 300  # 25 h de velas 5m: RSI idêntico ao do gráfico desde o 1º minuto


@dataclass
class Vela:
    abertura_ms: int
    abre: float
    maxima: float
    minima: float
    fecha: float


@dataclass
class Avaliacao:
    simbolo: str
    abertura_ms: int
    fechamento: float
    rsi: float | None
    faixa: str | None  # ACIMA | ABAIXO | None
    maxima_15m: float
    minima_15m: float
    tamanho_15m_pct: float
    setor: str | None  # A | B | C | None (vela 15m inválida)
    sinal: str | None  # X | Y | None
    alvo: float | None
    alvo_texto: str
    fechamento_texto: str
    latencia_ms: float | None = None
    publicacao_binance_ms: float | None = None  # evento Binance (E) − fechamento da vela
    recuperada: bool = False  # vela fechada durante queda de conexão, avaliada ao reconectar


# ─────────────────────────────── Lógica pura (testável) ───────────────────────────────


class RSIWilder:
    """RSI com suavização de Wilder (RMA) — mesmo método dos gráficos Binance/TradingView."""

    def __init__(self, periodo: int):
        self.periodo = periodo
        self.ultimo: float | None = None
        self.valor: float | None = None
        self._n = 0
        self._soma_ganho = 0.0
        self._soma_perda = 0.0
        self._media_ganho: float | None = None
        self._media_perda: float | None = None

    def atualizar(self, fechamento: float) -> float | None:
        if self.ultimo is None:
            self.ultimo = fechamento
            return None
        delta = fechamento - self.ultimo
        self.ultimo = fechamento
        ganho, perda = max(delta, 0.0), max(-delta, 0.0)
        p = self.periodo
        if self._media_ganho is None:
            self._n += 1
            self._soma_ganho += ganho
            self._soma_perda += perda
            if self._n < p:
                return None
            self._media_ganho = self._soma_ganho / p
            self._media_perda = self._soma_perda / p
        else:
            self._media_ganho = (self._media_ganho * (p - 1) + ganho) / p
            self._media_perda = (self._media_perda * (p - 1) + perda) / p
        if self._media_perda == 0:
            self.valor = 100.0
        elif self._media_ganho == 0:
            self.valor = 0.0
        else:
            self.valor = 100 - 100 / (1 + self._media_ganho / self._media_perda)
        return self.valor


def fecha_vela_15m(abertura_ms: int) -> bool:
    """True quando o fechamento da vela de 5m (abertura_ms + MS_5M) coincide com um fechamento
    de 15m (:00, :15, :30, :45) — item 4.5-b confirmado com o cliente em 19/09/2026: só nesses
    momentos a vela de 15m está de fato completa, então só neles a Condição 2 é confiável."""
    return (abertura_ms + MS_5M) % MS_15M == 0


def faixa_rsi(rsi: float | None, p: Parametros) -> str | None:
    if rsi is None:
        return None
    if rsi >= p.rsi_acima:
        return "ACIMA"
    if rsi <= p.rsi_abaixo:
        return "ABAIXO"
    return None


def setor_vela15(fechamento: float, maxima: float, minima: float, p: Parametros) -> tuple[str | None, float]:
    """Retorna (setor, tamanho_pct). Setor None quando a vela de 15m não atinge o tamanho mínimo."""
    tamanho = maxima - minima
    tamanho_pct = tamanho / minima * 100 if minima > 0 else 0.0
    if tamanho_pct <= p.tamanho_min_pct:
        return None, tamanho_pct
    faixa = tamanho * p.setor_pct / 100
    if fechamento >= maxima - faixa:
        return "A", tamanho_pct
    if fechamento <= minima + faixa:
        return "C", tamanho_pct
    return "B", tamanho_pct


def cruzamento(faixa: str | None, setor: str | None, fechamento: float, p: Parametros) -> tuple[str, float] | None:
    if faixa == "ACIMA" and setor == "A":
        return "X", fechamento * (1 + p.ajuste_pct / 100)  # Preço-Alvo W (verde)
    if faixa == "ABAIXO" and setor == "C":
        return "Y", fechamento * (1 - p.ajuste_pct / 100)  # Preço-Alvo Z (vermelho)
    return None


def formatar_preco(valor: float, casas: int) -> str:
    """77102.3949 -> '77.102,39' (padrão brasileiro, arredondamento comercial)."""
    q = Decimal(repr(valor)).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    inteiro, _, frac = f"{q:f}".partition(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    return f"{inteiro},{frac}" if frac else inteiro


def formatar_num(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


class Ativo:
    """Estado de um par: RSI incremental + últimas velas 5m fechadas (reconstroem a vela 15m)."""

    def __init__(self, simbolo: str, casas: int, p: Parametros):
        self.simbolo = simbolo
        self.casas = casas
        self.p = p
        self.rsi = RSIWilder(p.rsi_periodo)
        self.velas: deque[Vela] = deque(maxlen=3)
        self.ultima_abertura: int | None = None

    def carregar_historico(self, velas: list[Vela]) -> None:
        self.rsi = RSIWilder(self.p.rsi_periodo)
        self.velas.clear()
        self.ultima_abertura = None
        for v in velas:
            self._aplicar(v)

    def classificar(self, abertura_ms: int) -> str:
        """'nova' | 'duplicada' | 'lacuna' — protege contra mensagens repetidas e quedas de conexão."""
        if self.ultima_abertura is None or abertura_ms == self.ultima_abertura + MS_5M:
            return "nova"
        if abertura_ms <= self.ultima_abertura:
            return "duplicada"
        return "lacuna"

    def _aplicar(self, v: Vela) -> float | None:
        self.velas.append(v)
        self.ultima_abertura = v.abertura_ms
        return self.rsi.atualizar(v.fecha)

    def fechar_vela(self, v: Vela) -> Avaliacao:
        rsi = self._aplicar(v)
        faixa = faixa_rsi(rsi, self.p)

        # Vela de 15m em andamento no fechamento da 5m = agregação das velas 5m da mesma janela.
        # Matematicamente idêntica à vela 15m da Binance e imune a ordem de chegada das mensagens.
        janela = v.abertura_ms // MS_15M * MS_15M
        na_janela = [x for x in self.velas if x.abertura_ms >= janela]
        maxima = max(x.maxima for x in na_janela)
        minima = min(x.minima for x in na_janela)
        setor, tamanho_pct = setor_vela15(v.fecha, maxima, minima, self.p)

        cruz = cruzamento(faixa, setor, v.fecha, self.p)
        sinal, alvo = cruz if cruz else (None, None)
        return Avaliacao(
            simbolo=self.simbolo,
            abertura_ms=v.abertura_ms,
            fechamento=v.fecha,
            rsi=rsi,
            faixa=faixa,
            maxima_15m=maxima,
            minima_15m=minima,
            tamanho_15m_pct=tamanho_pct,
            setor=setor,
            sinal=sinal,
            alvo=alvo,
            alvo_texto=formatar_preco(alvo, self.casas) if alvo is not None else "",
            fechamento_texto=formatar_preco(v.fecha, self.casas),
        )


# ─────────────────────────────── Conexão Binance ───────────────────────────────


def _get_json(caminho: str, **params):
    url = f"{REST_BASE}{caminho}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "alerta-futuros-poc/0.1"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def _vela_de_kline(k: list) -> Vela:
    return Vela(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]))


class Monitor:
    def __init__(self, p: Parametros, ao_avaliar, pares: dict[str, int] = PARES):
        self.p = p
        self.ao_avaliar = ao_avaliar
        self.ativos = {s: Ativo(s, c, p) for s, c in pares.items()}
        self.offset_ms = 0.0  # relógio Binance − relógio local
        self.parar = threading.Event()
        self.conectado = threading.Event()  # exposto pra janela mostrar o status da conexão
        self.reconexoes = 0

    def _sincronizar_relogio(self) -> None:
        t0 = time.time() * 1000
        servidor = _get_json("/fapi/v1/time")["serverTime"]
        t1 = time.time() * 1000
        self.offset_ms = servidor - (t0 + t1) / 2

    def agora_binance_ms(self) -> float:
        return time.time() * 1000 + self.offset_ms

    def _baixar_velas(self, simbolo: str, antes_de_ms: int | None = None) -> list[Vela]:
        params = {"symbol": simbolo, "interval": "5m", "limit": self.p.velas_aquecimento + 1}
        if antes_de_ms is not None:
            params["endTime"] = antes_de_ms - 1
        agora = self.agora_binance_ms()
        # descarta a vela ainda aberta (closeTime no futuro)
        return [_vela_de_kline(k) for k in _get_json("/fapi/v1/klines", **params) if k[6] < agora]

    async def _recuperar(self, simbolo: str, antes_de_ms: int | None = None) -> None:
        """Recarrega o histórico via REST. Se o par já vinha sendo monitorado, as velas que fecharam
        durante a queda de conexão são AVALIADAS (e não apenas absorvidas no histórico)."""
        ativo = self.ativos[simbolo]
        ultima = ativo.ultima_abertura
        velas = await asyncio.to_thread(self._baixar_velas, simbolo, antes_de_ms)
        if ultima is None or not velas or ultima < velas[0].abertura_ms:
            if ultima is not None:
                log.warning("%s: queda maior que o histórico disponível; velas antigas não serão avaliadas.", simbolo)
            ativo.carregar_historico(velas)
            return
        ativo.carregar_historico([v for v in velas if v.abertura_ms <= ultima])
        for v in velas:
            if v.abertura_ms > ultima:
                av = ativo.fechar_vela(v)  # sempre atualiza o RSI(2), mesmo fora de um fechamento de 15m
                if not fecha_vela_15m(v.abertura_ms):
                    continue  # só captamos (CSV/pop-up) nos fechamentos que também fecham a vela de 15m
                av.latencia_ms = self.agora_binance_ms() - (v.abertura_ms + MS_5M)
                av.recuperada = True
                self.ao_avaliar(av)

    async def _sincronizar(self) -> None:
        await asyncio.to_thread(self._sincronizar_relogio)
        await asyncio.gather(*(self._recuperar(s) for s in self.ativos))
        log.info("Histórico carregado (%d velas 5m por par). Relógio Binance %+.0f ms vs. local.",
                 self.p.velas_aquecimento, self.offset_ms)

    def _url_ws(self) -> str:
        streams = "/".join(f"{s.lower()}@kline_{i}" for s in self.ativos for i in ("5m", "15m"))
        return f"{WS_BASE}?streams={streams}"

    async def executar(self) -> None:
        espera = 1
        while not self.parar.is_set():
            try:
                async with websockets.connect(self._url_ws(), open_timeout=10) as ws:
                    # Conecta primeiro e só depois baixa o histórico: mensagens ficam na fila,
                    # então nenhuma vela se perde entre o REST e o WebSocket.
                    await self._sincronizar()
                    log.info("WebSocket conectado: %d pares, streams 5m + 15m.", len(self.ativos))
                    self.conectado.set()
                    espera = 1
                    await self._ler(ws)
            except Exception as e:  # rede instável, Wi-Fi trocado, laptop hibernou, desconexão de 24h…
                self.conectado.clear()
                if self.parar.is_set():
                    break
                self.reconexoes += 1
                log.warning("Conexão perdida (%s). Reconectando em %ds…", type(e).__name__, espera)
                await asyncio.sleep(espera)
                espera = min(espera * 2, 30)

    async def _ler(self, ws) -> None:
        ultimo_msg = time.monotonic()
        while not self.parar.is_set():
            try:
                bruto = await asyncio.wait_for(ws.recv(), timeout=1)
            except TimeoutError:
                # klines chegam a cada ~250 ms; 30 s de silêncio = conexão morta sem aviso
                if time.monotonic() - ultimo_msg > 30:
                    raise ConnectionError("sem dados há 30 s")
                continue
            ultimo_msg = time.monotonic()
            dados = json.loads(bruto).get("data", {})
            k = dados.get("k")
            if not k or k["i"] != "5m" or not k["x"]:
                continue
            await self._vela_fechada(k, dados.get("E"), recebido_ms=self.agora_binance_ms())

    async def _vela_fechada(self, k: dict, evento_ms: int | None, recebido_ms: float) -> None:
        simbolo = k["s"]
        ativo = self.ativos.get(simbolo)
        if ativo is None:
            return
        vela = Vela(int(k["t"]), float(k["o"]), float(k["h"]), float(k["l"]), float(k["c"]))
        situacao = ativo.classificar(vela.abertura_ms)
        if situacao == "duplicada":
            return
        if situacao == "lacuna":
            log.warning("%s: lacuna detectada, recompondo histórico via REST.", simbolo)
            await self._recuperar(simbolo, antes_de_ms=vela.abertura_ms)
        av = ativo.fechar_vela(vela)  # sempre atualiza o RSI(2), mesmo fora de um fechamento de 15m
        if not fecha_vela_15m(vela.abertura_ms):
            return  # só captamos (CSV/pop-up) nos fechamentos que também fecham a vela de 15m
        fechou_ms = int(k["T"]) + 1
        av.latencia_ms = recebido_ms - fechou_ms
        if evento_ms is not None:
            av.publicacao_binance_ms = evento_ms - fechou_ms
        self.ao_avaliar(av)


# ─────────────────────────────── Pop-up (Tkinter) ───────────────────────────────

VERDE = "#22c55e"
VERMELHO = "#ef4444"


class Popups:
    """Janela estilo 'toast' no canto inferior direito: cor do preço + duração exata de 10 s,
    o que a notificação nativa do Windows não permite controlar."""

    LARGURA, ALTURA, MARGEM, BARRA_TAREFAS = 330, 104, 10, 56

    def __init__(self, root, segundos: int):
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.segundos = segundos
        self.abertos: list = []

    def mostrar(self, av: Avaliacao) -> None:
        tk = self.tk
        cor = VERDE if av.sinal == "X" else VERMELHO
        alvo = "W" if av.sinal == "X" else "Z"
        janela = tk.Toplevel(self.root)
        janela.overrideredirect(True)
        janela.attributes("-topmost", True)
        try:
            janela.attributes("-toolwindow", True)  # Windows: não aparece na barra de tarefas
        except tk.TclError:
            pass
        janela.configure(bg=cor)

        corpo = tk.Frame(janela, bg="#111827")
        corpo.place(x=5, y=0, relwidth=1, relheight=1, width=-5)
        hora = datetime.fromtimestamp((av.abertura_ms + MS_5M) / 1000).strftime("%H:%M")
        tk.Label(corpo, text=f"ALERTA FUTUROS  ·  fechamento 5m {hora}", fg="#9ca3af", bg="#111827",
                 font=("Segoe UI", 8)).place(x=12, y=8)
        tk.Label(corpo, text=av.simbolo, fg="#f9fafb", bg="#111827",
                 font=("Segoe UI", 13, "bold")).place(x=12, y=28)
        tk.Label(corpo, text=f"{alvo}  {av.alvo_texto}", fg=cor, bg="#111827",
                 font=("Segoe UI", 20, "bold")).place(x=12, y=50)
        detalhe = f"RSI(2) {formatar_num(av.rsi)} · Setor {av.setor} · Fech. {av.fechamento_texto}"
        tk.Label(corpo, text=detalhe, fg="#9ca3af", bg="#111827", font=("Segoe UI", 8)).place(x=12, y=84)

        for w in (janela, corpo, *corpo.winfo_children()):
            w.bind("<Button-1>", lambda _e, j=janela: self._fechar(j))
        self.abertos.append(janela)
        self._posicionar()
        janela.after(self.segundos * 1000, lambda: self._fechar(janela))

    def _fechar(self, janela) -> None:
        if janela in self.abertos:
            self.abertos.remove(janela)
            janela.destroy()
            self._posicionar()

    def _posicionar(self) -> None:
        largura_tela = self.root.winfo_screenwidth()
        altura_tela = self.root.winfo_screenheight()
        por_coluna = max(1, (altura_tela - self.BARRA_TAREFAS) // (self.ALTURA + self.MARGEM))
        for i, janela in enumerate(self.abertos):
            coluna, linha = divmod(i, por_coluna)
            x = largura_tela - (self.LARGURA + self.MARGEM) * (coluna + 1)
            y = altura_tela - self.BARRA_TAREFAS - (self.ALTURA + self.MARGEM) * (linha + 1)
            janela.geometry(f"{self.LARGURA}x{self.ALTURA}+{x}+{y}")


# ─────────────────────────────── Registro / console ───────────────────────────────


class Registro:
    CAMPOS = ["fechamento_5m", "par", "preco_fechamento", "rsi2", "faixa", "max_15m", "min_15m",
              "tamanho_15m_pct", "setor", "sinal", "preco_alvo", "latencia_ms", "publicacao_binance_ms",
              "recuperada"]

    def __init__(self, pasta: Path):
        pasta.mkdir(parents=True, exist_ok=True)
        self.caminho = pasta / f"fechamentos_{datetime.now():%Y%m%d_%H%M%S}.csv"
        self._arq = self.caminho.open("w", newline="", encoding="utf-8")
        self._csv = csv.writer(self._arq, delimiter=";")
        self._csv.writerow(self.CAMPOS)
        self._arq.flush()  # cabeçalho no disco na hora: sessão sem nenhuma captação não deixa arquivo vazio
        # gravar() roda na thread do motor e fechar() na thread da UI ("Parar"): sem o lock, uma vela
        # que fecha no mesmo instante do clique gravava em arquivo já fechado (ValueError).
        self._lock = threading.Lock()
        self.fechado = False
        self.avaliacoes = 0
        self.sinais = 0
        self.latencias: list[float] = []

    def gravar(self, av: Avaliacao) -> None:
        with self._lock:
            if self.fechado:  # já paramos: a avaliação não entra no CSV, mas também não quebra o motor
                log.debug("%s: avaliação após o encerramento do registro, ignorada.", av.simbolo)
                return
            self._gravar(av)

    def _gravar(self, av: Avaliacao) -> None:
        self.avaliacoes += 1
        self.sinais += av.sinal is not None
        if av.latencia_ms is not None and not av.recuperada:
            self.latencias.append(av.latencia_ms)
        fech = datetime.fromtimestamp((av.abertura_ms + MS_5M) / 1000)
        self._csv.writerow([
            f"{fech:%Y-%m-%d %H:%M}", av.simbolo, av.fechamento, _fmt(av.rsi, 2), av.faixa or "",
            av.maxima_15m, av.minima_15m, _fmt(av.tamanho_15m_pct, 4), av.setor or "inválida",
            av.sinal or "", av.alvo_texto, _fmt(av.latencia_ms, 0), _fmt(av.publicacao_binance_ms, 0),
            "sim" if av.recuperada else "",
        ])
        self._arq.flush()

        rsi = f"RSI(2) {formatar_num(av.rsi):>5} {av.faixa or '':<6}" if av.rsi is not None else "RSI —"
        setor = f"setor {av.setor}" if av.setor else "15m inválida"
        linha = (f"{fech:%H:%M} {av.simbolo:<9} fech {av.fechamento_texto:>11} | {rsi} | "
                 f"15m {formatar_num(av.tamanho_15m_pct, 3)}% {setor:<12} | lat {_fmt(av.latencia_ms, 0)} ms")
        if av.recuperada:
            linha += "  (recuperada após queda)"
        if av.sinal:
            linha += f"  >>> SINAL {av.sinal}: alvo {'W' if av.sinal == 'X' else 'Z'} {av.alvo_texto}"
        log.info(linha)

    def resumo(self) -> str:
        partes = [f"{self.avaliacoes} fechamentos avaliados", f"{self.sinais} sinais"]
        if self.latencias:
            lat = sorted(self.latencias)
            p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
            partes.append(f"latência mediana {statistics.median(lat):.0f} ms, p95 {p95:.0f} ms, máx {lat[-1]:.0f} ms")
        return " · ".join(partes) + f" · CSV: {self.caminho}"

    def fechar(self) -> None:
        with self._lock:
            if not self.fechado:
                self.fechado = True
                self._arq.close()


def _fmt(valor: float | None, casas: int) -> str:
    return "" if valor is None else f"{valor:.{casas}f}"


# ─────────────────────────────── Execução ───────────────────────────────


def _exemplos() -> list[Avaliacao]:
    base = {"BTCUSDT": 76718.8, "ETHUSDT": 2505.19, "SOLUSDT": 101.93, "BNBUSDT": 721.82,
            "XRPUSDT": 1.3688, "LINKUSDT": 11.534, "LTCUSDT": 650.39, "DOGEUSDT": 0.08506}
    p = Parametros()
    agora = int(time.time() * 1000) // MS_5M * MS_5M - MS_5M
    saida = []
    for i, (s, fech) in enumerate(base.items()):
        faixa, setor, rsi = ("ACIMA", "A", 94.7) if i % 2 == 0 else ("ABAIXO", "C", 3.2)
        sinal, alvo = cruzamento(faixa, setor, fech, p)
        casas = PARES[s]
        saida.append(Avaliacao(s, agora, fech, rsi, faixa, fech, fech, 0.3, setor, sinal, alvo,
                               formatar_preco(alvo, casas), formatar_preco(fech, casas)))
    return saida


def main() -> None:
    ap = argparse.ArgumentParser(description="PoC — alertas Binance Futuros (dados públicos)")
    ap.add_argument("--sem-popup", action="store_true", help="somente console + CSV")
    ap.add_argument("--demo", action="store_true", help="exibe pop-ups de exemplo (sem internet)")
    ap.add_argument("--minutos", type=float, default=0, help="encerra após N minutos (0 = contínuo)")
    ap.add_argument("--rsi-acima", type=float, default=90.0)
    ap.add_argument("--rsi-abaixo", type=float, default=5.0)
    ap.add_argument("--pasta-log", type=Path, default=Path(__file__).with_name("logs"))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    p = Parametros(rsi_acima=args.rsi_acima, rsi_abaixo=args.rsi_abaixo)

    if args.demo:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        popups = Popups(root, p.popup_segundos)
        for i, av in enumerate(_exemplos()):
            root.after(150 * i, lambda a=av: popups.mostrar(a))
        root.after(p.popup_segundos * 1000 + 1500, root.destroy)
        root.mainloop()
        return

    registro = Registro(args.pasta_log)
    fila_popups: queue.Queue[Avaliacao] = queue.Queue()

    def ao_avaliar(av: Avaliacao) -> None:
        registro.gravar(av)
        if av.sinal and (av.latencia_ms or 0) < ATRASO_MAX_POPUP_MS:
            fila_popups.put(av)

    monitor = Monitor(p, ao_avaliar)
    log.info("PoC Alerta Futuros — %d pares · RSI(%d) ≥ %s / ≤ %s · setores %s%% · ajuste ±%s%%",
             len(PARES), p.rsi_periodo, formatar_num(p.rsi_acima, 0), formatar_num(p.rsi_abaixo, 0),
             formatar_num(p.setor_pct, 0), formatar_num(p.ajuste_pct))

    motor = threading.Thread(target=lambda: asyncio.run(monitor.executar()), daemon=True)
    motor.start()
    fim = time.monotonic() + args.minutos * 60 if args.minutos else None

    try:
        if args.sem_popup:
            while motor.is_alive() and (fim is None or time.monotonic() < fim):
                time.sleep(0.5)
        else:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            popups = Popups(root, p.popup_segundos)

            def verificar() -> None:
                while not fila_popups.empty():
                    popups.mostrar(fila_popups.get_nowait())
                if fim is not None and time.monotonic() >= fim:
                    root.destroy()
                    return
                root.after(100, verificar)

            root.after(100, verificar)
            root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        monitor.parar.set()
        motor.join(timeout=3)
        log.info("Encerrado. %s · reconexões: %d", registro.resumo(), monitor.reconexoes)
        registro.fechar()


if __name__ == "__main__":
    main()
