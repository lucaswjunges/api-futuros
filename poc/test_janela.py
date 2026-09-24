"""Testa só a lógica de janela.py que não depende de um tk.Tk() real (widgets em si continuam
cobertos pelo smoke test manual — ver o combinado no PR). O que dá pra testar sem GUI é
justamente onde o bug do CSV faltando (corrigido em 19/09/2026) escapou: nada verificava que
o ao_avaliar usado pela janela também grava no Registro, igual o CLI já fazia."""

import queue
import unittest
from unittest.mock import MagicMock, call, patch

import janela
from alerta_futuros import Avaliacao
from janela import (
    LARGURA_MIN_LADO_A_LADO, URL_OUTRAS_VERSOES, abrir_outras_versoes, altura_maxima_do_quadro,
    construir_ao_avaliar,
)


def _avaliacao(simbolo: str = "BTCUSDT", abertura_ms: int = 0) -> Avaliacao:
    return Avaliacao(simbolo, abertura_ms, 100.0, 94.7, "ACIMA", 101.0, 99.0, 0.3, "A", "X", 100.5,
                      "100,50", "100,00")


class TestConstruirAoAvaliar(unittest.TestCase):
    """Registro CSV de fechamentos e sinais — item da proposta (Opção A, herdado pela B) que
    ficava descumprido quando o app rodava pela janela: Monitor recebia self.fila.put direto,
    sem nunca passar por um Registro."""

    def test_grava_no_registro_antes_de_publicar_na_fila(self):
        registro = MagicMock()
        fila: "queue.Queue[Avaliacao]" = queue.Queue()
        ao_avaliar = construir_ao_avaliar(registro, fila)
        av = _avaliacao()

        ao_avaliar(av)

        registro.gravar.assert_called_once_with(av)
        self.assertEqual(fila.get_nowait(), av)

    def test_cada_avaliacao_grava_e_publica_uma_vez(self):
        registro = MagicMock()
        fila: "queue.Queue[Avaliacao]" = queue.Queue()
        ao_avaliar = construir_ao_avaliar(registro, fila)
        av1, av2 = _avaliacao("BTCUSDT", 0), _avaliacao("ETHUSDT", 900_000)

        ao_avaliar(av1)
        ao_avaliar(av2)

        registro.gravar.assert_has_calls([call(av1), call(av2)])
        self.assertEqual(registro.gravar.call_count, 2)
        self.assertEqual([fila.get_nowait(), fila.get_nowait()], [av1, av2])


class TestAbrirOutrasVersoes(unittest.TestCase):
    """Link/botão "Conhecer outras versões" (Opção A/B, versão com IA) — pedido do Hugo/Lucas em
    19/09/2026 pra já ir acessível a partir da versão que vai pro cliente agora como MVP, mesmo
    a página de destino ainda não existindo (ver o TODO em cima de URL_OUTRAS_VERSOES)."""

    def test_abre_a_url_configurada_no_navegador(self):
        with patch("janela.webbrowser.open") as abrir_mock:
            abrir_outras_versoes()

        abrir_mock.assert_called_once_with(URL_OUTRAS_VERSOES)

    def test_url_configurada_e_https(self):
        # não trava qual site é (pode mudar quando a página de verdade existir), só garante que
        # nunca fica um link quebrado/vazio no material que já foi pro cliente.
        self.assertTrue(URL_OUTRAS_VERSOES.startswith("https://"))


class TestAlturaMaximaDoQuadro(unittest.TestCase):
    """Teto de altura do quadro de situação (16 pares, 23/09/2026). O que não pode acontecer é a
    janela passar da tela e levar os botões Iniciar/Parar para fora do alcance do cliente."""

    def test_sobra_de_tela_vira_espaco_do_quadro(self):
        # 1080 px de tela, 90% = 972; com 550 px de resto sobram 422 para o quadro
        self.assertEqual(altura_maxima_do_quadro(1080, 550), 422)

    def test_notebook_baixo_aperta_o_quadro(self):
        self.assertEqual(altura_maxima_do_quadro(768, 545), 146)

    def test_nunca_devolve_menos_que_o_minimo(self):
        self.assertEqual(altura_maxima_do_quadro(768, 900), 120)
        self.assertEqual(altura_maxima_do_quadro(600, 700, minimo=80), 80)

    def test_tela_larga_de_notebook_comum_usa_duas_colunas(self):
        self.assertGreaterEqual(1366, LARGURA_MIN_LADO_A_LADO)


if __name__ == "__main__":
    unittest.main()


class TestBandejaHabilitada(unittest.TestCase):
    """Bandeja só no Windows (20/09/2026): fora dele o laço GTK do pystray engole cliques do Tk —
    medido com clique sintético no Ubuntu, 1/5 com bandeja contra 4/5 sem."""

    def _com_ambiente(self, plataforma, variavel):
        with patch.object(janela.sys, "platform", plataforma), \
             patch.dict(janela.os.environ, {} if variavel is None else {"ALERTA_FUTUROS_BANDEJA": variavel},
                             clear=False):
            if variavel is None:
                janela.os.environ.pop("ALERTA_FUTUROS_BANDEJA", None)
            return janela._bandeja_habilitada()

    def test_ligada_no_windows_desligada_fora(self):
        self.assertTrue(self._com_ambiente("win32", None))
        self.assertFalse(self._com_ambiente("linux", None))
        self.assertFalse(self._com_ambiente("darwin", None))

    def test_variavel_de_ambiente_tem_a_ultima_palavra(self):
        self.assertTrue(self._com_ambiente("linux", "1"))
        self.assertFalse(self._com_ambiente("win32", "0"))
