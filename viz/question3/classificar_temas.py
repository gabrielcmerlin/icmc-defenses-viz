# Classifica cada banca em um tema (folha de data/temas.json) usando um LLM (API da Anthropic)
# e escreve data/temas_bancas_llm.csv
#
# - o modelo ve SO o titulo e o programa (nunca orientador nem aluno)
# - ele escolhe entre os temas do programa da banca, ou "Outros"
# - funciona com a API da Anthropic (padrao) ou do Google Gemini (--backend gemini, tem nivel gratuito)
# - cada resposta e guardada em data/raw/temas_llm.jsonl (com modelo e data), entao
#   rodar de novo nao refaz as chamadas que ja foram feitas
#
# a chave vem do arquivo .env na raiz do repo (ou de uma variavel de ambiente):
#   ANTHROPIC_API_KEY=...     (Anthropic)
#   GEMINI_API_KEY=...        (Gemini)
# uso:  python3 data/classificar_temas.py                          # Anthropic, roda tudo
#       python3 data/classificar_temas.py --backend gemini         # Gemini (gratis, com limite de uso)
#       python3 data/classificar_temas.py --dry-run                # mostra o prompt de uma banca, sem chamar a API
#       python3 data/classificar_temas.py --modelo claude-haiku-5-5   # modelo mais barato

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).parent
EVENTOS = DATA / "eventos.csv"
TEMAS = DATA / "temas.json"
CACHE = DATA / "raw" / "temas_llm.jsonl"
SAIDA = DATA / "temas_bancas_llm.csv"
SAIDA_ANTIGA = DATA / "temas_bancas.csv"   # rotulos feitos antes, so para comparar no final

MODELOS_PADRAO = {"anthropic": "claude-opus-5-5", "gemini": "gemini-2.5-flash"}
CHAVES = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}
OUTROS = "Outros"
NENHUM = "Nenhum"

# sigla no final do nome do programa -> chave do temas.json
SIGLAS = {"PPG-CCMC", "PPG-Mat", "PIPGES"}


def carregar_env():
    """Le o .env da raiz do repo (linhas CHAVE=valor); variaveis ja definidas no terminal tem prioridade."""
    arq = DATA.parent / ".env"
    if not arq.exists():
        return
    for linha in open(arq, encoding="utf-8"):
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            nome, valor = linha.split("=", 1)
            os.environ.setdefault(nome.removeprefix("export ").strip(), valor.strip().strip("\"'"))


def ler_temas():
    """Para cada programa: lista de (macro, caminho_completo, folha), sem folhas repetidas."""
    arvore = json.load(open(TEMAS, encoding="utf-8"))
    por_programa = {}

    def percorre(nos, caminho, macro, saida):
        for no in nos:
            c = caminho + [no["nome"]]
            if no.get("sub_temas"):
                percorre(no["sub_temas"], c, macro, saida)
            else:
                saida.append((macro, " > ".join(c), no["nome"]))

    for prog, v in arvore.items():
        folhas = []
        for m in v["macro_temas"]:
            percorre([m], [], m["nome"], folhas)
        vistos, unicas = set(), []
        for f in folhas:                 # ex: "Fisica Matematica" aparece em 2 areas do PPG-Mat: fica a primeira
            if f[2] not in vistos:
                vistos.add(f[2])
                unicas.append(f)
        por_programa[prog] = unicas
    return por_programa


def ler_bancas():
    bancas = []
    for r in csv.DictReader(open(EVENTOS, encoding="utf-8")):
        sigla = r["programa"].split(" - ")[-1]
        if sigla in SIGLAS:
            bancas.append({"id": r["id"], "programa": sigla, "titulo": r["titulo"]})
    return bancas


def montar_prompt(programa, titulo, folhas):
    lista = "\n".join(f"- {caminho}" for _, caminho, _ in folhas)
    return (
        f"Uma banca de pós-graduação do ICMC-USP (programa {programa}) tem o título abaixo.\n"
        f"Escolha o tema que melhor descreve o assunto, entre os temas oficiais do programa:\n\n"
        f"{lista}\n"
        f"- {OUTROS}\n\n"
        f"Regras:\n"
        f"- Decida só pelo título.\n"
        f"- Escolha sempre um tema folha, o último nome de cada caminho (ex: 'Aprendizado de Máquina e "
        f"Mineração de Dados', e não 'Inteligência Artificial').\n"
        f"- Use \"{OUTROS}\" só se nenhum tema servir de verdade.\n"
        f"- tema_secundario é opcional: use só se o título mistura claramente dois temas, senão \"{NENHUM}\".\n"
        f"- confianca: alta (título claro), media (mais de um tema plausível) ou baixa (título vago).\n\n"
        f"Título: {titulo}"
    )


def montar_esquema(folhas):
    nomes = [f[2] for f in folhas]
    return {
        "type": "object",
        "properties": {
            "tema": {"type": "string", "enum": nomes + [OUTROS]},
            "tema_secundario": {"type": "string", "enum": nomes + [NENHUM]},
            "confianca": {"type": "string", "enum": ["alta", "media", "baixa"]},
        },
        "required": ["tema", "tema_secundario", "confianca"],
        "additionalProperties": False,
    }


def chamar_anthropic(client, modelo, prompt, esquema):
    resp = client.messages.create(
        model=modelo,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": esquema}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("o modelo recusou a resposta")
    return "".join(b.text for b in resp.content if b.type == "text")


def chamar_gemini(client, modelo, prompt, esquema):
    from google.genai import types
    resp = client.models.generate_content(
        model=modelo,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json",
                                           response_json_schema=esquema),
    )
    return resp.text


