"""Achado em 19/09/2026 (teste ao vivo do Hugo): a criação do pystray.Icon pode dar certo, mas o
.run() de verdade — que roda numa thread separada — pode falhar depois, sem levantar nada no
código que criou a bandeja. Sem tratar isso, janela.py fica "configurada" pra minimizar ao fechar
mesmo sem nenhum ícone real pra reabrir, trancando o usuário fora do app. Este teste cobre
exatamente esse caminho, sem precisar de um backend de bandeja de verdade (a própria criação do
pystray.Icon já funciona neste sandbox sem GTK; só o .run() que não)."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock

try:
    from bandeja import Bandeja, CAMINHO_ICONE_PADRAO, carregar_icone, icone_padrao
    _ERRO_IMPORT = None
except Exception as _e:  # pystray às vezes falha já no import (ex.: Linux sem GTK/appindicator
    # nem xorg configurados — foi o caso deste sandbox de nuvem). No Windows real (a plataforma
    # de destino) isso não acontece: pystray escolhe o backend win32 direto, sem tentar GTK.
    Bandeja = None
    _ERRO_IMPORT = _e


@unittest.skipUnless(Bandeja is not None, f"pystray não conseguiu escolher um backend neste ambiente: {_ERRO_IMPORT!r}")
class TestExecutarAvisaFalhaDoRun(unittest.TestCase):
    def test_avisa_o_app_quando_o_run_do_pystray_falha(self):
        root = MagicMock()
        app = MagicMock()
        bandeja = Bandeja(root, app)
        bandeja.icone.run = MagicMock(side_effect=RuntimeError("sem backend de bandeja"))

        bandeja._executar()

        root.after.assert_called_once_with(0, app._bandeja_falhou_em_tempo_de_execucao)

    def test_nao_avisa_quando_o_run_termina_sem_erro(self):
        # .run() só "termina sem erro" de verdade quando alguém chama .stop() (fluxo normal de
        # sair de vez) — nesse caso não é falha, então não deve disparar o fallback.
        root = MagicMock()
        app = MagicMock()
        bandeja = Bandeja(root, app)
        bandeja.icone.run = MagicMock(return_value=None)

        bandeja._executar()

        root.after.assert_not_called()

    def test_thread_viva_reflete_o_estado_real_da_thread(self):
        root = MagicMock()
        app = MagicMock()
        bandeja = Bandeja(root, app)

        self.assertFalse(bandeja.thread_viva())  # ainda não chamou iniciar()


@unittest.skipUnless(Bandeja is not None, f"pystray não conseguiu escolher um backend neste ambiente: {_ERRO_IMPORT!r}")
class TestCarregarIcone(unittest.TestCase):
    """Achado em 19/09/2026: a bandeja sempre funcionou, só que com o placeholder genérico (círculo
    escuro + linha verde), pequeno demais e sem cara de "Alerta Futuros" pra ser notado na área de
    ícones ocultos. Trocado pela logo oficial da Blumenau TI (assets/icone_bandeja.png)."""

    def test_arquivo_da_logo_oficial_existe_no_repo(self):
        self.assertTrue(
            CAMINHO_ICONE_PADRAO.exists(),
            f"{CAMINHO_ICONE_PADRAO} não existe — a logo da Blumenau TI não foi commitada?",
        )

    def test_carrega_a_logo_oficial_por_padrao(self):
        img = carregar_icone()
        self.assertEqual(img.mode, "RGBA")
        self.assertGreaterEqual(img.size, (64, 64))

    def test_cai_no_placeholder_se_o_arquivo_nao_existir(self):
        img = carregar_icone(Path("/caminho/que/nao/existe.png"))
        self.assertEqual(img.size, icone_padrao().size)


if __name__ == "__main__":
    unittest.main()
