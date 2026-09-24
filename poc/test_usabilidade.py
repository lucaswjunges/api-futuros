"""Testes do que o teste de usabilidade de 21/09/2026 definiu (branch local feature/usabilidade-
monitoramento, nunca publicada) e que foi reintroduzido em 24/09/2026 por cima do redesenho visual e
dos 16 pares: status que explica o que está acontecendo, barra de espera animada, "sem sinal" no
quadro, exemplo de alerta, ajuda, histórico fora da pasta temporária do .exe e a janela que se
recupera sozinha quando o motor cai.

Os testes de TestJanelaReal montam um tk.Tk() de verdade (no CI Windows tem tela; no Linux, rode
com xvfb-run). Sem tela, são pulados — as funções puras continuam testadas.
"""

import queue
import sys
import tempfile
import time
import tkinter as tk
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import janela
from componentes import contagem_regressiva, fracao_do_intervalo
from janela import Aplicativo, executar_motor, mensagens_de_status, zoom_para
from test_janela import _avaliacao


class TestMensagensDeStatus(unittest.TestCase):
    def test_conectado_sem_avaliacao_nao_promete_sinal(self):
        titulo, texto = mensagens_de_status("conectado", 16, None, False, 0)
        self.assertEqual(titulo, "Monitoramento ativo · 16 pares")
        self.assertIn("só aparece se a regra acontecer", texto)

    def test_conectado_com_avaliacao_explica_sem_sinal(self):
        _, texto = mensagens_de_status("conectado", 8, "12:15", False, 0)
        self.assertIn("12:15", texto)
        self.assertIn("Sem sinal", texto)

    def test_conectando_vira_aviso_de_demora(self):
        self.assertIn("Conectando", mensagens_de_status("conectando", 8, None, False, 0)[0])
        self.assertIn("demorando", mensagens_de_status("conectando", 8, None, True, 0)[0])

    def test_reconectando_diz_quantas_tentativas(self):
        titulo, texto = mensagens_de_status("reconectando", 8, None, False, 3)
        self.assertIn("Sem conexão", titulo)
        self.assertIn("3 tentativa", texto)

    def test_um_par_no_singular(self):
        self.assertIn("1 par", mensagens_de_status("conectado", 1, None, False, 0)[0])

    def test_encerrado_orienta_a_tentar_de_novo(self):
        self.assertIn("Iniciar", mensagens_de_status("encerrado", 8, None, False, 0)[1])


class TestTempoAteAvaliacao(unittest.TestCase):
    def test_fracao_do_intervalo_de_15_minutos(self):
        self.assertEqual(fracao_do_intervalo(datetime(2026, 9, 24, 10, 0, 0)), 0.0)
        self.assertAlmostEqual(fracao_do_intervalo(datetime(2026, 9, 24, 10, 7, 30)), 0.5)
        self.assertAlmostEqual(fracao_do_intervalo(datetime(2026, 9, 24, 10, 29, 59)), 899 / 900)

    def test_contagem_regressiva(self):
        agora = datetime(2026, 9, 24, 10, 14, 1)
        self.assertEqual(contagem_regressiva(agora, datetime(2026, 9, 24, 10, 15)), "00:59")
        self.assertEqual(contagem_regressiva(agora, datetime(2026, 9, 24, 10, 0)), "00:00")


class TestZoomTelaCheia(unittest.TestCase):
    """Pedido do cliente (23/09/2026): usar a tela toda num notebook dedicado ao app."""

    def test_amplia_ate_caber_na_menor_proporcao(self):
        self.assertEqual(zoom_para((1196, 667), (1920, 1040)), 1.5)

    def test_nunca_encolhe_nem_passa_do_maximo(self):
        self.assertEqual(zoom_para((1196, 667), (1000, 600)), 1.0)
        self.assertEqual(zoom_para((500, 300), (3840, 2160)), 2.2)

    def test_tamanhos_invalidos_ficam_em_1(self):
        self.assertEqual(zoom_para((0, 0), (1920, 1080)), 1.0)


