"""
rerun_rounds.py - rifà i round 1, 2 e 3 (41 richieste) con la pipeline attuale, su tutti i modelli.

Per ogni modello e ogni richiesta: /api/generate -> /api/execute -> confronto con l'atteso
(oracolo di verify_execution.py). Confronta poi con l'esito della campagna originale
(verification_results.csv, ultima riga per modello e richiesta).

Richiede nella stessa cartella: verify_execution.py, repeatability.py, verification_results.csv.
Riprendibile: scrive ogni riga subito su rerun_rounds.csv; se lo interrompi e rilanci, salta le righe fatte.

ATTENZIONE: ogni chiamata a /api/generate viene registrata anche in test_campaign_log.csv.
Prima di lanciare fai una copia:
    copy test_campaign_log.csv test_campaign_log_prima_rerun.csv

Uso (backend avviato su localhost:8000):
    .\\venv\\Scripts\\python.exe .\\rerun_rounds.py
    .\\venv\\Scripts\\python.exe .\\rerun_rounds.py --models gemini gemma4
    .\\venv\\Scripts\\python.exe .\\rerun_rounds.py --runs 3      # più passate (modelli non deterministici)
Output: rerun_rounds.csv, rerun_rounds_riepilogo.csv
"""
import argparse, collections, csv, os, time
import requests
import verify_execution as V
import repeatability as R

ROUNDS = [
    ("R1", [  # round 1: 8 richieste
        "Mostrami tutti gli utenti",
        "Mostrami i prodotti con uno sconto maggiore del 20%",
        "Mostrami i prodotti biologici con un rating di almeno 4",
        "Mostrami i prodotti biologici oppure quelli con uno sconto superiore al 30%",
        "Espandi le recensioni dei prodotti in righe separate",
        "Collega ogni ordine all'utente che lo ha effettuato",
        "Raggruppa i prodotti per categoria",
        "Unisci i prodotti biologici e quelli scontati in un'unica collezione, senza duplicati"]),
    ("R2", [  # round 2: 5 richieste
        "Mostrami i prodotti che non sono biologici",
        "Mostrami i prodotti biologici con un rating di almeno 4, oppure quelli con uno sconto superiore al 50%",
        "Mostrami gli ordini superiori a 100 euro insieme all'utente che li ha effettuati",
        "Mostrami le recensioni dei prodotti con un voto superiore a 4",
        "Conta quanti prodotti ci sono per categoria"]),
    ("R3", [  # round 3: 28 richieste
        "Mostrami i prodotti con un rating compreso tra 3 e 4.5",
        "Mostrami i prodotti con uno sconto compreso tra il 10% e il 30%",
        "Mostrami i prodotti senza nessuno sconto",
        "Mostrami i prodotti con un rating inferiore a 3",
        "Mostrami i prodotti biologici con uno sconto maggiore del 20%",
        "Mostrami i prodotti non biologici con un rating di almeno 4",
        "Mostrami i prodotti che non sono biologici e non hanno nessuno sconto",
        "Mostrami i prodotti biologici oppure quelli con un rating di almeno 4.5",
        "Mostrami i prodotti con uno sconto superiore al 40%, oppure con un rating inferiore a 2",
        "Mostrami i prodotti biologici con uno sconto superiore al 10%, oppure quelli con un rating di almeno 4.5",
        "Mostrami i prodotti non biologici oppure quelli con uno sconto superiore al 50%",
        "Mostrami le recensioni dei prodotti con un voto uguale a 5",
        "Mostrami le recensioni dei prodotti con un voto inferiore a 3",
        "Mostrami le recensioni dei soli prodotti biologici",
        "Espandi gli articoli degli ordini in righe separate",
        "Collega ogni recensione all'utente che l'ha scritta",
        "Mostrami gli ordini inferiori a 50 euro insieme all'utente che li ha effettuati",
        "Collega ogni ordine ai prodotti acquistati",
        "Collega ogni utente ai suoi ordini",
        "Raggruppa gli ordini per utente",
        "Raggruppa i prodotti biologici per categoria",
        "Raggruppa i prodotti in biologici e non biologici",
        "Unisci i prodotti con un rating di almeno 4 e quelli con uno sconto superiore al 30% in un'unica collezione, senza duplicati",
        "Unisci i prodotti biologici e quelli senza sconto in un'unica collezione, mantenendo i duplicati",
        "Unisci gli ordini superiori a 100 euro e quelli inferiori a 20 euro in un'unica collezione",
        "Aggiungi a ogni ordine un campo con il totale maggiorato dell'IVA al 22%",
        "Aggiungi a ogni prodotto un campo con la differenza tra 5 e il rating",
        "Mostrami solo la categoria e il rating di ogni prodotto"]),
]
DEFAULT_MODELS = ["gemini", "gemma4", "llama32", "llama"]
OUT = "rerun_rounds.csv"
OUT_SUM = "rerun_rounds_riepilogo.csv"
FIELDS = ["modello", "round", "n", "run", "query_nl", "valida", "tentativi", "tempo_gen_s",
          "query_jcoql", "esito", "dettaglio", "esito_originale"]


