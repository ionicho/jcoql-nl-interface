"""
ft_paraphrase.py - riscrive in italiano naturale le richieste generate da ft_gen.py (con Gemini), senza cambiarne il significato.

Perche': le richieste di ft_gen sono volutamente meccaniche ("camere con occupata falso"). Cosi' il modello imparerebbe un italiano
da robot. Gemini le riscrive, ma OGNI riscrittura e' controllata prima di entrare nel dataset:
  - contiene tutti i numeri e i valori (parole tra apici nella query) della richiesta originale;
  - mantiene il senso degli operatori (maggiore/minore/almeno/al massimo/diverso, senza/con assegnato);
  - non contiene sintassi di query, non e' un duplicato, non e' troppo simile a una richiesta dei test (mmai nel training).
Riprendibile: scrive paraphrases.jsonl riga per riga e salta gli esempi gia' fatti.

Uso (dalla cartella finetune, dopo ft_gen.py):
    ..\\venv\\Scripts\\python.exe .\\ft_paraphrase.py --meta out\\dataset_meta.jsonl --out out
    ..\\venv\\Scripts\\python.exe .\\ft_paraphrase.py --selftest
"""
import argparse, csv, glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.join(HERE, "..")
NUM = re.compile(r"\d+(?:[.,]\d+)?")

# operatore (come scritto dal generatore) -> espressioni di cui almeno una deve comparire nella riscrittura
OPS = [
    ("maggiore di",      ("maggior", "più di", "piu di", "superior", "oltre", "sopra", "eccede", "supera", ">")),
    ("di almeno",        ("almeno", "non meno", "minimo", "a partire", "pari o", "maggiore o uguale", "non inferior", ">=")),
    ("inferiore a",      ("inferior", "meno di", "minor", "sotto", "al di sotto", "più basso", "piu basso", "<")),
    ("non superiore a",  ("non superior", "al massimo", "massimo", "fino a", "non oltre", "al più", "al piu", "pari o inferior", "minore o uguale", "<=")),
    ("diverso da",       ("divers", "non ", "tranne", "esclus", "eccetto", "senza", "!=")),
    ("che non hanno",    ("non ", "tranne", "esclus", "eccetto", "senza", "escludendo")),
    ("assegnato",        ("assegnat", "valorizzat", "present", "indicat", "specificat", "compilat", "ha un", "hanno un", "con ")),
    ("senza",            ("senza", "privi", "priv", "manca", "non hanno", "non ha", "vuot", "null", "non specificat", "non assegnat")),
]
# parole che nel linguaggio indicano altre operazioni (MERGE/INTERSECT/SUBTRACT): vietate nelle richieste di filtro/join
SETWORDS = re.compile(r"interse|differenza|sottra|unione|duplicat|\bunisci\b|\bunire\b")
# la riscrittura deve conservare il concetto dell'operazione (altrimenti l'etichetta non e' piu' motivata dal testo)
NEED = [
    ("INTERSECT COLLECTIONS", ("interse", "in comune", "contemporaneamente")),
    ("SUBTRACT COLLECTIONS",  ("differenza", "sottra", "esclu", "tranne", "eccetto", "senza", "non ")),
    ("MERGE COLLECTIONS",     ("unisc", "union", "unend", "unit", "unir", "combin", "fond", "insieme")),
    ("GROUP PARTITION",       ("grupp", "suddivid", "divid", "classific", "aggreg", "ripart", "raggrupp")),
    ("GENERATE BUILD",        ("sol", "unicament", "esclusivament", "limit", "restring")),
]
# query "pure" (solo GET / EXPAND): una riscrittura non puo' aggiungere condizioni che la query non ha
EXTRA_COND = re.compile(r"\b(che|dove|solo|soltanto|attiv\w*|disponibil\w*|valid\w*|corrent\w*|principal\w*)\b")
PURE = re.compile(r"\b(FILTER|JOIN|GROUP|MERGE|INTERSECT|SUBTRACT|BUILD)\b")
# il linguaggio non ha un ordinamento: una riscrittura di un raggruppamento ("per porto di partenza") non deve parlare di ordinare
ORDERING = re.compile(r"\bordin(?:a|ando|at[aeio]|ament)")
SYNTAX = re.compile(r"\b(GET|FILTER|COLLECTION|EXPAND|JOIN|UNPACK|SELECT|WHERE|CASE)\b|;|\.\w+\.\w+|\bitem\b")


