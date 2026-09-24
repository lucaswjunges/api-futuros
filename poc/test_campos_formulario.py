import unittest

from alerta_futuros import Parametros
from campos_formulario import (
    CampoInvalido, pares_do_texto, parametros_dos_textos, texto_do_parametro, texto_dos_pares, textos_de,
)

PADRAO = Parametros()


def _textos(**sobrescreve):
    base = {
        "rsi_acima": "90",
        "rsi_abaixo": "5",
        "setor_pct": "30",
        "tamanho_min_pct": "0,020",
        "ajuste_pct": "0,5",
    }
    base.update(sobrescreve)
    return base


class TestTextoDoParametro(unittest.TestCase):
    def test_numero_inteiro_sem_zeros_a_mais(self):
        self.assertEqual(texto_do_parametro(90.0), "90")

    def test_decimal_usa_virgula(self):
        self.assertEqual(texto_do_parametro(0.02), "0,02")

    def test_ida_e_volta_com_os_padroes_de_parametros(self):
        for campo, texto in textos_de(PADRAO).items():
            self.assertEqual(getattr(PADRAO, campo), float(texto.replace(",", ".")))


class TestParametrosDosTextos(unittest.TestCase):
    def test_le_os_valores_padrao(self):
        p = parametros_dos_textos(_textos(), PADRAO)
        self.assertEqual((p.rsi_acima, p.rsi_abaixo, p.setor_pct), (90.0, 5.0, 30.0))

    def test_aceita_virgula_e_ponto_decimal(self):
        p1 = parametros_dos_textos(_textos(tamanho_min_pct="0,020"), PADRAO)
        p2 = parametros_dos_textos(_textos(tamanho_min_pct="0.020"), PADRAO)
        self.assertEqual(p1.tamanho_min_pct, p2.tamanho_min_pct)

    def test_exemplo_da_proposta_rsi_95_3(self):
        p = parametros_dos_textos(_textos(rsi_acima="95", rsi_abaixo="3"), PADRAO)
        self.assertEqual((p.rsi_acima, p.rsi_abaixo), (95.0, 3.0))

    def test_mantem_campos_que_a_janela_nao_edita(self):
        base = Parametros(popup_segundos=7, velas_aquecimento=100)
        p = parametros_dos_textos(_textos(), base)
        self.assertEqual((p.popup_segundos, p.velas_aquecimento), (7, 100))

    def test_texto_nao_numerico_da_erro_com_o_nome_do_campo(self):
        with self.assertRaises(CampoInvalido) as ctx:
            parametros_dos_textos(_textos(rsi_acima="noventa"), PADRAO)
        self.assertIn("RSI — limite Acima", str(ctx.exception))

    def test_campo_ausente_do_formulario_da_erro_claro(self):
        textos = _textos()
        del textos["ajuste_pct"]
        with self.assertRaises(CampoInvalido):
            parametros_dos_textos(textos, PADRAO)


class TestParesDoTexto(unittest.TestCase):
    """Campo "Pares acompanhados" da janela (teto de 16, 23/09/2026). O cliente cola a lista do
    jeito que tiver em mãos, então o campo tem que aceitar qualquer pontuação razoável."""

    def test_separadores_aceitos(self):
        esperado = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        self.assertEqual(pares_do_texto("BTCUSDT ETHUSDT SOLUSDT"), esperado)
        self.assertEqual(pares_do_texto("BTCUSDT, ETHUSDT, SOLUSDT"), esperado)
        self.assertEqual(pares_do_texto("BTCUSDT;ETHUSDT/SOLUSDT"), esperado)
        self.assertEqual(pares_do_texto("BTCUSDT\nETHUSDT\n\nSOLUSDT\n"), esperado)

    def test_normaliza_para_maiusculas(self):
        self.assertEqual(pares_do_texto("btcusdt ethUsdt"), ["BTCUSDT", "ETHUSDT"])

    def test_campo_vazio_ou_so_pontuacao_vira_lista_vazia(self):
        # lista vazia é o que faz validar_pares avisar "escolha pelo menos um par"
        self.assertEqual(pares_do_texto("   \n  "), [])
        self.assertEqual(pares_do_texto(" , ; "), [])

    def test_mantem_repetidos_para_quem_valida_poder_avisar(self):
        self.assertEqual(pares_do_texto("BTCUSDT BTCUSDT"), ["BTCUSDT", "BTCUSDT"])

    def test_ida_e_volta_pelo_texto_do_campo(self):
        pares = ["BTCUSDT", "ETHUSDT", "ADAUSDT"]
        self.assertEqual(pares_do_texto(texto_dos_pares(pares)), pares)


if __name__ == "__main__":
    unittest.main()