def classificar(backend, client, modelo, banca, folhas):
    chamar = chamar_gemini if backend == "gemini" else chamar_anthropic
    prompt = montar_prompt(banca["programa"], banca["titulo"], folhas)
    for tentativa in range(5):          # no plano gratuito o limite por minuto estoura facil: espera e tenta de novo
        try:
            texto = chamar(client, modelo, prompt, montar_esquema(folhas))
            break
        except Exception as e:
            passageiro = any(k in str(e) for k in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "overloaded"))
            if not passageiro or tentativa == 4:    # erro de verdade (modelo errado, chave invalida...): falha logo
                raise
            time.sleep(10 * 2 ** tentativa)
    r = json.loads(texto)
    return {"id": banca["id"], "modelo": modelo, "data": datetime.now().isoformat(timespec="seconds"), **r}


def ler_cache(modelo):
    feitos = {}
    if CACHE.exists():
        for linha in open(CACHE, encoding="utf-8"):
            r = json.loads(linha)
            if r["modelo"] == modelo:
                feitos[r["id"]] = r
    return feitos


def comparar_com_antigo(resultado):
    """Quanto o LLM concordou com os rotulos que ja existiam em temas_bancas.csv."""
    if not SAIDA_ANTIGA.exists():
        return
    antigo = {r["id"]: r["tema_folha"] for r in csv.DictReader(open(SAIDA_ANTIGA, encoding="utf-8"))}
    comuns = [i for i in resultado if i in antigo]
    if not comuns:
        return
    iguais = sum(resultado[i]["tema"] == antigo[i] for i in comuns)
    print(f"concordancia com {SAIDA_ANTIGA.name}: {iguais}/{len(comuns)} ({100 * iguais / len(comuns):.0f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["anthropic", "gemini"], default="anthropic")
    ap.add_argument("--modelo", help="padrao: claude-opus-5-5 (anthropic) ou gemini-2.5-flash (gemini)")
    ap.add_argument("--listar-modelos", action="store_true", help="(gemini) lista os modelos que a sua chave pode usar")
    ap.add_argument("--dry-run", action="store_true", help="so mostra o prompt de uma banca")
    ap.add_argument("--paralelo", type=int, help="chamadas ao mesmo tempo (padrao: 6 anthropic, 2 gemini)")
    args = ap.parse_args()
    args.modelo = args.modelo or MODELOS_PADRAO[args.backend]
    args.paralelo = args.paralelo or (2 if args.backend == "gemini" else 6)

    temas = ler_temas()
    bancas = ler_bancas()

    if args.dry_run:
        b = bancas[0]
        print(montar_prompt(b["programa"], b["titulo"], temas[b["programa"]]))
        print("\nesquema:", json.dumps(montar_esquema(temas[b["programa"]]), ensure_ascii=False)[:300], "...")
        return

    carregar_env()
    chave = CHAVES[args.backend]
    if not os.environ.get(chave):
        sys.exit(f"Nao achei {chave}: coloque {chave}=... no arquivo .env na raiz do repo")

    if args.backend == "gemini":
        from google import genai
        client = genai.Client()
    else:
        import anthropic
        client = anthropic.Anthropic()

    if args.listar_modelos:
        if args.backend != "gemini":
            sys.exit("--listar-modelos so existe para --backend gemini")
        for m in client.models.list():
            if "generateContent" in (m.supported_actions or []):
                print(m.name.removeprefix("models/"))
        return

    feitos = ler_cache(args.modelo)
    falta = [b for b in bancas if b["id"] not in feitos]
    print(f"{len(bancas)} bancas, {len(feitos)} ja classificadas, {len(falta)} a fazer ({args.modelo})")

    CACHE.parent.mkdir(exist_ok=True)
    erros = []

    if falta:       # testa uma banca antes: se o modelo/chave estiver errado, para aqui em vez de falhar 475 vezes
        try:
            classificar(args.backend, client, args.modelo, falta[0], temas[falta[0]["programa"]])
        except Exception as e:
            sys.exit(f"A primeira chamada falhou, parando:\n{e}")

    def tarefa(b):
        try:
            return classificar(args.backend, client, args.modelo, b, temas[b["programa"]])
        except Exception as e:            # uma banca com erro nao derruba as outras
            erros.append((b["id"], str(e)))
            return None

    with ThreadPoolExecutor(args.paralelo) as pool, open(CACHE, "a", encoding="utf-8") as arq:
        for i, r in enumerate(pool.map(tarefa, falta), 1):
            if r:
                feitos[r["id"]] = r
                arq.write(json.dumps(r, ensure_ascii=False) + "\n")
                arq.flush()
            if i % 25 == 0:
                print(f"  {i}/{len(falta)}")

    # csv final
    macro_de = {p: {f[2]: f[0] for f in fs} for p, fs in temas.items()}
    with open(SAIDA, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "programa", "titulo", "tema_folha", "tema_macro", "tema_secundario", "confianca"])
        for b in bancas:
            r = feitos.get(b["id"])
            if not r:
                continue
            macro = macro_de[b["programa"]].get(r["tema"], OUTROS)
            sec = "" if r["tema_secundario"] == NENHUM else r["tema_secundario"]
            w.writerow([b["id"], b["programa"], b["titulo"], r["tema"], macro, sec, r["confianca"]])

    print(f"{len(feitos)} bancas em {SAIDA}")
    if erros:
        print(f"{len(erros)} com erro (rode de novo para tentar so essas):")
        for i, e in erros[:5]:
            print("  ", i, e[:120])
    comparar_com_antigo(feitos)


if __name__ == "__main__":
    main()
