# Visualização das bancas de defesa e qualificação do ICMC-USP

## Descrição

As bancas de qualificação e de defesa do ICMC-USP são divulgadas por e-mail, em avisos semanais de texto livre que informam aluno, orientador, título, data e local. Cada aviso mostra o que acontece naquela semana, mas ninguém enxerga o conjunto. Este projeto transforma esses avisos em um conjunto de dados estruturado com 1150 bancas de cinco programas de pós-graduação (PPG-CCMC, PIPGES, PPG-Mat, MECAI e PROFMAT), realizadas entre março de 2022 e outubro de 2026, e o explora com visualizações interativas em torno de três questões: quando as bancas acontecem (gráfico sazonal de linhas), que perfis de banca existem e quais são raros (treemap hierárquico) e se os orientadores são especialistas ou generalistas (gráfico de dispersão e mapa de calor). O tema de cada banca não existe nos e-mails e foi derivado do título por um modelo de linguagem executado localmente, a partir das árvores de temas oficiais dos programas.

Trabalho da disciplina SCC0252 – Visualização Computacional (2026/2), ICMC-USP, Prof. Jean R. Ponciano.

## Integrantes

- Gabriel da Costa Merlin
- Guilherme Antonio Costa Bandeira
- João Pedro Mori Machado

## Estrutura

```bash
icmc-defenses-viz/
├── data/
│   ├── raw/
│   │   └── defesas.mbox              # E-mails da lista [grad-l] exportados pelo Google Takeout
│   ├── scrape_emails.py              # Lê o .mbox e gera o eventos.csv
│   └── eventos.csv                   # Dataset final, uma banca por linha
├── viz/
│   ├── trab_parte1.ipynb             # Notebook da entrega (visualizações interativas)
│   ├── question1/                    # Notebook de desenvolvimento da Questão 1
│   ├── question2/                    # Notebook de desenvolvimento da Questão 2
│   └── question3/
│       ├── classificar_temas.py      # Classifica o título de cada banca em um tema (opcional)
│       ├── temas_existentes.json     # Árvores de temas oficiais dos programas
│       ├── temas_llm_novo.csv        # Tema e macro-tema de cada banca
│       └── plot.ipynb                # Notebook de desenvolvimento da Questão 3
├── .gitignore
├── README.md                         # Documentação do projeto (este arquivo)
└── env.yaml                          # Definição do ambiente conda para reprodutibilidade
```

## Como começar

### Instalando o Miniconda

