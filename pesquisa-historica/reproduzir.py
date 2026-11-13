"""Restaura o snapshot original conferindo os hashes, sem rede nem sobrescrita divergente."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent
def restore():
    manifest = json.loads((ROOT/'fontes/snapshot-original.json').read_text())
    archive = ROOT/'fontes/candles-original.zip'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('SHA-256 do snapshot divergente')
    with zipfile.ZipFile(archive) as z:
        for name, digest in manifest['files'].items():
            if Path(name).name != name: raise ValueError('Nome invalido no snapshot')
            data = z.read(name)
            if hashlib.sha256(data).hexdigest() != digest: raise ValueError(name)
            target = ROOT/'cache'/name
            if target.exists() and target.read_bytes() != data:
                raise ValueError(f'{target} difere do original; preserve-o e use clone limpo')
        (ROOT/'cache').mkdir(exist_ok=True)
        for name in manifest['files']:
            (ROOT/'cache'/name).write_bytes(z.read(name))
    print('Snapshot conferido:', len(manifest['files']), 'ativos; corte', manifest['cutoff_ms'])
if __name__ == '__main__': restore()
