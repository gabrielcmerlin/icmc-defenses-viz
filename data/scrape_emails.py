# Le o .mbox que o Takeout gerou e monta o eventos.csv
# (um evento por linha: defesas e qualificacoes da lista [grad-l] do ICMC)
#
# uso: python3 data/scrape_emails.py data/raw/grad-I.mbox

import csv
import email
import email.policy
import email.utils
import hashlib
import mailbox
import re
import sys
import unicodedata
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

# nome do programa -> como ele fica no csv (com a sigla no final)
PROGRAMAS = {
    "Ciências de Computação e Matemática Computacional": "Ciências de Computação e Matemática Computacional - PPG-CCMC",
    "Estatística": "Estatística - PIPGES",
    "Matemática": "Matemática - PPG-Mat",
    "Matemática, Estatística e Computação Aplicadas à Indústria": "Matemática, Estatística e Computação Aplicadas à Indústria - MECAI",
    "Matemática em Rede Nacional - PROFMAT": "Matemática em Rede Nacional - PROFMAT",
}

COLUNAS = ["id", "tipo", "nivel", "programa", "titulo", "aluno", "orientador", "data",
           "dia_semana", "hora", "local", "icmc", "remoto", "atualizado"]

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

# ex: "Defesa de Mestrado em Matemática"
CABECALHO = re.compile(r"(Defesa|Qualifica[cç][aã]o)\s+de\s+(Mestrado|Doutorado)\s+em\s+(.+)$", re.I)

# ex: "segunda-feira, 19 de outubro às 09 horas" / "15h30" / "09h45"
QUANDO = re.compile(r"(\d{1,2})\s+de\s+(\w+)(?:\s+de\s+(\d{4}))?"
                    r"(?:\s+às\s+(\d{1,2})(?:\s*h\s*(\d{2})?|:(\d{2})|\s+horas?)?)?", re.I)


class HtmlParaTexto(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pedacos = []

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "tr", "li"):
            self.pedacos.append("\n")

    def handle_data(self, data):
        self.pedacos.append(data)


def pegar_corpo(msg):
    parte = msg.get_body(preferencelist=("plain", "html"))
    if parte is None:
        return ""
    texto = parte.get_content()
    if parte.get_content_type() == "text/html":
        p = HtmlParaTexto()
        p.feed(texto)
        texto = "".join(p.pedacos)
    return texto


def tirar_citacoes(corpo):
    # os e-mails de resposta ("Re:", "Atualizado") repetem a agenda antiga embaixo,
    # entao corto tudo a partir do "Em ... escreveu:"
    m = re.search(r"^.*escreveu:\s*$", corpo, re.M)
    if m:
        corpo = corpo[:m.start()]
    # o mbox escreve ">From" quando a linha comeca com "From" (tinha um titulo assim)
    corpo = re.sub(r"^>(?=From )", "", corpo, flags=re.M)
    linhas = [l for l in corpo.splitlines() if not l.lstrip().startswith(">")]
    return "\n".join(linhas)


def ler_data_hora(texto, data_email):
    """Devolve (data 'AAAA-MM-DD', hora 'HH:MM'). O e-mail quase nunca tem o ano,
    entao uso o ano da data em que o e-mail foi enviado."""
    m = QUANDO.search(texto)
    if not m or m[2].lower() not in MESES:
        return None, None
    mes = MESES.index(m[2].lower()) + 1
    dia = int(m[1])
    ano = int(m[3]) if m[3] else data_email.year
    if not m[3]:
        # e-mail de dezembro falando de janeiro (ou o contrario) muda de ano
        if data_email.month >= 11 and mes <= 2:
            ano += 1
        elif data_email.month <= 2 and mes >= 11:
            ano -= 1
    try:
        data = date(ano, mes, dia).isoformat()
    except ValueError:
        return None, None
    hora = None
    if m[4]:
        minuto = int(m[5] or m[6] or 0)
        hora = f"{int(m[4]):02d}:{minuto:02d}"
    return data, hora


