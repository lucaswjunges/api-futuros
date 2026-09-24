"""Testa a parte de componentes.py e tema.py que não precisa de um tk.Tk() real: a geometria que
os desenhos usam (setores da vela, posição no eixo), o texto/cor do indicador de estado, o cálculo
da próxima avaliação e a escolha de fonte/escala. Os widgets em si continuam cobertos pelo smoke
test manual (captura em evidencias/visual/)."""

import unittest
from datetime import datetime

from campos_formulario import CampoInvalido, parametros_dos_textos
from alerta_futuros import Parametros
from componentes import (
    CORES_ESTADO, altura_visivel_das_linhas, alturas_setores, estado_do_monitor, posicao_no_eixo,
    proxima_avaliacao,
)
from tema import escala_de, primeira_familia_disponivel


class TestAlturasSetores(unittest.TestCase):
    """A vela desenhada tem que dividir a altura igual à regra (setor_vela15): A e C com
    setor_pct % de cada ponta, B com o resto — sem sobrar nem faltar um pixel."""

    def test_padrao_30_por_cento(self):
        self.assertEqual(alturas_setores(100, 30.0), (30, 40, 30))

    def test_sempre_soma_a_altura(self):
        for altura in (56, 64, 100):
            for pct in (0.0, 12.5, 30.0, 33.3, 49.0, 50.0):
                self.assertEqual(sum(alturas_setores(altura, pct)), altura, (altura, pct))

    def test_grampeia_fora_de_0_a_50(self):
        self.assertEqual(alturas_setores(100, -5.0), (0, 100, 0))
        self.assertEqual(alturas_setores(100, 80.0), (50, 0, 50))


class TestPosicaoNoEixo(unittest.TestCase):
    def test_extremos_e_meio(self):
        self.assertEqual(posicao_no_eixo(0, 92, 160), 92)
        self.assertEqual(posicao_no_eixo(100, 92, 160), 252)
        self.assertEqual(posicao_no_eixo(50, 92, 160), 172)

    def test_rsi_fora_de_0_a_100_fica_na_ponta(self):
        self.assertEqual(posicao_no_eixo(-3, 92, 160), 92)
        self.assertEqual(posicao_no_eixo(140, 92, 160), 252)


class TestEstadoDoMonitor(unittest.TestCase):
    def test_sequencia_de_uma_sessao(self):
        self.assertEqual(estado_do_monitor(False, False, False, 0), ("parado", "Parado"))
        self.assertEqual(estado_do_monitor(True, True, False, 0), ("conectando", "Conectando…"))
        self.assertEqual(estado_do_monitor(True, True, True, 0), ("conectado", "Conectado"))
        self.assertEqual(estado_do_monitor(True, True, False, 2), ("reconectando", "Reconectando… (tentativa 2)"))
        self.assertEqual(estado_do_monitor(True, False, False, 2), ("encerrado", "Encerrado"))

    def test_toda_chave_tem_cor(self):
        for chave in ("parado", "conectando", "conectado", "reconectando", "encerrado"):
            self.assertIn(chave, CORES_ESTADO)


class TestProximaAvaliacao(unittest.TestCase):
    """Só os fechamentos de :00/:15/:30/:45 mudam o quadro (item 4.5-b)."""

    def test_arredonda_para_o_proximo_quarto_de_hora(self):
        self.assertEqual(proxima_avaliacao(datetime(2026, 9, 22, 12, 7, 10)), datetime(2026, 9, 22, 12, 15))
        self.assertEqual(proxima_avaliacao(datetime(2026, 9, 22, 12, 15, 30)), datetime(2026, 9, 22, 12, 30))
        self.assertEqual(proxima_avaliacao(datetime(2026, 9, 22, 12, 59, 59)), datetime(2026, 9, 22, 13, 0))

    def test_vira_o_dia(self):
        self.assertEqual(proxima_avaliacao(datetime(2026, 9, 22, 23, 50)), datetime(2026, 9, 23, 0, 0))


class TestAlturaVisivelDasLinhas(unittest.TestCase):
    """Quanto do quadro de situação aparece sem rolagem (teto de 16 pares, 23/09/2026).
    Medidas de projeto: linha 25 px, respiro do rodapé 8 px."""

    def test_sem_limite_mostra_tudo_e_nao_rola(self):
        self.assertEqual(altura_visivel_das_linhas(16, 25, 8, None), (408, False))

    def test_cabendo_na_altura_disponivel_nao_rola(self):
        self.assertEqual(altura_visivel_das_linhas(8, 25, 8, 300), (208, False))

    def test_no_limite_exato_ainda_nao_rola(self):
        self.assertEqual(altura_visivel_das_linhas(8, 25, 8, 208), (208, False))

    def test_nao_cabendo_corta_em_linha_inteira_e_rola(self):
        # 146 px dão 5 linhas de 25; a sobra de 21 px seria uma fatia de linha na borda
        self.assertEqual(altura_visivel_das_linhas(16, 25, 8, 146), (125, True))

    def test_altura_minuscula_ainda_mostra_uma_linha(self):
        self.assertEqual(altura_visivel_das_linhas(16, 25, 8, 10), (25, True))

    def test_sem_pares_nao_rola(self):
        self.assertEqual(altura_visivel_das_linhas(0, 25, 8, 300), (8, False))


class TestTema(unittest.TestCase):
    def test_escolhe_a_primeira_fonte_que_existe(self):
        preferidas = ("Bahnschrift", "Segoe UI", "Helvetica")
        self.assertEqual(primeira_familia_disponivel(preferidas, ["Arial", "Segoe UI"]), "Segoe UI")
        self.assertEqual(primeira_familia_disponivel(preferidas, ["Bahnschrift", "Segoe UI"]), "Bahnschrift")

    def test_sem_nenhuma_fonte_cai_no_alias_final(self):
        # 'Helvetica' nunca aparece na lista do Tk, mas ele sempre resolve o alias — é a rede de
        # segurança que evita os blocos ilegíveis vistos no Ubuntu em 20/09/2026.
        self.assertEqual(primeira_familia_disponivel(("Bahnschrift", "Helvetica"), ["DejaVu Sans"]), "Helvetica")

    def test_escala_de_dpi(self):
        self.assertEqual(escala_de(96), 1.0)
        self.assertEqual(escala_de(120), 1.25)
        self.assertEqual(escala_de(144), 1.5)

    def test_dpi_absurdo_vira_escala_1(self):
        self.assertEqual(escala_de(0), 1.0)
        self.assertEqual(escala_de(10_000), 1.0)


class TestCampoInvalidoSabeOCampo(unittest.TestCase):
    """A janela destaca em vermelho o campo que falhou — pra isso o erro precisa dizer qual foi."""

    def test_erro_de_numero_traz_a_chave_do_campo(self):
        textos = {"rsi_acima": "90", "rsi_abaixo": "cinco", "setor_pct": "30", "tamanho_min_pct": "0,02", "ajuste_pct": "0,5"}
        with self.assertRaises(CampoInvalido) as ctx:
            parametros_dos_textos(textos, Parametros())
        self.assertEqual(ctx.exception.campo, "rsi_abaixo")

    def test_campo_ausente_nao_aponta_campo_unico(self):
        with self.assertRaises(CampoInvalido) as ctx:
            parametros_dos_textos({"rsi_acima": "90"}, Parametros())
        self.assertIsNone(ctx.exception.campo)


if __name__ == "__main__":
    unittest.main()
