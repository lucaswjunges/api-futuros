"""Testes da lógica de sinais. Executar: python -m unittest -v"""

import asyncio
import unittest

from alerta_futuros import (
    MS_5M,
    MS_15M,
    Ativo,
    Monitor,
    Parametros,
    RSIWilder,
    Vela,
    cruzamento,
    faixa_rsi,
    fecha_vela_15m,
    formatar_preco,
    setor_vela15,
)

P = Parametros()


class TestRSI(unittest.TestCase):
    def test_referencia_wilder_periodo_14(self):
        # Planilha de referência de Wilder publicada pela StockCharts (RSI 14, preços com 4 casas).
        fechamentos = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433,
                       46.0826, 45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116,
                       46.2222, 45.6439, 46.2122, 46.2521, 45.7137, 46.4515, 45.7835, 45.3548, 44.0288,
                       44.1783, 44.2181, 44.5672, 43.4205, 42.6628, 43.1314]
        esperado = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38, 54.71, 50.42,
                    39.99, 41.46, 41.87, 45.46, 37.30, 33.08, 37.77]
        rsi = RSIWilder(14)
        valores = [v for v in (rsi.atualizar(f) for f in fechamentos) if v is not None]
        for obtido, ref in zip(valores, esperado, strict=True):
            self.assertAlmostEqual(obtido, ref, delta=0.01)

    def test_periodo_2_calculado_a_mao(self):
        rsi = RSIWilder(2)
        self.assertIsNone(rsi.atualizar(10))
        self.assertIsNone(rsi.atualizar(11))
        # variações +1, −0,5 -> médias 0,5 / 0,25 -> RS 2 -> RSI 66,67
        self.assertAlmostEqual(rsi.atualizar(10.5), 66.6667, places=3)
        # +1,5 -> médias (0,5+1,5)/2 = 1,0 / 0,25/2 = 0,125 -> RS 8 -> RSI 88,89
        self.assertAlmostEqual(rsi.atualizar(12), 88.8889, places=3)

    def test_extremos(self):
        so_alta = RSIWilder(2)
        for f in (1, 2, 3, 4):
            so_alta.atualizar(f)
        self.assertEqual(so_alta.valor, 100.0)
        so_queda = RSIWilder(2)
        for f in (4, 3, 2, 1):
            so_queda.atualizar(f)
        self.assertEqual(so_queda.valor, 0.0)


class TestCondicoes(unittest.TestCase):
    def test_faixas_rsi_limites_inclusivos(self):
        self.assertEqual(faixa_rsi(90.0, P), "ACIMA")
        self.assertEqual(faixa_rsi(100.0, P), "ACIMA")
        self.assertIsNone(faixa_rsi(89.99, P))
        self.assertEqual(faixa_rsi(5.0, P), "ABAIXO")
        self.assertEqual(faixa_rsi(0.0, P), "ABAIXO")
        self.assertIsNone(faixa_rsi(5.01, P))
        self.assertIsNone(faixa_rsi(None, P))

    def test_setores_30_40_30(self):
        # Máx 110, Mín 100 -> tamanho 10 -> A: >= 107 · C: <= 103 · B: entre
        self.assertEqual(setor_vela15(110, 110, 100, P)[0], "A")
        self.assertEqual(setor_vela15(107, 110, 100, P)[0], "A")
        self.assertEqual(setor_vela15(106.99, 110, 100, P)[0], "B")
        self.assertEqual(setor_vela15(103.01, 110, 100, P)[0], "B")
        self.assertEqual(setor_vela15(103, 110, 100, P)[0], "C")
        self.assertEqual(setor_vela15(100, 110, 100, P)[0], "C")

    def test_vela_15m_pequena_invalida(self):
        # (100,02 − 100) / 100 = 0,020% -> não é MAIOR que 0,020% -> inválida
        setor, tamanho = setor_vela15(100.02, 100.02, 100, P)
        self.assertIsNone(setor)
        self.assertAlmostEqual(tamanho, 0.02, places=6)
        self.assertEqual(setor_vela15(100.03, 100.03, 100, P)[0], "A")

    def test_cruzamento_e_preco_alvo(self):
        sinal, alvo = cruzamento("ACIMA", "A", 1000.0, P)
        self.assertEqual(sinal, "X")
        self.assertAlmostEqual(alvo, 1005.0)
        sinal, alvo = cruzamento("ABAIXO", "C", 1000.0, P)
        self.assertEqual(sinal, "Y")
        self.assertAlmostEqual(alvo, 995.0)
        for faixa, setor in (("ACIMA", "C"), ("ABAIXO", "A"), ("ACIMA", "B"), (None, "A"), ("ACIMA", None)):
            self.assertIsNone(cruzamento(faixa, setor, 1000.0, P))


