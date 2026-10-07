"""Versão 1.1 — fator de ajuste do preço-alvo próprio por par (pedido do cliente em 05/10/2026).

O fator geral (Parametros.ajuste_pct) continua valendo para quem não tem um próprio; config.json
da 1.0, sem o campo novo, abre igual; valor inválido é recusado; W e Z saem com o fator do par."""

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from alerta_futuros import PARES, Ativo, Parametros, Registro, Vela, cruzamento
from campos_formulario import CampoInvalido, ajustes_dos_campos
from configuracao import Configuracao, carregar, salvar, validar


class TestCalculoDoAlvo(unittest.TestCase):
    def setUp(self):
        self.p = Parametros(ajuste_pct=0.5, ajuste_por_par={"ETHUSDT": 0.8})

    def test_par_com_fator_proprio(self):
        self.assertAlmostEqual(cruzamento("ACIMA", "A", 1000.0, self.p, "ETHUSDT")[1], 1008.0)  # W
        self.assertAlmostEqual(cruzamento("ABAIXO", "C", 1000.0, self.p, "ETHUSDT")[1], 992.0)  # Z

    def test_par_sem_fator_usa_o_geral(self):
        self.assertAlmostEqual(cruzamento("ACIMA", "A", 1000.0, self.p, "BTCUSDT")[1], 1005.0)
        self.assertAlmostEqual(cruzamento("ABAIXO", "C", 1000.0, self.p, "BTCUSDT")[1], 995.0)

    def test_sem_simbolo_usa_o_geral_como_na_1_0(self):
        self.assertAlmostEqual(cruzamento("ACIMA", "A", 1000.0, self.p)[1], 1005.0)

    def test_fator_nao_muda_quando_ha_sinal(self):
        self.assertIsNone(cruzamento("ACIMA", "B", 1000.0, self.p, "ETHUSDT"))
        self.assertIsNone(cruzamento(None, "A", 1000.0, self.p, "ETHUSDT"))

    def test_ativo_do_motor_usa_o_fator_do_proprio_par(self):
        """Do fechamento da vela até o Avaliacao.alvo, pelo mesmo caminho do monitor ao vivo."""
        p = Parametros(ajuste_pct=0.5, ajuste_por_par={"ETHUSDT": 2.0}, rsi_acima=50.0, rsi_abaixo=1.0)
        alvos = {}
        for simbolo in ("ETHUSDT", "BTCUSDT"):
            ativo = Ativo(simbolo, 2, p)
            ativo.carregar_historico([Vela(i * 300_000, 100, 100, 100, 100 - (i % 2)) for i in range(30)])
            # 3 velas 5m da mesma janela de 15m subindo; fecha na máxima => setor A, RSI alto => ACIMA
            base = 30 * 300_000 // 900_000 * 900_000 + 900_000
            ativo.velas.clear()
            ativo.ultima_abertura = base - 300_000
            for k, fecha in enumerate((101.0, 102.0, 103.0)):
                av = ativo.fechar_vela(Vela(base + k * 300_000, fecha - 1, fecha, fecha - 1, fecha))
            self.assertEqual(av.sinal, "X", simbolo)
            self.assertEqual(av.ajuste_pct, 2.0 if simbolo == "ETHUSDT" else 0.5)  # vai pro pop-up e CSV
            alvos[simbolo] = av.alvo
        self.assertAlmostEqual(alvos["ETHUSDT"], 103.0 * 1.02)
        self.assertAlmostEqual(alvos["BTCUSDT"], 103.0 * 1.005)


class TestRegistroCsv(unittest.TestCase):
    def test_fator_do_par_vai_na_ultima_coluna(self):
        from test_janela import _avaliacao
        with TemporaryDirectory() as tmp:
            registro = Registro(Path(tmp))
            av = _avaliacao()
            av.ajuste_pct = 0.8
            registro.gravar(av)
            registro.fechar()
            cabecalho, linha = registro.caminho.read_text(encoding="utf-8").splitlines()
        self.assertEqual(cabecalho.split(";")[-1], "fator_pct")
        self.assertEqual(cabecalho.split(";")[:14], Registro.CAMPOS[:14])  # colunas da 1.0 no mesmo lugar
        self.assertEqual(linha.split(";")[-1], "0.8")


