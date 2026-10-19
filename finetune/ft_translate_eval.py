"""
ft_translate_eval.py - traduce in INGLESE le richieste di valutazione del fine-tuning (le 144 di eval_heldout_v1.jsonl,
stesso campione di ft_eval.py: per famiglia 10, seed 1), lasciando identici schema, database, query di riferimento e risultato atteso.
Cosi' ft_eval_cpp.py puo' valutare il modello v3 su richieste inglesi contro schemi con nomi in italiano e confrontare
con la valutazione italiana gia' fatta (soup\\eval_v3_lora_runtime.csv: 138/144).

Il template del prompt resta quello italiano dell'addestramento (e' quello che il modello vede nell'uso reale): cambia SOLO il testo
tra le virgolette di RICHIESTA.

Controlli su ogni traduzione (scartata e rigenerata fino a 3 volte, altrimenti finisce in scarti):
  1. ogni numero della richiesta italiana compare uguale nella traduzione;
  2. ogni parola della richiesta che e' un VALORE d'esempio dello schema (es. 'giardino') resta IDENTICA (i valori nei dati non si
     traducono). I nomi di campo e di collezione invece SI TRADUCONO in modo naturale ("prezzo" -> "price"): e' proprio il caso che
     vogliamo misurare, una richiesta in inglese su uno schema con nomi in italiano;
  3. un secondo passaggio con Gemini (temperatura 0) deve confermare che le due frasi chiedono la stessa cosa (stessi filtri,
     stessi operatori, stesse collezioni, stesso verso di confronto).
Uso (da finetune\\, serve GEMINI_API_KEY nel .env):
    ..\\venv\\Scripts\\python.exe .\\ft_translate_eval.py --selftest
    ..\\venv\\Scripts\\python.exe .\\ft_translate_eval.py
Scrive out\\eval_heldout_v1_en.jsonl (solo le richieste che hanno superato i controlli), out\\eval_heldout_v1_en_review.csv
(italiano | inglese, per controllo a occhio) e out\\eval_heldout_v1_en_scarti.json.
"""
import argparse, collections, csv, json, os, random, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REQ = re.compile(r'RICHIESTA: "(.*)"', re.S)


def schema_tokens(instruction):
    """Valori d'esempio dello schema nel prompt (es. 'giardino'): sono dati, non si traducono."""
    toks = set(re.findall(r"\(es\. '([^']+)'\)", instruction))
    return {t for t in toks if len(t) >= 3}


def check(it, en, instruction, ref=""):
    if not en or not isinstance(en, str):
        return "traduzione vuota"
    if re.search(r"[àèéìòù]", en.lower()) and not re.search(r"[àèéìòù]", it.lower()):
        pass
    for n in re.findall(r"\d+(?:[.,]\d+)?", it):
        if n not in en and n.replace(",", ".") not in en:
            return f"numero perso o cambiato: {n}"
    low_en = en.lower()
    for tok in schema_tokens(instruction):
        if re.search(rf"(?<![\w]){re.escape(tok.lower())}(?![\w])", it.lower()) and tok.lower() not in low_en:
            return f"nome o valore dello schema non riportato identico: {tok}"
    for q in re.findall(r"(?<!\w)'([^']+)'(?!\w)", it):     # apici veri, non gli apostrofi di "l'elenco ... l'intersezione"
        if q.lower() not in low_en:
            return f"valore tra apici perso: {q}"
    # i valori testuali della query di riferimento che la richiesta italiana nomina vanno riportati come nella richiesta italiana
    for lit in set(re.findall(r"'([^']+)'", ref or "")):
        m = re.search(re.escape(lit), it, re.I)
        if m and m.group(0) not in en:
            return f"valore dei dati non riportato identico: {m.group(0)}"
    if len(en) > 3 * len(it) + 40 or len(en) < len(it) // 3:
        return "lunghezza anomala"
    return None


TR_PROMPT = """Translate each Italian request below into natural English. The requests ask a system to retrieve data from a database.
Rules:
- keep EXACTLY as written: numbers and every data value (a word or phrase that names a value stored in the data, usually a name or label such as 'giardino', 'venere', 'Adulto'): data values are NOT translated;
- translate everything else naturally, including the words that refer to fields and collections (a user writing in English would say "price" for the Italian "prezzo", "orders" for "ordini");
- do not add, drop or change any condition, comparison direction (more than / at least / less than / between), logical connector (and / or / not), or collection;
- do not add explanations; keep it a request, as in the original ("Show me...", "List...", "Link each X to Y...").
Return ONLY JSON: a list of objects {{"id": <id>, "en": "<English>"}}, one per request.

Requests:
{items}
"""

JUDGE_PROMPT = """Do these two requests ask a database for exactly the same thing (same conditions, same comparison operators and directions, same logical connectors, same collections)? Ignore language and wording.
Italian: {it}
English: {en}
Return ONLY JSON: {{"same": true or false, "why": "<short reason if false>"}}"""


