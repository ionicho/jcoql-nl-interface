"""
ft_eval.py - valuta un modello Ollama sugli esempi tenuti fuori (database MAI visti in addestramento).

Per ogni richiesta: il modello genera la query -> si esegue con il backend (POST /api/execute) ->
si confronta il numero di risultati con quello atteso (calcolato da Python). Si riporta anche l'uguaglianza
testuale con la query di riferimento (metrica piu' severa: query equivalenti ma scritte in modo diverso
non contano come esatte).

Uso (backend e MongoDB avviati, Ollama attivo), da finetune\\soup:
    python ft_eval.py --model llama3.1-jcoql --per-family 10
    python ft_eval.py --model llama3.1:8b-instruct-q4_K_M --per-family 10     # modello base, prompt breve (NON equo)
    python ft_eval.py --model llama3.1:8b-instruct-q4_K_M --prompt compact    # modello base, prompt del progetto (regole + RAG)

--prompt tuned   (default) il prompt breve dell'addestramento, preso dal file degli esempi;
--prompt compact il prompt "compatto" del backend (regole + schema + 7 esempi RAG), costruito dal
                 backend (POST /api/eval/build_prompt): e' il confronto equo per il modello base.
In entrambi i casi: per default UN solo tentativo, stessa esecuzione e stesso oracolo.
--retry N        dopo un ERRORE_QUERY (query rifiutata dal parser) rigenera fino a N volte, accodando al prompt
                 la query sbagliata e il messaggio di errore. Si riportano sia il risultato al 1o tentativo sia quello dopo i retry.
"""
import argparse, collections, csv, json, os, random, re, time


def clean(txt):
    t = txt.strip()
    t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t).strip()
    return t


