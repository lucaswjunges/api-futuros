"""Atualização automática (atualizacao.py): comparação de versões, validação do versao.json,
download conferido e a troca do .exe com a versão antiga guardada em "Versões anteriores"."""

import hashlib
import io
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import atualizacao
from atualizacao import Publicada, baixar, eh_mais_nova, ler_publicada, trocar_executavel, verificar
from publicar_versao import gerar

EXE = b"MZ" + b"\x90" * 5000


def _pub(conteudo=EXE, **mudar):
    dados = dict(versao="2099.1.1.1", url=atualizacao.DOMINIO_PERMITIDO + "assets/AlertaFuturos.exe",
                 sha256=hashlib.sha256(conteudo).hexdigest(), tamanho=len(conteudo), data="01/01/2099")
    dados.update(mudar)
    return dados


def _abridor(respostas):
    def abrir(url, timeout):
        for prefixo, corpo in respostas.items():
            if url.startswith(prefixo):
                if isinstance(corpo, Exception):
                    raise corpo
                return io.BytesIO(corpo)
        raise OSError("url inesperada " + url)
    return abrir


class TestVersoes(unittest.TestCase):
    def test_compara_numericamente(self):
        self.assertTrue(eh_mais_nova("2026.09.24.2", "2026.09.24.1"))
        self.assertTrue(eh_mais_nova("2026.10.1.1", "2026.9.30.9"))
        self.assertFalse(eh_mais_nova("2026.09.24.1", "2026.09.24.1"))
        self.assertFalse(eh_mais_nova("2026.09.23.9", "2026.09.24.1"))
        self.assertFalse(eh_mais_nova("lixo", "2026.09.24.1"))


class TestVersaoJson(unittest.TestCase):
    def test_valido(self):
        self.assertEqual(ler_publicada(_pub()).versao, "2099.1.1.1")

    def test_recusa_url_de_outro_site(self):
        with self.assertRaises(ValueError):
            ler_publicada(_pub(url="https://exemplo.com/virus.exe"))

    def test_recusa_campos_faltando_ou_invalidos(self):
        for ruim in ({"versao": "1"}, _pub(sha256="abc"), _pub(tamanho=0), _pub(versao="x.y")):
            with self.subTest(ruim=ruim), self.assertRaises(ValueError):
                ler_publicada(ruim)

    def test_verificar_sem_internet_nao_quebra(self):
        self.assertIsNone(verificar(abrir=_abridor({atualizacao.URL_VERSAO: OSError("offline")})))

    def test_verificar_json_quebrado_nao_quebra(self):
        self.assertIsNone(verificar(abrir=_abridor({atualizacao.URL_VERSAO: b"<html>"})))

    def test_verificar_so_devolve_se_for_mais_nova(self):
        nova = json.dumps(_pub()).encode()
        velha = json.dumps(_pub(versao="2000.1.1.1")).encode()
        self.assertEqual(verificar(abrir=_abridor({atualizacao.URL_VERSAO: nova})).versao, "2099.1.1.1")
        self.assertIsNone(verificar(abrir=_abridor({atualizacao.URL_VERSAO: velha})))


class TestDownload(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.destino = self.tmp / "baixado" / "AlertaFuturos-nova.exe"

    def test_baixa_confere_e_informa_progresso(self):
        p = ler_publicada(_pub())
        passos = []
        caminho = baixar(p, self.destino, progresso=lambda f, t: passos.append((f, t)),
                         abrir=_abridor({p.url: EXE}))
        self.assertEqual(caminho.read_bytes(), EXE)
        self.assertEqual(passos[-1], (len(EXE), len(EXE)))

    def test_hash_diferente_e_recusado_e_nao_sobra_arquivo(self):
        p = ler_publicada(_pub())
        adulterado = b"MZ" + b"\x00" * (len(EXE) - 2)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            baixar(p, self.destino, abrir=_abridor({p.url: adulterado}))
        self.assertEqual(list(self.destino.parent.iterdir()), [])

    def test_incompleto_e_recusado(self):
        p = ler_publicada(_pub())
        with self.assertRaisesRegex(ValueError, "incompleto"):
            baixar(p, self.destino, abrir=_abridor({p.url: EXE[:100]}))

    def test_nao_executavel_e_recusado(self):
        html = b"<html>" + b" " * 100
        p = ler_publicada(_pub(conteudo=html))
        with self.assertRaisesRegex(ValueError, "executável"):
            baixar(p, self.destino, abrir=_abridor({p.url: html}))


class TestTroca(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        self.atual = self.pasta / "AlertaFuturos.exe"
        self.atual.write_bytes(b"MZ velho")
        self.novo = self.pasta / "baixado.exe"
        self.novo.write_bytes(b"MZ novo")

    def test_novo_no_lugar_e_antigo_guardado(self):
        guardada = trocar_executavel(self.atual, self.novo, "2026.09.24.1")
        self.assertEqual(self.atual.read_bytes(), b"MZ novo")
        self.assertEqual(guardada.read_bytes(), b"MZ velho")
        self.assertEqual(guardada.parent.name, atualizacao.PASTA_ANTERIORES)
        self.assertEqual(guardada.name, "AlertaFuturos-2026.09.24.1.exe")

    def test_nao_sobrescreve_versao_antiga_ja_guardada(self):
        (self.pasta / atualizacao.PASTA_ANTERIORES).mkdir()
        (self.pasta / atualizacao.PASTA_ANTERIORES / "AlertaFuturos-2026.09.24.1.exe").write_bytes(b"x")
        guardada = trocar_executavel(self.atual, self.novo, "2026.09.24.1")
        self.assertEqual(guardada.name, "AlertaFuturos-2026.09.24.1 (2).exe")

    def test_falha_no_meio_desfaz(self):
        original = os.replace
        chamadas = []

        def replace(a, b):
            chamadas.append((a, b))
            if len(chamadas) == 2:
                raise PermissionError("bloqueado")
            return original(a, b)

        with patch("atualizacao.os.replace", side_effect=replace):
            with self.assertRaises(PermissionError):
                trocar_executavel(self.atual, self.novo, "1")
        self.assertEqual(self.atual.read_bytes(), b"MZ velho")  # o cliente nunca fica sem o programa


class TestPublicarVersao(unittest.TestCase):
    def test_gera_json_que_o_app_aceita(self):
        exe = Path(tempfile.mkdtemp()) / "AlertaFuturos.exe"
        exe.write_bytes(EXE)
        info = gerar(exe, "Tela cheia", hoje=date(2026, 9, 24))
        p = ler_publicada(info)
        self.assertEqual(p.sha256, hashlib.sha256(EXE).hexdigest())
        self.assertEqual(p.tamanho, len(EXE))
        self.assertEqual(p.data, "24/09/2026")


if __name__ == "__main__":
    unittest.main()