class TestFormatacao(unittest.TestCase):
    def test_tabela_do_cliente(self):
        casos = [
            (77102.39, 2, "77.102,39"),
            (2517.72, 2, "2.517,72"),
            (101.42, 2, "101,42"),
            (725.43, 2, "725,43"),
            (1.362, 4, "1,3620"),
            (11.476, 3, "11,476"),
            (653.64, 2, "653,64"),
            (0.08464, 5, "0,08464"),
        ]
        for valor, casas, esperado in casos:
            self.assertEqual(formatar_preco(valor, casas), esperado)

    def test_arredondamento(self):
        self.assertEqual(formatar_preco(76718.8 * 1.005, 2), "77.102,39")  # 77102,394
        self.assertEqual(formatar_preco(0.085065, 5), "0,08507")
        self.assertEqual(formatar_preco(1234567.891, 2), "1.234.567,89")


def _vela(minuto: int, maxima: float, minima: float, fecha: float) -> Vela:
    return Vela(minuto * 60_000, fecha, maxima, minima, fecha)


class TestAtivo(unittest.TestCase):
    def test_vela_15m_agrega_somente_a_janela_atual(self):
        ativo = Ativo("BTCUSDT", 2, P)
        ativo.carregar_historico([_vela(0, 105, 95, 100), _vela(5, 120, 99, 110)])
        # 10:10 fecha a janela 10:00–10:15: Máx 120, Mín 95 -> tamanho 25 -> A >= 112,5
        av = ativo.fechar_vela(_vela(10, 118, 108, 115))
        self.assertEqual((av.maxima_15m, av.minima_15m, av.setor), (120, 95, "A"))
        # 10:15 abre nova janela: só a própria vela conta
        av = ativo.fechar_vela(_vela(15, 116, 112, 112.5))
        self.assertEqual((av.maxima_15m, av.minima_15m, av.setor), (116, 112, "C"))

    def test_sinal_completo(self):
        ativo = Ativo("ETHUSDT", 2, P)
        ativo.carregar_historico([_vela(0, 101, 99, 100), _vela(5, 102, 100, 101)])
        av = ativo.fechar_vela(_vela(10, 110, 101, 110))  # alta forte: RSI(2) = 100, fecha na máxima
        self.assertEqual((av.faixa, av.setor, av.sinal), ("ACIMA", "A", "X"))
        self.assertEqual(av.alvo_texto, "110,55")

    def test_duplicada_e_lacuna(self):
        ativo = Ativo("SOLUSDT", 2, P)
        ativo.carregar_historico([_vela(0, 1, 1, 1), _vela(5, 1, 1, 1)])
        self.assertEqual(ativo.classificar(5 * 60_000), "duplicada")
        self.assertEqual(ativo.classificar(5 * 60_000 + MS_5M), "nova")
        self.assertEqual(ativo.classificar(5 * 60_000 + 3 * MS_5M), "lacuna")


def _kline(simbolo: str, minuto: int, o: float, h: float, l: float, c: float) -> dict:
    """Kline de 5m no formato do WebSocket da Binance, só com os campos que Monitor._vela_fechada lê."""
    abertura = minuto * 60_000
    return {"s": simbolo, "t": abertura, "T": abertura + MS_5M - 1, "o": o, "h": h, "l": l, "c": c,
            "i": "5m", "x": True}