def ler_bloco(bloco, data_email):
    """Transforma o texto de uma banca num dicionario. Devolve None se nao for uma banca."""
    # tem e-mail com o titulo colado no "Aluno(a):", separo em linhas
    bloco = re.sub(r"(?<=\S)(?=(?:Aluno\(a\)|Orientador\(a\)|Quando|Onde):)", "\n", bloco)
    # alguns e-mails vem com negrito em texto puro: *Qualificação* de *Mestrado*
    linhas = [l.replace("*", "").strip() for l in bloco.splitlines()]
    linhas = [l for l in linhas if l]
    # tem e-mail com "Atenciosamente," solto no meio da agenda e outros com rodape colado no ultimo bloco:
    # so a assinatura/rodape sai, o resto do e-mail fica
    for k, l in enumerate(linhas):
        if re.match(r"^(Atenciosamente,?|_\s*_?|--|Mais informações|Agenda de defesas.*|Serviço de Pós-Graduação.*)$", l):
            linhas = linhas[:k]
            break

    i = next((i for i, l in enumerate(linhas) if CABECALHO.search(l)), None)
    if i is None:
        return None
    cab = CABECALHO.search(linhas[i])
    resto = linhas[i + 1:]
    programa = cab[3].strip()

    # o e-mail quebra linha grande no meio ("...Matemática" / "Computacional"),
    # entao completo o nome com a lista de programas
    for nome in PROGRAMAS:
        if nome.startswith(programa + " ") and resto:
            falta = nome[len(programa):].strip()
            if resto[0].startswith(falta):
                programa = nome
                resto[0] = resto[0][len(falta):].strip()
                break
    # as vezes a sigla cai na linha de baixo ("Computacional -" / "PPG-CCMC")
    if resto:
        m = re.match(r"^-?\s*(?:PIPGES|MECAI|PPG-\w+)\b\.?\s*", resto[0])
        if m:
            resto[0] = resto[0][m.end():]
            programa = re.sub(r"\s*-$", "", programa)
        if not resto[0]:
            resto.pop(0)

    # tudo antes do primeiro campo (Aluno, Orientador...) é o titulo.
    # linha que nao comeca com campo continua o campo anterior (nome ou local quebrado)
    campos = {}
    titulo = []
    ultimo = None
    for l in resto:
        m = re.match(r"^(Aluno\(a\)|Orientador\(a\)|Quando|Onde):\s*(.*)$", l)
        if m:
            ultimo = m[1]
            campos[ultimo] = m[2].strip()
        elif not campos:
            titulo.append(l)
        elif ultimo:
            campos[ultimo] += " " + l
    if titulo:
        titulo[0] = re.sub(r"^T[íi]tulo:\s*", "", titulo[0])
    if "Aluno(a)" not in campos or "Quando" not in campos:
        return None

    # em alguns e-mails o "Onde:" some ou vem errado ("O Onde:") e o local fica dentro do "Quando"
    m = re.search(r"\s+(?:O\s+)?(?:Onde:\s*)?((?:Exame|Banca)\s+remot.*)$", campos["Quando"], re.I)
    if m:
        campos["Quando"] = campos["Quando"][:m.start()]
        campos.setdefault("Onde", m[1])

    data, hora = ler_data_hora(campos["Quando"], data_email)
    onde = campos.get("Onde", "").lstrip(") ")  # tem um "Onde:) 3-002" com erro de digitacao
    remoto = bool(re.search(r"remot[ao]", onde, re.I))

    junta = lambda t: re.sub(r"\s+", " ", t).strip()  # alguns e-mails tem espaco duplo ("ICMC,  3-002")
    return {
        "tipo": "Defesa" if cab[1].lower().startswith("defesa") else "Qualificação",
        "nivel": cab[2].capitalize(),
        "programa": programa,
        "titulo": junta(" ".join(titulo)),
        "aluno": junta(campos["Aluno(a)"]),
        "orientador": junta(campos.get("Orientador(a)", "")),
        "data": data,
        "dia_semana": date.fromisoformat(data).weekday() if data else None,  # 0 = segunda
        "hora": hora,
        # se for remota o "local" é so a citacao da resolucao, entao deixo vazio
        "local": "" if remoto else junta(onde),
        "remoto": int(remoto),
    }


def ler_alteracoes(corpo):
    """Email sem bloco de agenda avisando em texto livre que um exame passou a ser virtual."""
    corpo = re.sub(r"\s+", " ", corpo)
    return [re.sub(r"\s+", " ", n).strip().lower()
            for n in re.findall(r"aluno\(a\): (.+?) foi alterado e ocorrer[áa] de forma virtual", corpo)]


def ler_email(msg):
    assunto = str(msg.get("Subject", "")).replace("\n", " ")
    if not re.search(r"Defesas?\s+e\s+Qualifica", assunto, re.I):
        return [], []
    data_email = email.utils.parsedate_to_datetime(msg["Date"])
    corpo = tirar_citacoes(pegar_corpo(msg))
    alteracoes = [(nome, data_email.timestamp()) for nome in ler_alteracoes(corpo)]

    eventos = []
    for bloco in re.split(r"^\s*-{5,}\s*$", corpo, flags=re.M):  # uma banca por bloco
        ev = ler_bloco(bloco, data_email)
        if ev:
            ev["atualizado"] = int(bool(re.search(r"atualiza|retifica", assunto, re.I)))  # Atualizado/Atualização/Retificação...
            ev["_enviado_em"] = data_email.timestamp()  # so pra saber qual e-mail é o mais novo
            # a mesma banca aparece em varios e-mails, entao o id é aluno + tipo + nivel
            # (o programa nao entra porque o nome as vezes vem diferente)
            chave = f"{ev['aluno'].lower()}|{ev['tipo']}|{ev['nivel']}"
            ev["id"] = hashlib.sha1(chave.encode()).hexdigest()[:16]
            eventos.append(ev)
    return eventos, alteracoes


