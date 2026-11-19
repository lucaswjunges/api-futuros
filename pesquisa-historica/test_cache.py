import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import coletar

def candle(i):
    return [i*coletar.MS, '1', '2', '1', '1.5', '1', (i+1)*coletar.MS-1]

class Cache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'cache').mkdir()
        self.root_patch = patch.object(coletar, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.root_patch.stop)

    def write(self, rows):
        (self.root/'cache/X.json').write_text(json.dumps(rows))

    def test_novo_corte_atualiza_cauda(self):
        self.write([candle(0), candle(1)])
        with patch.object(coletar, 'request', return_value=[candle(2)]) as req:
            self.assertEqual(coletar.load_candles('X', 3*coletar.MS)[-1], candle(2))
            self.assertEqual(req.call_args.args[1]['startTime'], 2*coletar.MS)

    def test_novo_corte_sem_dados_falha(self):
        self.write([candle(0)])
        with patch.object(coletar, 'request', return_value=[]):
            with self.assertRaises(ValueError): coletar.load_candles('X', 3*coletar.MS)

    def test_replay_offline_limita_ao_corte(self):
        self.write([candle(0), candle(1), candle(2)])
        with patch.object(coletar, 'request', side_effect=AssertionError('Rede no replay')):
            self.assertEqual(coletar.load_candles('X', 2*coletar.MS, True), [candle(0), candle(1)])

    def test_replay_cache_antigo_falha(self):
        self.write([candle(0)])
        with self.assertRaises(ValueError): coletar.load_candles('X', 2*coletar.MS, True)

    def test_lacuna_falha(self):
        self.write([candle(0), candle(2)])
        with self.assertRaises(ValueError): coletar.load_candles('X', 3*coletar.MS, True)