def anchors(nl, query):
    nums = [n.replace(",", ".") for n in NUM.findall(nl)]
    vals = [v for v in re.findall(r"'([^']+)'", query)]
    return nums, vals


def check_variant(orig_nl, query, v):
    """None se la riscrittura e' accettabile, altrimenti il motivo."""
    if not isinstance(v, str):
        return "non e' una stringa"
    v = v.strip()
    if not 8 <= len(v) <= 220:
        return "lunghezza"
    if SYNTAX.search(v):
        return "contiene sintassi di query"
    low = v.lower().replace("piu'", "più").replace("po'", "poco")
    if ORDERING.search(low):
        return "parla di ordinamento"
    if not re.search(r"\b(MERGE|INTERSECT|SUBTRACT)\b", query) and SETWORDS.search(low):
        return "parola di altra operazione"
    nums, vals = anchors(orig_nl, query)
    vnums = {n.replace(",", ".") for n in NUM.findall(v)}
    for n in nums:
        if n not in vnums:
            return f"manca il numero {n}"
    # il chiaro-scuro dei valori: la parola deve comparire (senza distinzione tra maiuscole)
    for val in vals:
        if val.lower() not in low:
            return f"manca il valore {val}"
    if not PURE.search(query) and EXTRA_COND.search(low):
        return "condizione in piu'"
    for marker, alts in NEED:
        if marker in query and not any(a in low for a in alts):
            return "concetto dell'operazione perso"
    o = orig_nl.lower()
    for key, alts in OPS:
        if key in o and not any(a in low for a in alts):
            return f"operatore '{key}' perso"
    # operatori opposti introdotti per errore
    if "maggiore di" in o and any(x in low for x in ("inferior", "meno di", "minor", "sotto")) and not any(x in low for x in ALTS_OK_UP):
        return "operatore invertito"
    if "inferiore a" in o and any(x in low for x in ("maggior", "più di", "piu di", "superior", "sopra", "oltre")) and not any(x in low for x in ALTS_OK_DOWN):
        return "operatore invertito"
    return None


ALTS_OK_UP = ("maggior", "più di", "piu di", "superior", "oltre", "sopra")
ALTS_OK_DOWN = ("inferior", "meno di", "minor", "sotto")


def similar(a, b):
    ta, tb = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(ta & tb) / max(1, len(ta | tb))


def load_test_requests():
    """Richieste dei test gia' fatti (nei CSV della cartella del progetto): mai nel training."""
    out = set()
    for p in glob.glob(os.path.join(PARENT, "*.csv")):
        try:
            for r in csv.DictReader(open(p, encoding="utf-8-sig")):
                for k in ("query_nl", "richiesta", "nl", "request"):
                    if r.get(k):
                        out.add(r[k].strip())
        except Exception:
            pass
    return out


def make_prompt(items):
    return f"""Riscrivi ciascuna richiesta in italiano naturale, come la scriverebbe una persona vera che interroga un database.
Per ogni richiesta dammi 2 riscritture DIVERSE tra loro e diverse dall'originale.

REGOLE DI FEDELTA' (le riscritture vengono controllate automaticamente e scartate se le violano):
- stesso identico significato: stesse condizioni, stessi numeri, stessi valori (parole come 'giardino' o 'Torino'), nessuna condizione in piu' o in meno;
- non cambiare il verso dei confronti ("maggiore di" resta maggiore, "inferiore a" resta minore, "di almeno" resta almeno, "non superiore a" resta al massimo);
- "senza X" resta "senza/privo di X"; "con X assegnato" resta "con X indicato/valorizzato"; "con A vero/falso" si puo' dire in modo naturale ("attivi", "non attivi");
- mantieni il nome dell'insieme (libri, camere, pazienti...), anche al singolare se serve;
- se la richiesta nomina un'operazione, la riscrittura la deve nominare: "raggruppa/dividi in gruppi", "intersezione", "differenza tra insiemi" (o "escludendo"), "unendo i due insiemi senza duplicati", "con solo/soltanto <campi>" (non trasformare mai una richiesta di soli campi in una richiesta di tutto il documento);
- "per <campo>" in una richiesta di raggruppamento resta un raggruppamento: non parlare mai di ordinare ("ordina", "ordinandoli", "ordinati");
- non usare sintassi di query, ne' nomi di campo con il punto, ne' la parola "item".
Varia forma e lessico: imperativo, domanda ("Quali ...?"), forma breve, tono informale, sinonimi.

Rispondi SOLO con JSON: {{"<id>": ["riscrittura 1", "riscrittura 2"], ...}}
Richieste:
{json.dumps(items, ensure_ascii=False)}"""


