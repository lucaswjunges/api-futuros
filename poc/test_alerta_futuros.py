"""Testes da lógica de sinais. Executar: python -m unittest -v"""

import asyncio
import tempfile
import unittest
from pathlib import Path

from alerta_futuros import (
    CASAS_PADRAO,
    LIMITE_PARES,
    MS_5M,
    MS_15M,
    PARES,
    Ativo,
    Avaliacao,
    Monitor,
    Parametros,
    Registro,
    RSIWilder,
    Vela,
    casas_de_exchange_info,
    casas_do_tick,
    cruzamento,
    faixa_rsi,
    fecha_vela_15m,
    formatar_preco,
    pares_desconhecidos,
    resolver_pares,
    setor_vela15,
)

P = Parametros()


class TestCasasDecimais(unittest.TestCase):
    """Casas decimais dos pares acrescentados depois dos 8 originais (teto de 16, 23/09/2026):
    elas saem do tickSize da Binance, não mais de uma tabela escrita à mão."""

    def test_tick_size_com_zeros_de_enchimento(self):
        # valores reais do /fapi/v1/exchangeInfo em 23/09/2026
        self.assertEqual(casas_do_tick("0.0100"), 2)    # SOLUSDT
        self.assertEqual(casas_do_tick("0.000010"), 5)  # DOGEUSDT
        self.assertEqual(casas_do_tick("0.0001"), 4)    # XRPUSDT
        self.assertEqual(casas_do_tick("0.001"), 3)     # LINKUSDT
        self.assertEqual(casas_do_tick("0.10"), 1)      # BTCUSDT
        self.assertEqual(casas_do_tick("1"), 0)
        self.assertEqual(casas_do_tick("10"), 0)

    def test_tick_size_estranho_cai_no_padrao(self):
        for valor in ("", "abc", None, "NaN"):
            self.assertEqual(casas_do_tick(valor), CASAS_PADRAO, valor)

    def test_le_o_exchange_info_e_ignora_simbolo_sem_price_filter(self):
        dados = {"symbols": [
            {"symbol": "ADAUSDT", "filters": [{"filterType": "LOT_SIZE"},
                                              {"filterType": "PRICE_FILTER", "tickSize": "0.00010"}]},
            {"symbol": "SEMFILTRO", "filters": [{"filterType": "LOT_SIZE"}]},
        ]}
        self.assertEqual(casas_de_exchange_info(dados), {"ADAUSDT": 4})

    def test_exchange_info_vazio_ou_sem_a_chave(self):
        self.assertEqual(casas_de_exchange_info({}), {})


class TestResolverPares(unittest.TestCase):
    def test_tabela_do_cliente_vence_o_tick_size(self):
        """O BTCUSDT é o caso concreto: o tickSize dá 1 casa, mas o cliente montou a tabela dele
        olhando o gráfico e pediu 2. Mexer nisso mudaria o preço que ele já está acostumado a ver."""
        resolvido = resolver_pares(["BTCUSDT"], catalogo={"BTCUSDT": 1})
        self.assertEqual(resolvido, {"BTCUSDT": 2})

    def test_par_novo_usa_o_catalogo_da_binance(self):
        self.assertEqual(resolver_pares(["ADAUSDT"], catalogo={"ADAUSDT": 4}), {"ADAUSDT": 4})

    def test_par_novo_sem_catalogo_cai_no_padrao(self):
        self.assertEqual(resolver_pares(["ADAUSDT"], catalogo={}), {"ADAUSDT": CASAS_PADRAO})

    def test_preserva_a_ordem_pedida(self):
        pedidos = ["ETHUSDT", "BTCUSDT", "DOGEUSDT"]
        self.assertEqual(list(resolver_pares(pedidos, catalogo={})), pedidos)

    def test_normaliza_espaco_e_minuscula(self):
        self.assertEqual(resolver_pares([" btcusdt ", "ethusdt"], catalogo={}),
                         {"BTCUSDT": 2, "ETHUSDT": 2})

    def test_os_8_originais_continuam_com_as_casas_de_sempre(self):
        self.assertEqual(resolver_pares(list(PARES), catalogo={}), dict(PARES))


class TestParesDesconhecidos(unittest.TestCase):
    """Erro de digitação no campo de pares vira aviso, e não uma linha morta no quadro."""

    CATALOGO = {"BTCUSDT": 2, "ADAUSDT": 4}

    def test_aponta_o_que_a_binance_nao_tem(self):
        self.assertEqual(pares_desconhecidos(["BTCUSDT", "BTCUSD"], self.CATALOGO), ["BTCUSD"])

    def test_tudo_certo_nao_aponta_nada(self):
        self.assertEqual(pares_desconhecidos(["BTCUSDT", "ADAUSDT"], self.CATALOGO), [])

    def test_sem_catalogo_deixa_passar(self):
        """Sem internet a consulta volta vazia; aí é melhor deixar iniciar do que travar o app."""
        self.assertEqual(pares_desconhecidos(["QUALQUERCOISA"], {}), [])

    def test_nao_repete_o_mesmo_erro_duas_vezes(self):
        self.assertEqual(pares_desconhecidos(["btcusd", "BTCUSD"], self.CATALOGO), ["BTCUSD"])


class TestMonitorComOutrosPares(unittest.TestCase):
    def test_monta_um_ativo_por_par_ate_o_teto(self):
        pares = resolver_pares([f"AA{i:02d}USDT" for i in range(LIMITE_PARES)], catalogo={})
        monitor = Monitor(P, lambda _av: None, pares)
        self.assertEqual(len(monitor.ativos), LIMITE_PARES)

    def test_url_do_websocket_pede_os_streams_dos_pares_escolhidos(self):
        monitor = Monitor(P, lambda _av: None, resolver_pares(["ADAUSDT", "BTCUSDT"], catalogo={}))
        url = monitor._url_ws()
        self.assertIn("adausdt@kline_5m", url)
        self.assertIn("btcusdt@kline_5m", url)
        self.assertNotIn("ethusdt", url)


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


class TestRegistro(unittest.TestCase):
    """Corrida achada em 20/09/2026: o motor grava numa thread e a UI fecha o CSV noutra ("Parar")."""

    def _avaliacao(self) -> Avaliacao:
        return Avaliacao("BTCUSDT", 0, 1.0, 95.0, "ACIMA", 2.0, 1.0, 1.0, "A", "X", 1.005, "1,01", "1,00", 100)

    def test_cabecalho_vai_pro_disco_na_criacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            registro = Registro(Path(pasta))
            self.assertIn("fechamento_5m", registro.caminho.read_text(encoding="utf-8"))
            registro.fechar()

    def test_gravar_depois_de_fechar_nao_quebra_o_motor(self):
        with tempfile.TemporaryDirectory() as pasta:
            registro = Registro(Path(pasta))
            registro.gravar(self._avaliacao())
            registro.fechar()
            registro.gravar(self._avaliacao())  # antes do fix: ValueError na thread do motor
            self.assertEqual(registro.caminho.read_text(encoding="utf-8").count("BTCUSDT"), 1)

    def test_fechar_duas_vezes_e_inofensivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            registro = Registro(Path(pasta))
            registro.fechar()
            registro.fechar()


if __name__ == "__main__":
    unittest.main()
