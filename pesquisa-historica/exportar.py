"""Um comando: gerar do JSON, escrever instrucao e validar cada linha exportada."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
node = os.environ.get('ARTIFACT_NODE', 'node')
subprocess.run([node, str(ROOT/'authoring/build.mjs'), *sys.argv[1:]], check=True)
subprocess.run([sys.executable, str(ROOT/'guia.py')], check=True)
subprocess.run([sys.executable, str(ROOT/'validar_exportacao.py')], check=True)