def arrumar_programa(programa):
    programa = re.sub(r"[\s.\-–]+$", "", programa)                          # ponto ou "-" no final
    programa = re.sub(r"\s+-\s+(PIPGES|MECAI|PPG-?\w+)$", "", programa)    # sigla que ja veio no e-mail
    if programa not in PROGRAMAS:
        print("programa desconhecido:", programa, file=sys.stderr)
    return PROGRAMAS.get(programa, programa)


def sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def arrumar_orientadores(linhas):
    """Junta as grafias diferentes de um mesmo orientador (acento, maiuscula, ponto final, sobrenome a menos)."""
    for l in linhas:
        l["orientador"] = l["orientador"].rstrip(". ")  # tinha um "Gonçalves."
    nomes = Counter(l["orientador"] for l in linhas)
    chave = lambda n: sem_acento(n).casefold()

    # 1) mesmo nome mudando so acento/maiuscula ("Ednaldo José" x "Ednaldo Jose", "érica" x "Érica"):
    #    fica a grafia que comeca com maiuscula, com mais acentos e mais frequente
    por_chave = {}
    for n in nomes:
        por_chave.setdefault(chave(n), []).append(n)
    melhor = {}
    for variantes in por_chave.values():
        escolhida = max(variantes, key=lambda n: (n[0].isupper(), sum(not c.isascii() for c in n), nomes[n]))
        for n in variantes:
            melhor[n] = escolhida

    # 2) um nome que é o comeco de outro ("Cibele Maria Russo" -> "Cibele Maria Russo Novelli"),
    #    so se tiver 3+ palavras e um unico candidato maior
    finais = set(melhor.values())
    for n in finais:
        maiores = [m for m in finais if m != n and chave(m).startswith(chave(n) + " ")]
        if len(n.split()) >= 3 and len(maiores) == 1:
            for k, v in melhor.items():
                if v == n:
                    melhor[k] = maiores[0]
    for l in linhas:
        l["orientador"] = melhor[l["orientador"]]


def separar_icmc(linhas):
    """Coluna icmc: 1 = sala do ICMC (e o local fica so com o codigo da sala, ex.: 3-002),
    0 = outro lugar (o local fica como veio no e-mail), vazio = banca remota (nao tem local)."""
    for l in linhas:
        if not l["local"]:
            l["icmc"] = ""
            continue
        sala = re.search(r"\b(\d-\d{3}[A-Z]?)\b", l["local"])
        if sala and "UFSCar" not in l["local"]:
            l["icmc"] = 1
            l["local"] = sala.group(1)
        elif l["local"] == "Sala da Congregação":  # sala do ICMC que nao tem codigo numerico
            l["icmc"] = 1
        else:
            l["icmc"] = 0


def main():
    if len(sys.argv) < 2:
        sys.exit("uso: python3 data/scrape_emails.py data/raw/grad-I.mbox [saida.csv]")
    caminho_mbox = sys.argv[1]
    saida = sys.argv[2] if len(sys.argv) > 2 else Path(__file__).parent / "eventos.csv"

    todos = []
    alteracoes = []
    for m in mailbox.mbox(caminho_mbox):
        msg = email.message_from_bytes(m.as_bytes(), policy=email.policy.default)
        evs, alts = ler_email(msg)
        todos += evs
        alteracoes += alts

    # se a banca aparece em mais de um e-mail (semanal, "Atualizado"...) fica o mais recente
    por_id = {}
    for ev in sorted(todos, key=lambda e: e["_enviado_em"]):
        por_id[ev["id"]] = ev

    # as vezes o e-mail "Atualizado" troca o nivel (Doutorado -> Mestrado) e o id muda:
    # mesmo aluno + tipo com datas proximas é a mesma banca, vale a versao mais nova
    grupos = {}
    for ev in por_id.values():
        grupos.setdefault((ev["aluno"].lower(), ev["tipo"]), []).append(ev)
    for evs in grupos.values():
        evs.sort(key=lambda e: e["_enviado_em"])
        for velho in evs[:-1]:
            novo = evs[-1]
            if velho["nivel"] != novo["nivel"] and abs(date.fromisoformat(velho["data"]) - date.fromisoformat(novo["data"])).days <= 90:
                por_id.pop(velho["id"], None)

    # aviso em texto livre de que o exame passou a ser virtual (so tem 1 assim)
    for nome, quando in alteracoes:
        for ev in por_id.values():
            if ev["aluno"].lower() == nome and ev["_enviado_em"] < quando:
                ev["remoto"] = 1
                ev["local"] = ""

    linhas = []
    for ev in por_id.values():
        linha = {c: ev.get(c, "") for c in COLUNAS}
        linha["programa"] = arrumar_programa(linha["programa"])
        linhas.append(linha)
    arrumar_orientadores(linhas)
    separar_icmc(linhas)
    linhas.sort(key=lambda l: (l["data"] or "", l["hora"] or ""))

    with open(saida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        w.writerows(linhas)
    print(f"{len(todos)} ocorrências lidas, {len(linhas)} eventos no CSV")


if __name__ == "__main__":
    main()
