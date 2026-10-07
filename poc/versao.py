"""Versão deste build do Alerta Futuros.

Dois valores, de propósito:
  VERSAO       — número técnico, formato ano.mês.dia.sequência do dia. É por ele que os apps já
                 instalados sabem que existe atualização (ver atualizacao.py e publicar_versao.py):
                 AUMENTAR a cada .exe novo publicado no site. Precisa crescer sempre — trocar para
                 "1.0.0" quebraria a comparação com os apps que já estão em 2026.09.24.2.
  NOME_VERSAO  — o nome que o cliente vê ("Versão 1.0"). Muda só quando a entrega muda de
                 patamar (1.1, 2.0 com IA...), não a cada correção.
  PLANO        — plano comprado com este build. O versao.json pode dizer para quais planos uma
                 versão nova é inclusa ("planos"); fora deles o app não instala, só mostra que a
                 versão existe e leva à página de versões (ver atualizacao.incluida_no_plano).
"""

VERSAO = "2026.10.07.2"
NOME_VERSAO = "1.1"
PLANO = "completa"
