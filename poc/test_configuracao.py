import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alerta_futuros import LIMITE_PARES, PARES, Parametros
from configuracao import Configuracao, carregar, salvar, validar, validar_pares


class TestSalvarCarregar(unittest.TestCase):
    def test_ida_e_volta_preserva_valores(self):
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            original = Configuracao(
                parametros=Parametros(rsi_acima=95.0, rsi_abaixo=3.0, setor_pct=25.0),
                iniciar_com_windows=True,
            )
            salvar(original, caminho)
            lido = carregar(caminho)
            self.assertEqual(lido.parametros.rsi_acima, 95.0)
            self.assertEqual(lido.parametros.rsi_abaixo, 3.0)
            self.assertEqual(lido.parametros.setor_pct, 25.0)
            self.assertTrue(lido.iniciar_com_windows)

    def test_arquivo_inexistente_volta_padrao(self):
        with TemporaryDirectory() as tmp:
            lido = carregar(Path(tmp) / "nao-existe.json")
            self.assertEqual(lido, Configuracao())

    def test_arquivo_corrompido_nao_derruba_o_app(self):
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            caminho.write_text("{ isso nao é json valido", encoding="utf-8")
            lido = carregar(caminho)
            self.assertEqual(lido, Configuracao())

    def test_campo_desconhecido_e_ignorado_sem_quebrar(self):
        """Simula um config.json salvo por uma versão futura, com um campo que ainda não existe."""
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            caminho.write_text(
                json.dumps({"parametros": {"rsi_acima": 92.0, "campo_do_futuro": 123}}),
                encoding="utf-8",
            )
            lido = carregar(caminho)
            self.assertEqual(lido.parametros.rsi_acima, 92.0)

    def test_grava_de_forma_atomica_sem_deixar_temporario(self):
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            salvar(Configuracao(), caminho)
            restantes = list(Path(tmp).iterdir())
            self.assertEqual(restantes, [caminho])


class TestParesNaConfiguracao(unittest.TestCase):
    """A lista de pares passou a ser salva em 23/09/2026, quando o teto subiu de 8 para 16."""

    def test_ida_e_volta_preserva_a_lista_e_a_ordem(self):
        pares = ["ETHUSDT", "BTCUSDT", "ADAUSDT"]
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            salvar(Configuracao(pares=pares), caminho)
            self.assertEqual(carregar(caminho).pares, pares)

    def test_config_antigo_sem_a_chave_volta_com_os_8_originais(self):
        """Quem já usava o app tem um config.json anterior a esta versão: abrir tem que continuar
        funcionando, com exatamente os pares que ele já via."""
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            caminho.write_text(json.dumps({"parametros": {"rsi_acima": 92.0}}), encoding="utf-8")
            self.assertEqual(carregar(caminho).pares, list(PARES))

    def test_lista_estragada_no_arquivo_nao_derruba_o_app(self):
        for valor in ("BTCUSDT", [], [123, None], ["nao vale"], ["BTCUSDT"] * (LIMITE_PARES + 1)):
            with TemporaryDirectory() as tmp:
                caminho = Path(tmp) / "config.json"
                caminho.write_text(json.dumps({"pares": valor}), encoding="utf-8")
                self.assertEqual(carregar(caminho).pares, list(PARES), valor)

    def test_maiusculas_e_espacos_sao_normalizados_na_leitura(self):
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            caminho.write_text(json.dumps({"pares": [" btcusdt ", "EthUsdt"]}), encoding="utf-8")
            self.assertEqual(carregar(caminho).pares, ["BTCUSDT", "ETHUSDT"])


class TestValidarPares(unittest.TestCase):
    def test_os_8_originais_sao_validos(self):
        self.assertEqual(validar_pares(list(PARES)), [])

    def test_no_teto_de_16_ainda_e_valido(self):
        self.assertEqual(validar_pares([f"AA{i:02d}USDT" for i in range(LIMITE_PARES)]), [])

    def test_acima_do_teto_diz_quantos_tirar(self):
        erros = validar_pares([f"AA{i:02d}USDT" for i in range(LIMITE_PARES + 3)])
        self.assertTrue(erros)
        self.assertIn("Tire 3", erros[0])

    def test_lista_vazia_e_invalida(self):
        self.assertTrue(validar_pares([]))

    def test_repetido_e_apontado_uma_vez_so(self):
        erros = validar_pares(["BTCUSDT", "BTCUSDT", "BTCUSDT", "ETHUSDT"])
        self.assertEqual(len(erros), 1)
        self.assertIn("BTCUSDT", erros[0])

    def test_simbolo_com_pontuacao_e_recusado(self):
        erros = validar_pares(["BTC/USDT"])
        self.assertTrue(erros)
        self.assertIn("BTC/USDT", erros[0])


class TestValidar(unittest.TestCase):
    def test_parametros_padrao_sao_validos(self):
        self.assertEqual(validar(Parametros()), [])

    def test_exemplos_da_proposta_sao_validos(self):
        # "testar variações da estratégia (por exemplo, RSI 95/3 ou setores de 25%)" — Seção 5
        self.assertEqual(validar(Parametros(rsi_acima=95.0, rsi_abaixo=3.0)), [])
        self.assertEqual(validar(Parametros(setor_pct=25.0)), [])

    def test_rsi_abaixo_maior_que_acima_e_invalido(self):
        self.assertTrue(validar(Parametros(rsi_acima=10.0, rsi_abaixo=20.0)))

    def test_rsi_acima_acima_de_100_e_invalido(self):
        self.assertTrue(validar(Parametros(rsi_acima=101.0)))

    def test_setor_pct_50_ou_mais_e_invalido(self):
        # setor_pct >= 50 não deixa espaço pro setor B (meio)
        self.assertTrue(validar(Parametros(setor_pct=50.0)))

    def test_tamanho_min_negativo_e_invalido(self):
        self.assertTrue(validar(Parametros(tamanho_min_pct=-0.01)))

    def test_ajuste_pct_zero_ou_negativo_e_invalido(self):
        self.assertTrue(validar(Parametros(ajuste_pct=0.0)))
        self.assertTrue(validar(Parametros(ajuste_pct=-0.5)))


if __name__ == "__main__":
    unittest.main()
