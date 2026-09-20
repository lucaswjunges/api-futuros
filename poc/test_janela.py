"""Testa só a lógica de janela.py que não depende de um tk.Tk() real (widgets em si continuam
cobertos pelo smoke test manual — ver o combinado no PR). O que dá pra testar sem GUI é
justamente onde o bug do CSV faltando (corrigido em 19/09/2026) escapou: nada verificava que
o ao_avaliar usado pela janela também grava no Registro, igual o CLI já fazia."""

import queue
import unittest
from unittest.mock import MagicMock, call, patch

from alerta_futuros import Avaliacao
from janela import URL_OUTRAS_VERSOES, abrir_outras_versoes, construir_ao_avaliar


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


if __name__ == "__main__":
    unittest.main()