def call_gemini(prompt, temperature=0.9):
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PARENT, ".env")); load_dotenv()
    except Exception:
        pass
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    m = genai.GenerativeModel("gemini-3.1-flash-lite-preview",
                              generation_config=genai.GenerationConfig(temperature=temperature, response_mime_type="application/json"))
    return m.generate_content(prompt).text


def selftest():
    q = "GET COLLECTION rooms; FILTER CASE WHERE .view = 'giardino' AND .beds >= 2;"
    nl = "Mostrami camere con vista uguale a giardino e con letti di almeno 2"
    cases = [("Quali camere hanno vista sul giardino e almeno 2 letti?", True),
             ("Dammi le camere con vista giardino e un massimo di 2 letti", False),     # operatore cambiato
             ("Quali camere hanno vista sul parco e almeno 2 letti?", False),            # valore perso
             ("Quali camere hanno vista sul giardino e almeno 3 letti?", False),         # numero cambiato
             ("GET COLLECTION rooms WHERE giardino 2", False),                           # sintassi
             ("camere giardino con almeno due letti", False),
             ("Interseca le camere con vista giardino e almeno 2 letti", False)]   # parola di un'altra operazione                            # numero scritto a parole
    bad = 0
    for v, want in cases:
        r = check_variant(nl, q, v)
        ok = (r is None) == want
        bad += not ok
        print(f"{'OK ' if ok else 'ERR'} {v!r:70} -> {r or 'accettata'}")
    qg, nlg = "GET COLLECTION a; GROUP PARTITION TRUE BY .porto INTO .aByPorto;", "Raggruppa viaggi per porto"
    for v, want in [("Dividi i viaggi in gruppi in base al porto", True), ("Raggruppa i viaggi ordinandoli per porto", False),
                    ("Quanti ordini ci sono per ogni stato?", True)]:
        r = check_variant(nlg, qg, v) if "ordini" not in v else check_variant(nlg, qg, "Suddividi gli ordini in gruppi per stato")
        ok = (r is None) == want; bad += not ok
        print(f"{'OK ' if ok else 'ERR'} {v!r:70} -> {r or 'accettata'}")
    q2, nl2 = "GET COLLECTION cars; FILTER CASE WHERE .km > 1000;", "Elenca auto con chilometri maggiore di 1000"
    for v, want in [("Quali auto hanno piu' di 1000 chilometri?", True), ("Quali auto hanno meno di 1000 chilometri?", False)]:
        r = check_variant(nl2, q2, v); ok = (r is None) == want; bad += not ok
        print(f"{'OK ' if ok else 'ERR'} {v!r:70} -> {r or 'accettata'}")
    qe = "GET COLLECTION s; EXPAND UNPACK TRUE ARRAY .sensori TO .e;"
    for v, want in [("Elenca ogni sensore delle serre su una riga", True), ("Mostrami i sensori attivi nelle serre", False)]:
        r = check_variant("Visualizza ogni sensore delle serre", qe, v); ok = (r is None) == want; bad += not ok
        print(f"{'OK ' if ok else 'ERR'} {v!r:70} -> {r or 'accettata'}")
    fam = [
        ("GET COLLECTION a; GROUP PARTITION TRUE BY .stato INTO .aByStato;", "Raggruppa ordini per stato",
         [("Suddividi gli ordini in gruppi in base allo stato", True), ("Quanti ordini ci sono per ogni stato?", False)]),
        ("GET COLLECTION a; FILTER CASE WHERE .x = 'v'; SAVE AS selA@d; GET COLLECTION a; FILTER CASE WHERE .y = 'w'; SAVE AS selB@d; INTERSECT COLLECTIONS selA@d, selB@d;",
         "Mostrami a con x uguale a v e con y uguale a w, usando l'intersezione tra i due insiemi",
         [("Quali a hanno x uguale a v e anche y uguale a w, ottenuti con l'intersezione dei due insiemi?", True),
          ("Mostrami a con x uguale a v e con y uguale a w", False)]),
        ("GET COLLECTION a; FILTER GENERATE BUILD { .nome: .nome };", "Mostrami a con solo nome",
         [("Elenca le a mostrando esclusivamente il nome", True), ("Dammi le a con il loro nome", False)]),
    ]
    for q3, nl3, cs in fam:
        for v, want in cs:
            r = check_variant(nl3, q3, v); ok = (r is None) == want; bad += not ok
            print(f"{'OK ' if ok else 'ERR'} {v!r:70} -> {r or 'accettata'}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", default=os.path.join("out", "dataset_meta.jsonl"))
    ap.add_argument("--out", default="out")
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--pause", type=float, default=5)
    ap.add_argument("--keep-original", type=float, default=0.15, help="quota di esempi che mantengono anche la richiesta meccanica originale")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(1 if selftest() else 0)
    rows = [json.loads(l) for l in open(a.meta, encoding="utf-8")]
    pfile = os.path.join(a.out, "paraphrases.jsonl")
    done = {}
    if os.path.exists(pfile):
        for l in open(pfile, encoding="utf-8"):
            r = json.loads(l); done[r["i"]] = r
    tests = load_test_requests()
    print(f"{len(rows)} esempi; gia' fatti {len(done)}; richieste di test da evitare: {len(tests)}")
    todo = [i for i in range(len(rows)) if i not in done]
    stats = {"ok": 0, "scartate": 0}; why = {}
    with open(pfile, "a", encoding="utf-8") as fh:
        for s in range(0, len(todo), a.batch):
            idx = todo[s:s + a.batch]
            items = {str(i): rows[i]["meta"]["nl"] for i in idx}
            try:
                data = json.loads(call_gemini(make_prompt(items)))
            except Exception as ex:
                print(f"   blocco {s // a.batch + 1}: errore {ex!r}"); time.sleep(a.pause); continue
            for i in idx:
                good, seen = [], set()
                for v in (data.get(str(i)) or [])[:4]:
                    r = check_variant(rows[i]["meta"]["nl"], rows[i]["output"], v)
                    if r is None and (v.strip().lower() in seen or v.strip() == rows[i]["meta"]["nl"]):
                        r = "duplicato"
                    if r is None and any(similar(v, t) >= 0.8 for t in tests):
                        r = "troppo simile a una richiesta di test"
                    if r:
                        stats["scartate"] += 1
                        k = " ".join(r.split(" ")[:2]); why[k] = why.get(k, 0) + 1
                    else:
                        good.append(v.strip()); seen.add(v.strip().lower()); stats["ok"] += 1
                fh.write(json.dumps({"i": i, "variants": good}, ensure_ascii=False) + "\n"); fh.flush()
                done[i] = {"i": i, "variants": good}
            print(f"   blocco {s // a.batch + 1}/{(len(todo) + a.batch - 1) // a.batch}: accettate {stats['ok']}, scartate {stats['scartate']}")
            time.sleep(a.pause)
    # dataset finale: ogni esempio con le sue riscritture (e, per una quota, anche la richiesta originale)
    import random
    rng = random.Random(1)
    tr, ev = [], []
    for i, r in enumerate(rows):
        vs = [v for v in done.get(i, {}).get("variants", []) if check_variant(r["meta"]["nl"], r["output"], v) is None]
        texts = list(vs)
        if not texts or rng.random() < a.keep_original:
            texts.append(r["meta"]["nl"])
        for t in texts:
            prompt = re.sub(r'RICHIESTA: ".*"\n$', lambda m: f'RICHIESTA: "{t}"\n', r["instruction"])
            rec = {"instruction": prompt, "input": "", "output": r["output"]}
            (tr if r["meta"]["split"] == "train" else ev).append((rec, dict(rec, meta=dict(r["meta"], nl_variant=t))))
    json.dump(why, open(os.path.join(a.out, "scarti_motivi.json"), "w"), ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, "train_final.jsonl"), "w", encoding="utf-8") as f:
        for rec, _ in tr: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(os.path.join(a.out, "eval_heldout.jsonl"), "w", encoding="utf-8") as f:
        for _, full in ev: f.write(json.dumps(full, ensure_ascii=False) + "\n")
    print(f"scritti train_final.jsonl ({len(tr)} esempi) ed eval_heldout.jsonl ({len(ev)}); scarti per motivo: {why}")


if __name__ == "__main__":
    main()