class TestPastaDoHistorico(unittest.TestCase):
    """No .exe (--onefile) __file__ fica numa pasta temporária apagada ao fechar o app: o CSV
    não pode morar lá."""

    def test_no_exe_vai_para_a_pasta_de_configuracao(self):
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(janela, "pasta_configuracao", return_value=Path("C:/AppData/AlertaFuturos")):
            self.assertEqual(janela._pasta_logs(), Path("C:/AppData/AlertaFuturos") / "logs")

    def test_no_codigo_fonte_fica_ao_lado_do_script(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(janela._pasta_logs(), Path(janela.__file__).with_name("logs"))


class TestExecutarMotor(unittest.TestCase):
    def test_falha_vira_mensagem_para_a_janela(self):
        class Motor:
            async def executar(self):
                raise RuntimeError("falha simulada")
        erros = queue.Queue()
        with self.assertLogs("alerta.janela", level="ERROR"):
            executar_motor(Motor(), erros)
        self.assertIn("interrompido", erros.get_nowait())

    def test_fim_normal_nao_gera_mensagem(self):
        class Motor:
            async def executar(self):
                return None
        erros = queue.Queue()
        executar_motor(Motor(), erros)
        self.assertTrue(erros.empty())


def _tem_tela() -> bool:
    try:
        r = tk.Tk()
        r.destroy()
        return True
    except tk.TclError:
        return False


@unittest.skipUnless(_tem_tela(), "sem tela para montar um tk.Tk() (no Linux, rode com xvfb-run)")
class TestJanelaReal(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.root.destroy)
        patch.object(self.root, "after", return_value="teste").start()
        patch.object(Aplicativo, "_configurar_bandeja").start()
        self.addCleanup(patch.stopall)
        self.app = Aplicativo(self.root, Path(self.tmp.name) / "config.json")
        self.app.popups = MagicMock()
        self.root.update_idletasks()

    def sessao(self, conectado=False, vivo=True, reconexoes=0):
        m = MagicMock()
        m.conectado.is_set.return_value = conectado
        m.reconexoes = reconexoes
        self.app.monitor = m
        self.app.thread_motor = MagicMock()
        self.app.thread_motor.is_alive.return_value = vivo
        self.app.sessao_ativa = True
        self.app.inicio_sessao = time.monotonic()
        self.app._estilizar_botoes(rodando=True)
        return m

    def test_comeca_explicando_o_que_fazer(self):
        self.assertIn("Pronto", self.app.rotulo_status.cget("text"))
        self.assertIn("Iniciar", self.app.rotulo_orientacao.cget("text"))

    def test_conectando_anima_a_barra_e_reduzir_movimento_para(self):
        self.sessao(conectado=False)
        self.app._processar()
        self.assertEqual(self.app.barra_espera.modo, "animando")
        self.app.reduzir_movimento.set(True)
        self.app._atualizar_barra()
        self.assertEqual(self.app.barra_espera.modo, "parado")
        self.assertIn("Conectando", self.app.rotulo_status.cget("text"))  # o texto continua dizendo

    def test_conectado_mostra_tempo_ate_o_fechamento(self):
        self.sessao(conectado=True)
        self.app._processar()
        self.assertEqual(self.app.barra_espera.modo, "progresso")
        self.assertIn("ativo", self.app.rotulo_status.cget("text"))
        self.assertIn("Próxima avaliação às", self.app.rotulo_proxima.cget("text"))

    def test_sem_sinal_escrito_no_quadro_e_contadores(self):
        self.sessao(conectado=True)
        av = _avaliacao()
        av.sinal = None
        self.app.fila.put(av)
        self.app._processar()
        itens = self.app.painel._linhas["BTCUSDT"]
        self.assertEqual(self.app.painel.corpo.itemcget(itens["sinal"], "text"), "sem sinal")
        self.assertEqual((self.app.avaliacoes, self.app.sinais), (1, 0))
        self.app.popups.mostrar.assert_not_called()

    def test_sinal_mostra_popup_e_conta(self):
        self.sessao(conectado=True)
        self.app.fila.put(_avaliacao())
        self.app._processar()
        self.app.popups.mostrar.assert_called_once()
        self.assertEqual(self.app.sinais, 1)

    def test_depois_de_parar_nao_mostra_aviso_atrasado(self):
        self.sessao(conectado=True)
        self.app.parar()
        self.app.fila.put(_avaliacao())
        self.app._processar()
        self.app.popups.mostrar.assert_not_called()
        self.assertIn("parado", self.app.rotulo_status.cget("text"))

    def test_motor_que_morre_sozinho_libera_o_iniciar(self):
        self.sessao(conectado=True, vivo=False)
        self.app.erros_motor.put("O monitoramento foi interrompido por uma falha inesperada.")
        self.app._processar()
        self.assertIn("interrompido", self.app.rotulo_status.cget("text"))
        self.assertIn("interrompido", self.app.rotulo_erro.cget("text"))
        self.assertEqual(self.app.botao_iniciar.cget("state"), "normal")
        self.assertFalse(self.app.sessao_ativa)

    def test_iniciar_bloqueado_enquanto_sessao_anterior_termina(self):
        self.sessao(vivo=True)
        with patch("janela.Registro") as registro:
            self.app.iniciar()
        registro.assert_not_called()
        self.assertIn("Aguarde", self.app.rotulo_erro.cget("text"))

    def test_exemplo_usa_o_popup_real_sem_entrar_no_historico(self):
        self.app.registro = MagicMock()
        self.app.mostrar_exemplo()
        args, kwargs = self.app.popups.mostrar.call_args
        self.assertIn("SIMULAÇÃO", kwargs["titulo"])
        self.assertTrue(self.app.fila.empty())
        self.app.registro.gravar.assert_not_called()
        self.assertEqual((self.app.avaliacoes, self.app.sinais), (0, 0))

    def test_zoom_preserva_o_que_estava_na_tela(self):
        self.sessao(conectado=True)
        self.app.fila.put(_avaliacao())
        self.app._processar()
        self.app.entradas["rsi_acima"].config(state="normal")
        self.app.entradas["rsi_acima"].delete(0, "end")
        self.app.entradas["rsi_acima"].insert(0, "88")
        self.app._habilitar_campos(False)
        largura = self.app.conteudo.winfo_reqwidth()
        self.app.aplicar_zoom(1.5)
        self.root.update_idletasks()
        self.assertGreater(self.app.conteudo.winfo_reqwidth(), largura * 1.3)
        self.assertEqual(self.app.entradas["rsi_acima"].get(), "88")
        self.assertEqual(self.app.entradas["rsi_acima"].cget("state"), "disabled")  # sessão rodando
        self.assertEqual(self.app.botao_iniciar.cget("state"), "disabled")
        itens = self.app.painel._linhas["BTCUSDT"]
        self.assertIn("W", self.app.painel.corpo.itemcget(itens["sinal"], "text"))  # quadro redesenhado
        self.app.aplicar_zoom(1.0)
        self.root.update_idletasks()
        self.assertEqual(self.app.conteudo.winfo_reqwidth(), largura)

    def _versao_nova(self):
        import atualizacao
        return atualizacao.Publicada("2099.1.1.1", atualizacao.DOMINIO_PERMITIDO + "assets/AlertaFuturos.exe",
                                     "0" * 64, 100, "01/01/2099", "Tela cheia")

    def test_atualizacao_so_pergunta_com_a_janela_visivel(self):
        self.app.fila_atualizacao.put(("disponivel", self._versao_nova()))
        with patch("janela.messagebox.askyesno", return_value=False) as pergunta, \
             patch.object(self.app, "_janela_visivel", return_value=False):
            self.app._tratar_atualizacao()
        pergunta.assert_not_called()  # abriu minimizado: espera o cliente abrir a janela
        with patch("janela.messagebox.askyesno", return_value=False) as pergunta, \
             patch.object(self.app, "_janela_visivel", return_value=True):
            self.app._tratar_atualizacao()
            self.app._tratar_atualizacao()
        pergunta.assert_called_once()
        self.assertIsNotNone(self.app.link_atualizacao)  # "Não" deixa o aviso dourado no rodapé

    def test_falha_de_atualizacao_mantem_o_app_e_oferece_o_site(self):
        self.app.atualizacao = self._versao_nova()
        self.app.atualizacao_perguntada = True
        with patch("janela.atualizacao.baixar", side_effect=ValueError("SHA-256 diferente")):
            self.app.iniciar_atualizacao()
            for _ in range(50):
                if not self.app.fila_atualizacao.empty():
                    break
                time.sleep(0.02)
        with patch("janela.messagebox.askyesno", return_value=True) as pergunta, \
             patch("janela.webbrowser.open") as abrir:
            self.app._tratar_atualizacao()
        self.assertIn("SHA-256", pergunta.call_args[0][1])
        abrir.assert_called_once()
        self.assertFalse(self.app.atualizando)

    def test_como_usar_abre_uma_vez_so(self):
        self.app.mostrar_ajuda()
        primeira = self.app.janela_ajuda
        self.app.mostrar_ajuda()
        self.assertIs(self.app.janela_ajuda, primeira)
        primeira.destroy()


if __name__ == "__main__":
    unittest.main()
