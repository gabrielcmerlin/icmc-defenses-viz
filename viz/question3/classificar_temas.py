# Classifica cada banca em um tema (nivel mais especifico de temas_existentes.json) usando um modelo local via Ollama e escreve temas_llm.csv
#
# - o modelo ve APENAS o titulo e o programa (nunca orientador nem aluno)
# - ele escolhe entre os temas do programa da banca, ou "Outros"
# - a resposta e forcada a seguir um JSON schema (campo `format` do Ollama), entao sempre cai na lista
# - cada resposta e gravada no proprio temas_llm.csv, linha a linha, entao
#   rodar de novo continua de onde parou. o csv nao guarda o modelo: para refazer tudo
#   (ou trocar de modelo) apague o csv antes
#
# uso:  python3 classificar_temas.py                        # roda o que falta com o modelo padrao
#       python3 classificar_temas.py --modelo qwen3.5:9b    # outro modelo (veja `ollama list`); apague o csv antes
#       python3 classificar_temas.py --dry-run              # mostra o prompt de uma banca, sem chamar o modelo

import argparse
import csv
import json
from pathlib import Path
import requests

AQUI = Path(__file__).parent
RAIZ = AQUI.parent.parent
EVENTOS = RAIZ / "data" / "eventos.csv"
TEMAS = AQUI / "temas_existentes.json"
SAIDA = AQUI / "temas_llm.csv"

OLLAMA = "http://localhost:11434"
MODELO_PADRAO = "gemma4:12b"
OUTROS = "Outros"

# programas classificados: a sigla no final do nome do programa e a chave em temas_existentes.json
# (os outros programas de eventos.csv, como MECAI e PROFMAT, ficam de fora de proposito)
SIGLAS = {"PPG-CCMC", "PPG-Mat", "PIPGES"}


def ler_temas():
    """Para cada programa: lista de (macro_tema, caminho_completo, tema), sem temas repetidos.
    Tema e o ultimo nivel de cada ramo da arvore; um macro_tema sem sub_temas e tema dele mesmo.
    So le "macro_temas"; as outras chaves do json (ex: "fonte") sao so documentacao."""
    arvore = json.load(open(TEMAS, encoding="utf-8"))
    por_programa = {}

    def percorre(nos, caminho, macro_tema, saida):
        for no in nos:
            c = caminho + [no["nome"]]
            if no.get("sub_temas"):
                percorre(no["sub_temas"], c, macro_tema, saida)
            else:
                saida.append((macro_tema, " > ".join(c), no["nome"]))

    for prog, v in arvore.items():
        todos = []
        for m in v["macro_temas"]:
            percorre([m], [], m["nome"], todos)
        vistos, unicas = set(), []
        for t in todos:                  # ex: "Fisica Matematica" aparece em 2 macro-temas do PPG-Mat: fica o primeiro
            if t[2] not in vistos:
                vistos.add(t[2])
                unicas.append(t)
        por_programa[prog] = unicas
    return por_programa


def ler_bancas():
    bancas = []
    for r in csv.DictReader(open(EVENTOS, encoding="utf-8")):
        sigla = r["programa"].split(" - ")[-1]
        if sigla in SIGLAS:
            bancas.append({"id": r["id"], "programa": sigla, "titulo": r["titulo"]})
    return bancas


def montar_prompt(programa, titulo, temas):
    lista = "\n".join(f"- {caminho}" for _, caminho, _ in temas)
    return (
        f"Uma banca de pós-graduação do ICMC-USP (programa {programa}) tem o título abaixo.\n"
        f"Escolha o tema que melhor descreve o assunto, entre os temas oficiais do programa:\n\n"
        f"{lista}\n"
        f"- {OUTROS}\n\n"
        f"Regras:\n"
        f"- Decida só pelo título.\n"
        f"- Escolha sempre um tema folha, o último nome de cada caminho (ex: 'Aprendizado de Máquina e "
        f"Mineração de Dados', e não 'Inteligência Artificial').\n"
        f"- Use \"{OUTROS}\" só se nenhum tema servir de verdade.\n\n"
        f"Título: {titulo}"
    )


def montar_esquema(temas):
    nomes = [t[2] for t in temas]
    return {
        "type": "object",
        "properties": {
            "tema": {"type": "string", "enum": nomes + [OUTROS]},
        },
        "required": ["tema"],
        "additionalProperties": False,
    }


def chamar_ollama(modelo, prompt, esquema):
    resp = requests.post(f"{OLLAMA}/api/chat", timeout=300, json={
        "model": modelo,
        "messages": [{"role": "user", "content": prompt}],
        "format": esquema,
        "think": False,              # escolher entre opcoes nao precisa de raciocinio longo
        "stream": False,
        "options": {"temperature": 0},
    })
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def classificar(modelo, banca, temas):
    prompt = montar_prompt(banca["programa"], banca["titulo"], temas)
    return json.loads(chamar_ollama(modelo, prompt, montar_esquema(temas)))["tema"]


def ler_feitos():
    """ids das bancas que ja estao em temas_llm.csv."""
    if not SAIDA.exists():
        return set()
    return {r["id"] for r in csv.DictReader(open(SAIDA, encoding="utf-8"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default=MODELO_PADRAO, help=f"modelo do Ollama (padrao: {MODELO_PADRAO}); apague o csv antes de trocar")
    ap.add_argument("--dry-run", action="store_true", help="so mostra o prompt de uma banca")
    args = ap.parse_args()

    temas_por_programa = ler_temas()
    bancas = ler_bancas()

    if args.dry_run:
        b = bancas[0]
        print(montar_prompt(b["programa"], b["titulo"], temas_por_programa[b["programa"]]))
        esquema = json.dumps(montar_esquema(temas_por_programa[b["programa"]]), ensure_ascii=False)
        print("\nesquema:", esquema[:300] + ("..." if len(esquema) > 300 else ""))
        return

    feitos = ler_feitos()
    falta = [b for b in bancas if b["id"] not in feitos]
    print(f"{len(bancas)} bancas, {len(feitos)} ja classificadas, {len(falta)} a fazer ({args.modelo})")

    erros = []
    macro_de = {p: {t[2]: t[0] for t in ts} for p, ts in temas_por_programa.items()}
    novo = not SAIDA.exists() or SAIDA.stat().st_size == 0

    with open(SAIDA, "a", newline="", encoding="utf-8") as arq:
        w = csv.writer(arq)
        if novo:
            w.writerow(["id", "programa", "titulo", "tema", "macro_tema"])
        for i, b in enumerate(falta, 1):
            try:
                tema = classificar(args.modelo, b, temas_por_programa[b["programa"]])
            except requests.ConnectionError:
                raise SystemExit(f"Nao consegui falar com o Ollama em {OLLAMA}: ele esta rodando? (ollama serve)")
            except Exception as e:
                if i == 1:                # primeira falha: provavelmente modelo errado, para em vez de falhar 475 vezes
                    raise SystemExit(f"A primeira chamada falhou, parando:\n{e}")
                erros.append((b["id"], str(e)))
                continue
            feitos.add(b["id"])
            w.writerow([b["id"], b["programa"], b["titulo"], tema, macro_de[b["programa"]].get(tema, OUTROS)])
            arq.flush()
            if i % 25 == 0:
                print(f"  {i}/{len(falta)}")

    print(f"{len(feitos)} bancas em {SAIDA}")
    if erros:
        print(f"{len(erros)} com erro (rode de novo para tentar so essas):")
        for i, e in erros[:5]:
            print("  ", i, e[:120])


if __name__ == "__main__":
    main()