class TestConfigJson(unittest.TestCase):
    def test_ida_e_volta(self):
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            salvar(Configuracao(parametros=Parametros(ajuste_por_par={"ETHUSDT": 0.8, "SOLUSDT": 1.25})),
                   caminho)
            self.assertEqual(carregar(caminho).parametros.ajuste_por_par, {"ETHUSDT": 0.8, "SOLUSDT": 1.25})

    def test_config_da_1_0_abre_igual(self):
        """Exatamente o formato que a 1.0 grava: sem ajuste_por_par."""
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            caminho.write_text(json.dumps({
                "parametros": {"rsi_periodo": 2, "rsi_acima": 95.0, "rsi_abaixo": 3.0, "setor_pct": 30.0,
                               "tamanho_min_pct": 0.02, "ajuste_pct": 0.7, "popup_segundos": 10,
                               "velas_aquecimento": 300},
                "iniciar_com_windows": True, "pares": ["BTCUSDT", "ETHUSDT"]}), encoding="utf-8")
            lido = carregar(caminho)
            self.assertEqual(lido.parametros.ajuste_por_par, {})
            self.assertEqual(lido.parametros.ajuste_pct, 0.7)
            self.assertEqual(lido.parametros.rsi_acima, 95.0)
            self.assertEqual(lido.pares, ["BTCUSDT", "ETHUSDT"])
            self.assertTrue(lido.iniciar_com_windows)

    def test_entrada_estragada_e_descartada_sem_levar_as_outras(self):
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            caminho.write_text(json.dumps({"parametros": {"ajuste_por_par": {
                "ethusdt": 0.8, "SOLUSDT": "abc", "XRPUSDT": -1, "BNBUSDT": True, "??": 1, "LTCUSDT": "1.5"}}}),
                encoding="utf-8")
            self.assertEqual(carregar(caminho).parametros.ajuste_por_par, {"ETHUSDT": 0.8, "LTCUSDT": 1.5})

    def test_campo_que_nao_e_dicionario_vira_vazio(self):
        with TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "config.json"
            caminho.write_text(json.dumps({"parametros": {"ajuste_por_par": [1, 2]}}), encoding="utf-8")
            self.assertEqual(carregar(caminho).parametros.ajuste_por_par, {})


class TestValidacao(unittest.TestCase):
    def test_valor_menor_ou_igual_a_zero_e_invalido(self):
        for ruim in (0.0, -0.5, 100.0):
            with self.subTest(ruim=ruim):
                erros = validar(Parametros(ajuste_por_par={"ETHUSDT": ruim}))
                self.assertTrue(any("ETHUSDT" in e for e in erros))

    def test_valor_bom_passa(self):
        self.assertEqual(validar(Parametros(ajuste_por_par={"ETHUSDT": 0.8})), [])


class TestCamposDaJanelinha(unittest.TestCase):
    def test_virgula_ou_ponto_e_branco_usa_o_geral(self):
        self.assertEqual(ajustes_dos_campos({"ETHUSDT": "0,8", "SOLUSDT": " 1.25 ", "BTCUSDT": "  "}),
                         {"ETHUSDT": 0.8, "SOLUSDT": 1.25})

    def test_texto_que_nao_e_numero_aponta_o_par(self):
        with self.assertRaises(CampoInvalido) as ctx:
            ajustes_dos_campos({"ETHUSDT": "0,8", "SOLUSDT": "um"})
        self.assertEqual(ctx.exception.campo, "SOLUSDT")
        self.assertIn("SOLUSDT", str(ctx.exception))


def _tem_tela() -> bool:
    try:
        tk.Tk().destroy()
        return True
    except tk.TclError:
        return False