class TestCaptacao15m(unittest.TestCase):
    """Item 4.5-b, confirmado com o cliente em 19/09/2026: só os fechamentos de 5m que também
    fecham uma vela de 15m (:00/:15/:30/:45) são captados (CSV + pop-up) — os demais só alimentam
    o RSI(2), porque a vela de 15m ainda estaria "em formação" nesses momentos."""

    def test_fecha_vela_15m_marca_so_os_fechamentos_de_15_30_45_00(self):
        self.assertFalse(fecha_vela_15m(0 * 60_000))   # fecha às :05
        self.assertFalse(fecha_vela_15m(5 * 60_000))   # fecha às :10
        self.assertTrue(fecha_vela_15m(10 * 60_000))   # fecha às :15
        self.assertFalse(fecha_vela_15m(15 * 60_000))  # fecha às :20
        self.assertTrue(fecha_vela_15m(25 * 60_000))   # fecha às :30
        self.assertEqual(MS_15M, 3 * MS_5M)

    def test_monitor_so_capta_avaliacoes_nos_fechamentos_de_15m(self):
        avaliadas = []
        monitor = Monitor(P, avaliadas.append, pares={"BTCUSDT": 2})
        monitor.ativos["BTCUSDT"].carregar_historico([_vela(0, 101, 99, 100), _vela(5, 102, 100, 101)])

        asyncio.run(monitor._vela_fechada(_kline("BTCUSDT", 10, 101, 110, 101, 110), None, 0))  # 10:15 — captado
        asyncio.run(monitor._vela_fechada(_kline("BTCUSDT", 15, 110, 112, 109, 111), None, 0))  # 10:20 — só RSI
        asyncio.run(monitor._vela_fechada(_kline("BTCUSDT", 20, 111, 113, 110, 112), None, 0))  # 10:25 — só RSI

        self.assertEqual([a.abertura_ms for a in avaliadas], [10 * 60_000])
        # o RSI(2)/histórico de velas avançou pelas 3 fechadas, não só pela captada
        self.assertEqual(monitor.ativos["BTCUSDT"].ultima_abertura, 20 * 60_000)


class TestRecuperacaoAposQueda(unittest.TestCase):
    def _monitor(self, lotes):
        avaliadas = []
        monitor = Monitor(P, avaliadas.append, pares={"BTCUSDT": 2})
        monitor._baixar_velas = lambda _simbolo, _antes=None: lotes.pop(0)
        return monitor, avaliadas

    def test_conectado_comeca_desligado(self):
        # a janela (Opção B) usa esse Event pra mostrar o status da conexão no quadro de situação
        monitor, _ = self._monitor([[]])
        self.assertFalse(monitor.conectado.is_set())

    def test_velas_fechadas_durante_a_queda_sao_avaliadas(self):
        historico = [_vela(m, 101, 99, 100) for m in range(0, 30, 5)]  # 10:00 … 10:25
        # 10:30 fecha às 10:35 (não é fechamento de 15m) · 10:35 fecha às 10:40 (idem)
        # 10:40 fecha às 10:45 (é fechamento de 15m) — item 4.5-b: só esse é "captado"
        durante_queda = [_vela(30, 110, 100, 110), _vela(35, 111, 109, 111), _vela(40, 112, 108, 112)]
        monitor, avaliadas = self._monitor([historico, historico + durante_queda])
        asyncio.run(monitor._recuperar("BTCUSDT"))  # conexão inicial: só carrega
        self.assertEqual(avaliadas, [])
        asyncio.run(monitor._recuperar("BTCUSDT"))  # reconexão: RSI atualiza nas 3, mas só 10:40 é captada
        self.assertEqual([a.abertura_ms for a in avaliadas], [40 * 60_000])
        self.assertTrue(all(a.recuperada for a in avaliadas))
        # o RSI(2) e o histórico de velas avançaram pelas 3, mesmo as 2 não captadas
        self.assertEqual(monitor.ativos["BTCUSDT"].ultima_abertura, 40 * 60_000)

    def test_queda_maior_que_o_historico_nao_avalia_velas_antigas(self):
        monitor, avaliadas = self._monitor([[_vela(0, 1, 1, 1)], [_vela(m, 1, 1, 1) for m in range(600, 700, 5)]])
        asyncio.run(monitor._recuperar("BTCUSDT"))
        asyncio.run(monitor._recuperar("BTCUSDT"))
        self.assertEqual(avaliadas, [])


if __name__ == "__main__":
    unittest.main()
