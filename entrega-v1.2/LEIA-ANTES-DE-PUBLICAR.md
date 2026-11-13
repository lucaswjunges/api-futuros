# Entrega 1.2 aguardando liberacao

Não publicado nem enviado ao cliente. Publicar somente depois de confirmar
**aceite e recebimento do Pix de R$ 720,00**, CNPJ **53.700.754/0001-10**.
Prazo comercial: até dois dias úteis após o Pix. Não há confirmação nesta tarefa.

`preparar.py` prepara os pacotes a partir de um EXE explícito e da pesquisa validada:

```powershell
python pesquisa-historica/exportar.py
python entrega-v1.2/preparar.py --exe poc/dist/AlertaFuturos.exe
```

EXE, XLSX, ZIP e pastas de staging ficam locais e fora do Git. `manifesto-entrega.json`
registra seus tamanhos e hashes. Distribuir depois da liberação comercial por canal
privado; o EXE público deve ser incorporado ao site existente. Fontes, testes,
documentação e snapshot histórico de auditoria ficam versionados.

Antes da publicação:

1. Resolver a divergência de comportamento: o usuário forneceu a transcrição do
   WhatsApp de Roberto ao Business de sexta-feira, 06/11/2026, 06:53:
   “orçar uma Versão 1.2 do App, bloqueando a 'Vela de 15 Minutos' (deixando tudo
   só 5M) e bloqueando o 'Alerta de 10 Segundos', deixando o restante da mesma
   forma em que está”. O pacote atual muda padrões, mas permite reativar essas
   opções. Foi solicitada decisão explícita entre bloqueá-las e manter os novos
   padrões com opções selecionáveis, conforme o escopo técnico inicial. Até essa
   decisão, não considerar o pacote atual aprovado quanto a esse requisito.
2. Projeto Pages informado pelo usuário: `alerta-futuros-versoes`, conta Cloudflare
   do Lucas (mesma de `blumenauti.com.br`). Confirmar no painel/API autorizado que
   seu domínio personalizado é `futuros.blumenauti.com.br`, exportar o site completo
   atual e anotar deployment ID. A informação foi recebida, ainda não verificada
   diretamente. Não executar `wrangler pages deploy` antes da liberação comercial.
3. Guardar EXE/manifesto anteriores e backup das configurações do teste isolado.
4. Incorporar somente `assets/AlertaFuturos.exe` e `versao.json` ao site COMPLETO.
   Nunca fazer deploy da pasta parcial `publicar-apos-aceite` como site inteiro.
5. Publicar os dois juntos. Se sequencial, EXE primeiro e manifesto por último.
6. Baixar ambos da produção sem cache; comparar tamanho e SHA-256 ao manifesto local.
   Conferir página inicial, download e `/versoes` contra o backup.
7. Em conta/pasta isolada, abrir a 1.1 original, configurar pares/fator por par,
   início automático e preferências; registrar config antes. Aceitar atualização
   oferecida pela produção e conferir 1.2, padrões e configurações preservadas.
8. Após 60 segundos, conferir a 1.1 em `Versões anteriores`, seu hash e reabertura.
   Reverter arquivos/config do ambiente de teste e documentar recuperação. Se falhar,
   restaurar o deployment completo anterior e reconferir os downloads públicos.

Os testes automatizados de troca, rollback de falha e configuração não substituem
o teste real 1.1 → 1.2 contra produção. Esse teste depende da publicação autorizada.
Veja `RELATORIO.md` para evidências e pendências.