@unittest.skipUnless(_tem_tela(), "sem tela para montar um tk.Tk() (no Linux, rode com xvfb-run)")
class TestJanelaComFatorPorPar(unittest.TestCase):
    """A janela de verdade: campo novo salva no Iniciar, recusa erro, trava rodando, sobrevive ao zoom."""

    def setUp(self):
        from janela import Aplicativo
        self.root = tk.Tk()
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.root.destroy)
        patch.object(self.root, "after", return_value="teste").start()
        patch.object(Aplicativo, "_configurar_bandeja").start()
        patch("janela.pares_desconhecidos", return_value=[]).start()
        patch("janela.resolver_pares", side_effect=lambda pares: {s: 2 for s in pares}).start()
        patch("janela.Registro").start()
        self.monitor = patch("janela.Monitor").start()
        patch("janela.threading.Thread").start()
        patch("janela.Aplicativo._aplicar_inicio_automatico").start()
        self.addCleanup(patch.stopall)
        self.caminho = Path(self.tmp.name) / "config.json"
        self.app = Aplicativo(self.root, self.caminho)
        self.app.popups = MagicMock()

    def definir(self, valores):
        """Abre a janelinha, preenche as caixas e aperta OK, como o cliente faria."""
        self.app.abrir_ajustes()
        for simbolo, texto in valores.items():
            self.app.entradas_ajuste[simbolo].delete(0, "end")
            self.app.entradas_ajuste[simbolo].insert(0, texto)
        return self.app.confirmar_ajustes()

    def test_janelinha_lista_os_pares_da_tela(self):
        self.app.entrada_pares.delete("1.0", "end")
        self.app.entrada_pares.insert("1.0", "btcusdt ETHUSDT ETHUSDT")
        self.app.abrir_ajustes()
        self.assertEqual(list(self.app.entradas_ajuste), ["BTCUSDT", "ETHUSDT"])

    def test_ok_e_iniciar_salvam_e_entregam_ao_motor(self):
        self.assertTrue(self.definir({"ETHUSDT": "0,8"}))
        self.assertIn("1 próprio", self.app.link_ajustes.cget("text"))
        self.app.iniciar()
        self.assertEqual(self.app.rotulo_erro.cget("text"), "")
        parametros = self.monitor.call_args[0][0]
        self.assertEqual(parametros.ajuste_por_par, {"ETHUSDT": 0.8})
        self.assertEqual(parametros.ajuste_pct, 0.5)  # o geral não muda
        self.assertEqual(carregar(self.caminho).parametros.ajuste_por_par, {"ETHUSDT": 0.8})

    def test_sem_fator_proprio_e_a_1_0(self):
        self.app.iniciar()
        self.assertEqual(self.monitor.call_args[0][0].ajuste_por_par, {})
        self.assertEqual(self.app.link_ajustes.cget("text"), "Fator por par…")

    def test_valor_invalido_e_recusado_na_janelinha(self):
        for ruim in ("0", "-1", "abc", "150"):
            with self.subTest(ruim=ruim):
                self.assertFalse(self.definir({"ETHUSDT": ruim}))
                self.assertIn("ETHUSDT", self.app.rotulo_erro_ajustes.cget("text"))
                self.assertEqual(str(self.app.entradas_ajuste["ETHUSDT"].cget("highlightbackground")),
                                 janela_cor_vermelha())
                self.app.janela_ajustes.destroy()
        self.assertEqual(self.app.ajustes, {})

    def test_cancelar_nao_muda_nada(self):
        self.app.abrir_ajustes()
        self.app.entradas_ajuste["ETHUSDT"].insert(0, "0,8")
        self.app.janela_ajustes.destroy()
        self.assertEqual(self.app.ajustes, {})

    def test_travado_com_o_monitor_rodando(self):
        self.app.iniciar()
        self.app.abrir_ajustes()
        self.assertIsNone(self.app.janela_ajustes)

    def test_par_que_sai_da_lista_leva_o_fator_junto(self):
        self.definir({"ETHUSDT": "0,8", "SOLUSDT": "1,2"})
        self.app.entrada_pares.delete("1.0", "end")
        self.app.entrada_pares.insert("1.0", "BTCUSDT ETHUSDT")
        self.app.iniciar()
        self.assertEqual(self.monitor.call_args[0][0].ajuste_por_par, {"ETHUSDT": 0.8})

    def test_reabrir_mostra_o_que_foi_salvo(self):
        from janela import Aplicativo
        self.definir({"ETHUSDT": "0,8"})
        self.app.iniciar()
        outro = Aplicativo(self.root, self.caminho)
        outro.abrir_ajustes()
        self.assertEqual(outro.entradas_ajuste["ETHUSDT"].get(), "0,8")
        self.assertEqual(outro.entradas_ajuste["BTCUSDT"].get(), "")

    def test_exemplo_de_alerta_usa_o_fator_do_par(self):
        self.definir({"BTCUSDT": "1"})
        self.app.mostrar_exemplo()
        av = self.app.popups.mostrar.call_args[0][0]
        self.assertEqual(av.simbolo, "BTCUSDT")
        self.assertEqual(av.ajuste_pct, 1.0)
        self.assertAlmostEqual(av.alvo, av.fechamento * 1.01)

    def test_zoom_mantem_os_fatores(self):
        self.definir({"ETHUSDT": "0,8"})
        self.app.aplicar_zoom(1.5)
        self.assertEqual(self.app.ajustes, {"ETHUSDT": 0.8})
        self.assertIn("1 próprio", self.app.link_ajustes.cget("text"))


def janela_cor_vermelha():
    from janela import VERMELHO
    return VERMELHO

if __name__ == "__main__":
    unittest.main()