def load_old():
    old = {}
    if os.path.exists("verification_results.csv"):
        for r in csv.DictReader(open("verification_results.csv", encoding="utf-8-sig")):
            old[(r["modello"], r["query_nl"].strip().rstrip("."))] = r["esito"]     # ultima riga vince
    return old


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--tuned", action="store_true", help="per llama: usa il prompt tuned (llama-server con LoRA)")
    ap.add_argument("--gen-timeout", type=int, default=1500)
    ap.add_argument("--exec-timeout", type=int, default=120)
    ap.add_argument("--pause-gemini", type=int, default=20)
    ap.add_argument("--wait-rate-limit", type=int, default=70)
    ap.add_argument("--max-rate-retries", type=int, default=4)
    a = ap.parse_args()

    C = V.load_collections_mongo()
    old = load_old()
    rows = list(csv.DictReader(open(OUT, encoding="utf-8-sig"))) if os.path.exists(OUT) else []
    done = {(r["modello"], r["query_nl"], int(r["run"])) for r in rows}
    new_file = not os.path.exists(OUT)
    fh = open(OUT, "a", newline="", encoding="utf-8-sig")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file:
        w.writeheader()
    tot = sum(len(q) for _, q in ROUNDS) * a.runs
    for m in a.models:
        rr = requests.post(f"{V.BACKEND}/api/set_llm", params={"llm_type": m})
        if rr.status_code != 200:
            print(f"!! impossibile selezionare {m}: {rr.text[:100]}"); continue
        print(f"=== modello {m} ===")
        if a.tuned and m == "llama":
            r2 = requests.post(f"{V.BACKEND}/api/set_local_prompt_mode", params={"mode": "tuned"})
            if r2.status_code != 200:
                print("!! impossibile impostare il prompt tuned"); continue
        k = 0
        for run in range(1, a.runs + 1):
            for rname, qs in ROUNDS:
                for n, nl in enumerate(qs, 1):
                    k += 1
                    if (m, nl, run) in done:
                        continue
                    row = R.one_run(m, f"{rname}-{n}", nl, run, C, a.gen_timeout, a.exec_timeout)
                    tries = 0
                    while R.is_rate_limited(row) and tries < a.max_rate_retries:
                        tries += 1
                        print(f"   quota/timeout: attendo {a.wait_rate_limit}s e rifaccio ({tries}/{a.max_rate_retries})")
                        time.sleep(a.wait_rate_limit)
                        row = R.one_run(m, f"{rname}-{n}", nl, run, C, a.gen_timeout, a.exec_timeout)
                    if m == "gemini" and a.pause_gemini:
                        time.sleep(a.pause_gemini)
                    out = {"modello": m, "round": rname, "n": n, "run": run, "query_nl": nl,
                           "valida": row["valida"], "tentativi": row["tentativi"], "tempo_gen_s": row["tempo_gen_s"],
                           "query_jcoql": row["query_jcoql"], "esito": row["esito"], "dettaglio": row["dettaglio"],
                           "esito_originale": old.get((m, nl.strip().rstrip(".")), "")}
                    w.writerow(out); fh.flush(); rows.append(out)
                    print(f"[{m} {k}/{tot}] {rname}-{n:<2} {row['esito'][:26]:26} (prima: {out['esito_originale'][:22]})  {row['tempo_gen_s']}s")
    fh.close()
    if a.tuned:
        try: requests.post(f"{V.BACKEND}/api/set_local_prompt_mode", params={"mode": "compact"})
        except Exception: pass

    summ = []
    for m in a.models:
        for rname, _ in ROUNDS + [("TOT", [])]:
            rs = [r for r in rows if r["modello"] == m and (rname == "TOT" or r["round"] == rname)]
            if not rs:
                continue
            ok = sum(r["esito"].startswith("ESATTO") for r in rs)
            ok_old = sum(r["esito_originale"].startswith("ESATTO") for r in rs)
            tg = [float(r["tempo_gen_s"]) for r in rs if r["tempo_gen_s"] != ""]
            summ.append({"modello": m, "round": rname, "righe": len(rs), "valide": sum(r["valida"] == "SI" for r in rs),
                         "esatte_ora": ok, "esatte_campagna_originale": ok_old,
                         "tempo_medio_s": round(sum(tg) / len(tg), 1) if tg else ""})
    with open(OUT_SUM, "w", newline="", encoding="utf-8-sig") as f:
        sw = csv.DictWriter(f, fieldnames=list(summ[0])); sw.writeheader(); sw.writerows(summ)
    print("\nRIEPILOGO (ESATTO = risultato uguale all'atteso calcolato dai dati)")
    for s in summ:
        print(f"{s['modello']:8} {s['round']:4} righe {s['righe']:>3}  valide {s['valide']:>3}  esatte ora {s['esatte_ora']:>3}  campagna originale {s['esatte_campagna_originale']:>3}  tempo medio {s['tempo_medio_s']}s")
    print("scritti", OUT, "e", OUT_SUM)


if __name__ == "__main__":
    main()
