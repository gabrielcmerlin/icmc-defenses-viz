# Trabalho 2 - Visualização Computacional

Dados: agenda semanal de defesas e qualificações do ICMC, que chega por e-mail na lista `[grad-l]`.
Aqui está o passo a passo de como eu peguei esses e-mails e transformei num CSV.

## 1. Baixar os e-mails do Gmail

1. No Gmail da USP, pesquisei `subject:"[grad-l]" "Qualificações"`.
2. Marquei todos os resultados.
3. Criei um rótulo novo chamado `grad-I` e apliquei nesses e-mails.
4. Entrei em https://takeout.google.com e cliquei em "Desmarcar tudo".
5. Marquei só "E-mail" e, em "Todos os dados do E-mail incluídos", deixei só o rótulo `grad-I`.
6. "Próxima etapa" -> deixei as opções padrão (link por e-mail, exportar uma vez, .zip, 2 GB) -> "Criar exportação".
7. Esperei o e-mail do Google avisando que ficou pronto e baixei o `.zip`.

## 2. Gerar o CSV

Tudo rodando de dentro da pasta do trabalho, com o ambiente conda:

```bash
conda activate viscomp
cd /Users/gabrielcmerlin/codes/viscomp/trab2
```

Coloquei o zip em `data/raw/`:

```bash
mkdir -p data/raw
mv ~/Downloads/takeout-*.zip data/raw/
```

Extraí o `.mbox` que está dentro do zip e renomeei para `grad-I.mbox`
(dentro do zip ele aparece como `Takeout/E-mail/grad-I.mbox`, com "I" maiúsculo):

```bash
unzip -q -o data/raw/takeout-*.zip -d data/raw/takeout
mv data/raw/takeout/Takeout/E-mail/*.mbox data/raw/grad-I.mbox
rm -r data/raw/takeout
```

Rodei o script que lê o `.mbox` e monta o CSV:

```bash
python3 data/scrape_emails.py data/raw/grad-I.mbox
```

No terminal aparece:

```
647 ocorrências lidas, 523 eventos no CSV
```

O resultado fica em `data/eventos.csv`, com uma linha por defesa/qualificação.

## O que o script faz

- Lê as 120 mensagens do `.mbox` e pega só as que têm "Defesas e Qualificações" no assunto.
- Separa cada e-mail em blocos (um por banca, divididos pelas linhas `-----`) e tira de cada um
  tipo, nível, programa, título, aluno, orientador, data, hora e local.
- A mesma banca aparece em vários e-mails (semanal, "Atualizado", "Retificada"...), então
  juntei pelo aluno + tipo + nível e deixei sempre a versão do e-mail mais recente.
  Por isso 647 ocorrências viram 523 eventos.
- O CSV é reescrito inteiro a cada execução (não junta com o que já existia). Para atualizar
  com e-mails novos, é só fazer um novo export e rodar o script de novo.
- O nome do programa sai sempre com a sigla no fim (ex.: `... - PPG-CCMC`). As siglas
  (PPG-CCMC, PIPGES, PPG-Mat, MECAI, PROFMAT) são as que aparecem nos próprios e-mails.

### Problemas de parsing que apareceram (e como resolvi)

Os dois e-mails de exemplo que eu usei no começo eram "bonitinhos". Nos e-mails de verdade
apareceu bastante coisa diferente. Conferi o resultado contando os `Aluno(a):` de cada e-mail
contra os eventos que o script extraiu, e fui corrigindo até bater:

- **Negrito em texto puro:** alguns e-mails vêm como `*Qualificação* de *Mestrado*`. O script
  não reconhecia o cabeçalho e jogava o e-mail inteiro fora (inclusive o de 19 a 23/10).
  Agora os `*` são removidos.
- **Linhas quebradas:** o e-mail quebra linhas longas no meio. Isso quebrava o nome do programa
  (`...Matemática` / `Computacional`) e a palavra "Computacional" ia parar no começo do título.
  Agora o script completa o nome do programa usando a lista dos programas que aparecem
  nos e-mails. Nomes de alunos e locais quebrados em duas linhas também são juntados.
- **Respostas e e-mails citados:** os e-mails "Re:" e "Atualizado" repetem a agenda antiga
  embaixo, depois de "Em ... escreveu:". O script corta tudo a partir dessa linha (e ignora
  linhas começando com `>`). Antes, um desses e-mails fez o campo `local` de um evento
  ficar com mais de 5 mil caracteres.
- **Título colado no `Aluno(a):`** (sem quebra de linha), **lixo antes do cabeçalho** na mesma linha
  e **"Onde:" faltando ou digitado errado** em alguns e-mails: tratados caso a caso.
- **"Atenciosamente," solto no meio da agenda:** um e-mail (06 a 10/10/2025) tem essa linha no meio
  e eu estava cortando o e-mail ali, perdendo as bancas seguintes (e deixando uma data
  desatualizada de uma remarcação). Achei porque conferi todos os nomes de `Aluno(a):` do texto cru
  contra o CSV. Agora só a assinatura é cortada, dentro do bloco.
- **Rodapé colado no `local`:** em alguns e-mails o último bloco vem seguido de `--` /
  `Serviço de Pós-Graduação...` ou de `Mais informações...`, e isso entrava no campo `local`
  (ex.: `3-004B -- Serviço de Pós-Graduação ICMC - USP +55-16-...`). Agora o bloco é cortado
  nesses marcadores. Também tirei um `)` que sobrava em `Onde:) 3-002`.
