import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import inicio_automatico as ia


class TestComandoDeInicializacao(unittest.TestCase):
    def test_coloca_o_caminho_entre_aspas(self):
        # o caminho de instalação pode ter espaços (Program Files, nome do usuário…)
        caminho = Path(r"C:\Program Files\Alerta Futuros\AlertaFuturos.exe")
        self.assertEqual(ia.comando_de_inicializacao(caminho), f'"{caminho}"')


@patch.object(ia, "_no_windows", return_value=False)
class TestForaDoWindows(unittest.TestCase):
    """Neste sandbox (Linux) e no Ubuntu do Hugo, sys.platform nunca é "win32":
    as funções não devem fingir sucesso, e esta_ativo() deve ser sempre False."""

    def test_definir_levanta_erro_fora_do_windows(self, _mock):
        with self.assertRaises(RuntimeError):
            ia.definir(True, Path("C:/qualquer/coisa.exe"))

    def test_esta_ativo_e_sempre_falso_fora_do_windows(self, _mock):
        self.assertFalse(ia.esta_ativo())


if __name__ == "__main__":
    unittest.main()