def gem(prompt, temperature):
    import ft_paraphrase as fp
    return json.loads(fp.call_gemini(prompt, temperature=temperature))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default="out/eval_heldout_v1.jsonl")
    ap.add_argument("--per-family", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="out/eval_heldout_v1_en.jsonl")
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    rows = [json.loads(l) for l in open(a.eval, encoding="utf-8")]
    by = collections.defaultdict(list)
    for r in rows:
        by[r["meta"]["family"]].append(r)
    rng = random.Random(a.seed)
    sample = [x for fam in sorted(by) for x in rng.sample(by[fam], min(a.per_family, len(by[fam])))]
    print(f"{len(rows)} esempi tenuti fuori, campione di {len(sample)} (stesso di ft_eval.py)")
    for i, r in enumerate(sample):
        r["_id"] = i
        r["_it"] = REQ.search(r["instruction"]).group(1)

    done, reason = {}, {}
    pending = list(sample)
    for attempt in range(1, a.tries + 1):
        if not pending:
            break
        print(f"--- passaggio {attempt}: {len(pending)} richieste da tradurre")
        temp = 0.2 if attempt == 1 else 0.6
        for i in range(0, len(pending), a.batch):
            chunk = pending[i:i + a.batch]
            items = "\n".join(f'{r["_id"]}: {r["_it"]}' for r in chunk)
            try:
                out = gem(TR_PROMPT.format(items=items), temp)
            except Exception as ex:
                print("   errore Gemini:", str(ex)[:120]); continue
            got = {int(o["id"]): o.get("en", "") for o in out if isinstance(o, dict) and "id" in o}
            for r in chunk:
                en = (got.get(r["_id"]) or "").strip()
                why = check(r["_it"], en, r["instruction"], r["output"])
                if why is None:
                    try:
                        j = gem(JUDGE_PROMPT.format(it=r["_it"], en=en), 0.0)
                        if not j.get("same"):
                            why = "giudice: " + str(j.get("why", ""))[:90]
                    except Exception as ex:
                        why = "giudice non raggiungibile"
                if why is None:
                    done[r["_id"]] = en
                else:
                    reason[r["_id"]] = why
            print(f"   {min(i + a.batch, len(pending))}/{len(pending)}  ok finora {len(done)}")
        pending = [r for r in sample if r["_id"] not in done]

    outrows = []
    for r in sample:
        if r["_id"] not in done:
            continue
        en = done[r["_id"]]
        new = dict(r); new.pop("_id"); new.pop("_it")
        new["instruction"] = r["instruction"].replace(f'RICHIESTA: "{r["_it"]}"', f'RICHIESTA: "{en}"')
        new["meta"] = dict(r["meta"]); new["meta"]["nl_it"] = r["_it"]; new["meta"]["nl_variant"] = en
        outrows.append(new)
    with open(a.out, "w", encoding="utf-8") as f:
        for o in outrows:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    rev = a.out.replace(".jsonl", "_review.csv")
    with open(rev, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f); w.writerow(["famiglia", "db", "italiano", "inglese"])
        for o in outrows:
            w.writerow([o["meta"]["family"], o["meta"]["db"], o["meta"]["nl_it"], o["meta"]["nl_variant"]])
    scarti = {str(r["_id"]): {"it": r["_it"], "motivo": reason.get(r["_id"], "mai tradotta")} for r in sample if r["_id"] not in done}
    json.dump(scarti, open(a.out.replace(".jsonl", "_scarti.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\ntradotte e controllate: {len(outrows)}/{len(sample)}   scartate: {len(scarti)}")
    print("scritti:", a.out, "|", rev)


def selftest():
    ins = ('X\nCOLLEZIONI DISPONIBILI: rooms, guests\nSCHEMA:\nrooms: ._id:string (es. \'room_1\'), .view:string (es. \'giardino\'), .beds:integer\n'
           'guests: ._id:string, .name:string\nRICHIESTA: "Elenca le camere con vista giardino e almeno 2 letti"')
    it = "Elenca le camere con vista giardino e almeno 2 letti"
    ref = "GET COLLECTION rooms; FILTER CASE WHERE .view = 'giardino' AND .beds >= 2;"
    cases = [("List the rooms with view giardino and at least 2 beds", True),
             ("List the rooms with a garden view and at least 2 beds", False),      # valore tradotto
             ("List the rooms with view giardino and at least 3 beds", False),       # numero cambiato
             ("List the rooms with view giardino and at least two beds", False),     # numero a parole
             ("", False)]
    bad = 0
    for en, want in cases:
        r = check(it, en, ins, ref); ok = (r is None) == want; bad += not ok
        print(("OK " if ok else "ERR"), repr(en)[:70], "->", r or "accettata")
    r2 = check("Mostrami le zone con stato attivo", "Show me the zones with status active", ins, "GET COLLECTION z; FILTER CASE WHERE .stato = 'attivo';")
    bad += (r2 is None); print("OK " if r2 else "ERR", "valore 'attivo' tradotto ->", r2)
    r3 = check("Mostrami le zone con stato attivo", "Show me the zones whose stato is attivo", ins, "GET COLLECTION z; FILTER CASE WHERE .stato = 'attivo';")
    bad += (r3 is not None); print("OK " if r3 is None else "ERR", "valore 'attivo' mantenuto ->", r3 or "accettata")
    print("schema_tokens:", sorted(schema_tokens(ins)))
    print("autotest:", "tutto ok" if not bad else f"{bad} errori")


if __name__ == "__main__":
    main()