- **Nível corrigido num e-mail "Atualizado":** a qualificação de Vinicius Morgado Rosa Vianna saiu
  como Doutorado e depois como Mestrado. Como o `id` usa o nível, ficavam dois eventos. Agora, se o
  mesmo aluno tem o mesmo tipo com níveis diferentes em até 90 dias, vale o e-mail mais novo.
- **Aviso em texto livre:** o e-mail `[ALTERAÇÃO]` de 17/09/2024 não tem bloco de agenda, só diz
  que a qualificação de Bruno Ely Reis Garcia passou a ser virtual. O script procura essa frase e
  marca o evento como remoto.
- **Orientador escrito de jeitos diferentes:** `Ednaldo José`/`Ednaldo Jose`, `Érica`/`érica`,
  `Gonçalves.` com ponto final, e `Cibele Maria Russo` x `Cibele Maria Russo Novelli`. O script
  junta essas grafias (fica a que começa com maiúscula, com acento e mais frequente).
- **Local em vários formatos:** a mesma sala aparecia como `3-002`, `ICMC, 3-002`, `Sala 3-002`...
  Se o texto tem um código de sala (`d-ddd`, ex.: `3-002`, `3-004B`) e não é da UFSCar, conta como
  ICMC (`icmc` = 1) e o `local` vira só o código. A `Sala da Congregação` também é do ICMC
  (`icmc` = 1), mas não tem código e o `local` fica com esse nome. O resto (`icmc` = 0) fica como veio.
- **`>From` do mbox:** o formato mbox escreve `>From` quando uma linha começa com "From".
  Um título começando com "From reviews to features..." estava sendo confundido com citação.
- **Nome do programa com sufixo:** alguns e-mails trazem ` - PIPGES` ou ` - PPG-Mat` no final,
  ou um ponto no fim. Tirei isso, e no final ficam 5 programas.
- Para ter certeza, li os 120 e-mails inteiros à mão (sem usar o script), montei minha própria
  lista de eventos e comparei campo a campo com o CSV. Foi assim que apareceram os três
  problemas acima (rodapé, nível e aviso em texto livre). Depois das correções, os 523 eventos
  batem em tipo, nível, programa, aluno, orientador, data, hora, local e remoto.
- Depois conferi 55 eventos sorteados, lado a lado com o texto original do e-mail, e todos bateram.
- Conferi também que o dia da semana escrito no e-mail bate com a data calculada
  (todos batem) e que não sobrou asterisco nem campo vazado em nenhuma coluna.

## Sobre a contagem de e-mails

O Gmail mostra 110 conversas e o `.mbox` tem 120 mensagens. É porque o Gmail agrupa
e-mails da mesma conversa (os "Atualizado", "Retificada" e as respostas "Re:") numa coisa só,
e o Takeout exporta cada mensagem separada.

## Estrutura

```
trab2/
├── README.md
└── data/
    ├── scrape_emails.py   # lê o mbox e gera o CSV
    ├── eventos.csv        # dataset final (gerado)
    └── raw/
        ├── takeout-...zip # export do Gmail
        └── grad-I.mbox    # extraído do zip (gerado)
```

## Colunas do `eventos.csv`

| Coluna | O que é |
|---|---|
| `id` | identificador do evento (hash de aluno + tipo + nível) |
| `tipo` | Defesa ou Qualificação |
| `nivel` | Mestrado ou Doutorado |
| `programa` | programa de pós-graduação, com a sigla no fim |
| `titulo`, `aluno` | dados da banca |
| `orientador` | orientador, com a grafia padronizada (ver abaixo) |
| `data` | AAAA-MM-DD |
| `dia_semana` | 0 = segunda, 1 = terça, ..., 4 = sexta |
| `hora` | HH:MM (vazio se o e-mail não informou) |
| `local` | se `icmc` = 1, só o código da sala (ex.: `3-002`); se `icmc` = 0, o texto do e-mail como veio; vazio se a banca é remota |
| `icmc` | 1 = sala do ICMC (inclui a Sala da Congregação), 0 = outro lugar (UFSCar, FFCLRP, sessão fechada), vazio = banca remota |
| `remoto` | 1 se a banca é remota, 0 se presencial |
| `atualizado` | 1 se a versão final do evento veio de um e-mail de correção (assunto com "Atualizado", "Atualização" ou "Retificação") |

## Problemas que ficaram nos dados

Nenhum é erro do script: vêm dos próprios e-mails.

- Não aparecem eventos de mar-abr/2025 (conferi no Gmail: a lista não mandou e-mails nesse período).
- O export vai até o começo de out/2026 (foi quando pedi), mas já inclui a semana de 19 a 23/10.
- Uma linha (Bruno Estanislau Holtz, 13/08/2026) está sem hora, porque o e-mail não informou.
- Um evento (Ricardo Tetti Camacho, 03/09/2024) ficou de fora: nos dois e-mails em que ele
  aparece falta a linha "Defesa/Qualificação de ...", então não dá para saber o tipo.
- Alguns títulos vêm cortados no próprio e-mail (8 casos) e há erros de digitação neles
  (ex.: `Abaout a theorem by Nomizu`, `ambien t`). Deixei como estão.
- Uma defesa (Maria Lydia Fioravanti, 29/05/2026) é "sessão fechada": não é remota nem tem sala
  (`remoto` = 0, `icmc` = 0, e o `local` guarda o texto do e-mail).
- O script não sabe de bancas canceladas sem aviso por e-mail.