def norm(q):
    return re.sub(r"\s+", " ", q).strip().rstrip(";").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama-server+lora")
    ap.add_argument("--eval", default="../out/eval_heldout.jsonl")
    ap.add_argument("--dbs", default="../out/databases.json")
    ap.add_argument("--per-family", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--backend", default="http://localhost:8000")
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--mongo", default="mongodb://localhost:27017")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--no-seed", action="store_true", help="non ricaricare i database in MongoDB")
    ap.add_argument("--prompt", choices=["tuned", "compact"], default="tuned")
    ap.add_argument("--retry", type=int, default=0, help="rigenerazioni dopo ERRORE_QUERY, con errore del parser nel prompt")
    ap.add_argument("--llamacpp", default=None, help="URL di llama-server (es. http://localhost:8081): genera li' con il template chat di addestramento invece di usare Ollama")
    ap.add_argument("--gemini", action="store_true", help="genera con Gemini (stesso modello e temperatura 0 del backend; serve GEMINI_API_KEY nel .env); con --prompt compact")
    ap.add_argument("--pause", type=float, default=0.0, help="secondi di pausa dopo ogni richiesta (Gemini: 4)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    import requests
    tok = None
    if a.llamacpp:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained("meta-llama/Llama-3.1-8B-Instruct")
    gem = None
    if a.gemini:
        try:
            from dotenv import load_dotenv
            for p in (".env", "../.env", "../../.env"):
                if os.path.exists(p):
                    load_dotenv(p); break
        except Exception:
            pass
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        gem = genai.GenerativeModel("gemini-3.1-flash-lite-preview", generation_config=genai.GenerationConfig(temperature=0))
    rows = [json.loads(l) for l in open(a.eval, encoding="utf-8")]
    by = collections.defaultdict(list)
    for r in rows:
        by[r["meta"]["family"]].append(r)
    rng = random.Random(a.seed)
    sample = [x for fam in sorted(by) for x in rng.sample(by[fam], min(a.per_family, len(by[fam])))]
    print(f"modello {a.model}: {len(rows)} esempi tenuti fuori, campione di {len(sample)} su {len(by)} famiglie")

    mongo = None
    if not a.no_seed:
        from pymongo import MongoClient
        mongo = MongoClient(a.mongo, serverSelectionTimeoutMS=4000); mongo.admin.command("ping")
        dbs = {d["name"]: d for d in json.load(open(a.dbs, encoding="utf-8"))}
        for name in sorted({r["meta"]["db"] for r in sample}):
            mongo.drop_database(name)
            for coll, docs in dbs[name]["collections"].items():
                if docs:
                    mongo[name][coll].insert_many([dict(d) for d in docs])
        print("database sintetici caricati in MongoDB")

    res, tally = [], collections.defaultdict(collections.Counter)
    tally1 = collections.defaultdict(collections.Counter)
    for k, r in enumerate(sample, 1):
        m, ref, dbn = r["meta"], r["output"], r["meta"]["db"]
        t0 = time.time()
        prompt = r["instruction"]
        if a.prompt == "compact":
            nl = re.search(r'RICHIESTA: "(.*)"', r["instruction"]).group(1)
            prompt = requests.post(f"{a.backend}/api/eval/build_prompt", params={
                "database_name": dbn, "nl_query": nl, "mode": "compact"}, timeout=120).json()["prompt"]

        def attempt(p):
            """una generazione + esecuzione; ritorna (gen, esito, dettaglio, errore_completo)"""
            gen, err = "", ""
            try:
                if gem is not None:
                    gen, last = "", None
                    for w in range(5):          # quota/limite di frequenza: attende e riprova (fino a 5 volte)
                        try:
                            gen = clean(gem.generate_content(p).text); last = None; break
                        except Exception as ex:
                            last = ex
                            if "429" in str(ex) or "quota" in str(ex).lower() or "exhausted" in str(ex).lower():
                                time.sleep(70)
                            else:
                                break
                    if last is not None:
                        return gen, "ERRORE_MODELLO", str(last)[:150], ""
                    if a.pause: time.sleep(a.pause)
                elif a.llamacpp:
                    pr = tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False, add_generation_prompt=True).replace("<|begin_of_text|>", "", 1)
                    g = requests.post(a.llamacpp + "/completion", json={"prompt": pr, "n_predict": 600, "temperature": 0,
                                      "stop": ["<|eot_id|>"], "cache_prompt": False}, timeout=1800).json()
                    gen = clean(g.get("content", ""))
                else:
                    g = requests.post(f"{a.ollama}/api/generate", json={
                        "model": a.model, "prompt": p, "stream": False,
                        "options": {"temperature": 0, "num_predict": 600,
                                    "num_ctx": 4096 if a.prompt == "tuned" else 8192}}, timeout=600).json()
                    gen = clean(g.get("response", ""))
            except Exception as ex:
                return gen, "ERRORE_MODELLO", str(ex)[:150], ""
            if mongo is not None:
                for coll in re.findall(r"SAVE AS\s+(\w+)@", gen):
                    mongo[dbn].drop_collection(coll)
            try:
                j = requests.post(f"{a.backend}/api/execute", json={"jcoql_query": gen, "database_name": dbn,
                                  "timeout_seconds": a.timeout}, timeout=a.timeout + 30).json()
            except Exception as ex:
                return gen, "ERRORE_BACKEND", str(ex)[:150], ""
            if not j.get("success"):
                err = str(j.get("error") or j.get("detail"))
                return gen, "ERRORE_QUERY", err[:150], err
            n = j.get("count", len(j.get("results") or []))
            if n == m["expected"]:
                return gen, "ESATTO", f"{n} risultati", ""
            return gen, "DIVERSO", f"attesi {m['expected']}, ottenuti {n}", ""

        gen, esito, det, err = attempt(prompt)
        esito1, tentativi = esito, 1
        while esito == "ERRORE_QUERY" and tentativi <= a.retry:
            retry_prompt = (prompt + "\nTENTATIVO PRECEDENTE (query NON valida):\n" + gen +
                            "\nERRORE DEL PARSER: " + err[:500] +
                            "\nScrivi la query corretta. Rispondi SOLO con la query.\n")
            gen, esito, det, err = attempt(retry_prompt)
            tentativi += 1
        tally1[m["family"]][esito1] += 1
        same = norm(gen) == norm(ref)
        tally[m["family"]][esito] += 1
        tally[m["family"]]["identica"] += same
        res.append(dict(famiglia=m["family"], db=dbn, esito=esito, identica=same, dettaglio=det, esito_1o_tentativo=esito1, tentativi=tentativi,
                        richiesta=m.get("nl_variant", m["nl"]), generata=gen, riferimento=ref, secondi=round(time.time() - t0, 1)))
        print(f"[{k}/{len(sample)}] {m['family']:16} {esito:14} {'=' if same else ' '} {det[:60]}")

    suffix = ("" if a.prompt == "tuned" else f"_{a.prompt}") + (f"_retry{a.retry}" if a.retry else "")
    out = a.out or f"eval_{'gemini' if a.gemini else ''}{re.sub(r'[^A-Za-z0-9]+', '_', a.model)}{suffix}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)
    tot = collections.Counter()
    print(f"\nRIEPILOGO {a.model}  (esatti per esecuzione / query identica al riferimento / totale)")
    for fam, c in sorted(tally.items()):
        n = sum(v for kk, v in c.items() if kk != "identica")
        print(f"   {fam:18} {c['ESATTO']:3} / {c['identica']:3} / {n:3}")
        tot["e"] += c["ESATTO"]; tot["i"] += c["identica"]; tot["n"] += n
    print(f"   {'TOTALE':18} {tot['e']:3} / {tot['i']:3} / {tot['n']:3}   -> {100*tot['e']/max(1,tot['n']):.1f}% esatti per esecuzione")
    if a.retry:
        e1 = sum(c["ESATTO"] for c in tally1.values()); q1 = sum(c["ERRORE_QUERY"] for c in tally1.values())
        print(f"   1o tentativo: {e1}/{tot['n']} esatti ({100*e1/max(1,tot['n']):.1f}%), {q1} ERRORE_QUERY; "
              f"dopo al massimo {a.retry} retry: {tot['e']}/{tot['n']} ({100*tot['e']/max(1,tot['n']):.1f}%)")
    print(f"\nscritto {out}")


if __name__ == "__main__":
    main()