Se você já tem o conda instalado, pule esta etapa. Os comandos abaixo valem para Linux; para macOS e Windows, siga as instruções em [docs.anaconda.com/miniconda](https://docs.anaconda.com/miniconda/).

```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
rm Miniconda3-latest-Linux-x86_64.sh
echo 'export PATH="$HOME/miniconda3/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Baixando o código

```bash
git clone https://github.com/gabrielcmerlin/icmc-defenses-viz.git
cd icmc-defenses-viz
```

### Instalando as dependências

```bash
conda env create -f env.yaml
conda activate viscomp
```

### Dados

Não há nada para baixar. O dataset (`data/eventos.csv`) e os temas das bancas (`viz/question3/temas_llm_novo.csv`) já estão no repositório, então não é preciso gerar nem classificar nada para rodar o notebook. Caso queira refazer alguma dessas etapas, veja [Gerando o dataset do zero](#gerando-o-dataset-do-zero) e [Reclassificando os temas](#reclassificando-os-temas-opcional).



### Notas importantes

**Nota 1**: o notebook é entregue **sem as figuras salvas**. As visualizações aparecem quando você o executa por inteiro (*Run All*), e os painéis interativos (filtros, seletores e campos de busca) só funcionam com um kernel ativo, no VS Code ou no JupyterLab. O visualizador de notebooks do GitHub mostra o código, mas não as figuras nem os painéis.

**Nota 2**: o arquivo `data/raw/defesas.mbox` é a exportação bruta dos e-mails da lista `[grad-l]`, e está no repositório para que o `eventos.csv` possa ser reproduzido. As bancas são divulgadas pelo próprio ICMC para a comunidade, e os dados extraídos são os mesmos que aparecem nos avisos.

**Nota 3**: o dataset é gerado por um script sobre e-mails de texto livre, e não representa com 100% de fidelidade o conteúdo dos e-mails. As particularidades conhecidas são:
* 2022 (a partir de março) e 2026 (até outubro) são anos incompletos.
* O PPG-Mat, o MECAI e o PROFMAT não têm nenhuma qualificação no conjunto, porque elas não são divulgadas na lista desses programas. O MECAI e o PROFMAT só têm bancas de mestrado.
* Bancas canceladas sem aviso por e-mail não são detectadas.
* Alguns títulos aparecem cortados ou com erros de digitação nos próprios e-mails, e foram mantidos como vieram. Uma banca está sem horário, porque o e-mail não informou.
* O tema de cada banca é uma aproximação, atribuída por um modelo de linguagem a partir do título. Só o PPG-CCMC, o PPG-Mat e o PIPGES foram classificados.

## Como executar

### Abrindo o notebook

O notebook usa caminhos relativos à pasta `viz/`, então abra-o a partir da própria pasta.

* **VS Code:** abra `viz/trab_parte1.ipynb`, selecione o kernel `viscomp` e execute todas as células.
* **JupyterLab:**
```bash
jupyter lab viz/trab_parte1.ipynb
```

### Gerando o dataset do zero

Esta etapa é opcional e **sobrescreve** o `data/raw/defesas.mbox` e o `data/eventos.csv` atuais. Para reproduzi-la é preciso estar inscrito na lista `[grad-l]`.

**1. Baixando os e-mails do Gmail**

1. No Gmail da USP, pesquise `subject:"[grad-l]" "Qualificações"`.
2. Marque todos os resultados.
3. Crie um rótulo novo e aplique-o a esses e-mails. O nome é livre; o arquivo `.mbox` exportado leva o nome do rótulo.
4. Entre em [takeout.google.com](https://takeout.google.com) e clique em "Desmarcar tudo".
5. Marque só "E-mail" e, em "Todos os dados do E-mail incluídos", deixe só o rótulo criado.
6. Clique em "Próxima etapa", mantenha as opções padrão (link por e-mail, exportar uma vez, `.zip`, 2 GB) e clique em "Criar exportação".
7. Espere o e-mail do Google avisando que ficou pronto e baixe o `.zip`.

**2. Gerando o CSV**

```bash
mkdir -p data/raw
mv ~/Downloads/takeout-*.zip data/raw/
unzip -q -o data/raw/takeout-*.zip -d data/raw/takeout
mv data/raw/takeout/Takeout/E-mail/*.mbox data/raw/defesas.mbox
rm -r data/raw/takeout
python3 data/scrape_emails.py data/raw/defesas.mbox
```

O script aceita um segundo argumento opcional com o caminho do CSV de saída. Com os e-mails até 23/10/2026, o terminal mostra:

```
1398 ocorrências lidas, 1150 eventos no CSV
```

O script:
* lê só os e-mails cujo assunto contém "Defesas e Qualificações" e descarta os trechos citados de respostas anteriores;
* separa cada e-mail em blocos, um por banca, e extrai tipo, nível, programa, título, aluno, orientador, data, hora e local com expressões regulares;
* junta a mesma banca que aparece em vários e-mails (agenda semanal, "Atualizado", "Retificação") pelo aluno, tipo e nível, e mantém a versão do e-mail mais recente;
* padroniza os nomes dos programas e as grafias dos orientadores;
* deriva `dia_semana`, `remoto`, `icmc` e `atualizado`.

O CSV é reescrito por inteiro a cada execução. Para atualizar com e-mails novos, faça uma nova exportação e rode o script de novo.

### Reclassificando os temas (opcional)

Esta etapa só é necessária se você quiser classificar os temas de novo. O resultado já vem pronto em `viz/question3/temas_llm_novo.csv`.

**1. Configurando o modelo**

1. Instale o [Ollama](https://ollama.com/).
2. Baixe o modelo usado na classificação:
```bash
ollama pull gemma4:12b
```
3. Deixe o servidor rodando em outro terminal:
```bash
ollama serve
```

**2. Rodando a classificação**

```bash
# Mostra o prompt de uma banca, sem chamar o modelo
python3 viz/question3/classificar_temas.py --dry-run

# Classifica as bancas que ainda não têm tema
python3 viz/question3/classificar_temas.py
```

O modelo recebe só o programa e o título de cada banca, nunca o orientador nem o aluno, e escolhe entre os temas do programa em `viz/question3/temas_existentes.json` ou "Outros". O resultado é gravado linha a linha em `viz/question3/temas_llm_novo.csv`, então rodar o script de novo continua de onde parou. Para refazer tudo, ou para trocar de modelo com `--modelo`, apague esse CSV antes.

## Colunas do `eventos.csv`

| Coluna | Descrição |
|---|---|
| `id` | Identificador da banca (hash de aluno + tipo + nível) |
| `tipo` | Defesa ou Qualificação |
| `nivel` | Mestrado ou Doutorado |
| `programa` | Programa de pós-graduação, com a sigla no final (cinco valores) |
| `titulo` | Título do trabalho (texto livre) |
| `aluno` | Nome do(a) aluno(a) |
| `orientador` | Nome do(a) orientador(a), com a grafia unificada |
| `data` | Data da banca (AAAA-MM-DD) |
| `dia_semana` | 0 = segunda-feira, ..., 4 = sexta-feira |
| `hora` | Horário da banca (HH:MM) |
| `local` | Código da sala (ex.: `3-002`) se `icmc` = 1, texto do e-mail se `icmc` = 0, vazio nas bancas remotas |
| `icmc` | 1 = sala do ICMC, 0 = outro lugar, vazio = sem local registrado |
| `remoto` | 1 = remota, 0 = presencial |
| `atualizado` | 1 se a versão final veio de um e-mail de correção (assunto com "Atualizado", "Atualização" ou "Retificação") |

## Fontes e créditos

* **Bancas:** avisos semanais da lista `[grad-l]`, enviados pelo Serviço de Pós-Graduação do ICMC-USP.
* **Árvores de temas:** páginas dos programas [PPG-CCMC](https://www.icmc.usp.br/pos-graduacao/ppgccmc), [PPG-Mat](https://www.icmc.usp.br/pos-graduacao/ppgmat) e [PIPGES](https://www.icmc.usp.br/pos-graduacao/pipges).
* **Paleta de cores:** Okabe, M.; Ito, K. (2008). *Color Universal Design (CUD): How to make figures and presentations that are friendly to colorblind people.*
* **Classificação de temas:** modelo Gemma, executado localmente com o [Ollama](https://ollama.com/).
