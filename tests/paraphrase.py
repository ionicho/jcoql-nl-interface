"""
paraphrase.py - robustezza alle parafrasi: 12 richieste dei round 1-3, ognuna con l'originale + 3 riformulazioni
(stesso significato, parole diverse). Ogni formulazione e' giudicata dallo stesso atteso (oracolo) della richiesta originale.

Richiede nella stessa cartella: verify_execution.py, repeatability.py. Backend avviato su localhost:8000.
Riprendibile (paraphrase.csv). ATTENZIONE: scrive anche in test_campaign_log.csv:
    copy test_campaign_log.csv test_campaign_log_prima_parafrasi.csv

Uso:
    .\\venv\\Scripts\\python.exe tests/paraphrase.py --models gemini
    .\\venv\\Scripts\\python.exe tests/paraphrase.py --models gemma4 llama32 llama
    .\\venv\\Scripts\\python.exe tests/paraphrase.py --models llama --tuned   (llama-server v3 + LLAMACPP_URL)
Output: paraphrase.csv, paraphrase_riepilogo.csv
"""
import argparse, csv, os, time
import requests
import verify_execution as V
import repeatability as R

# (id, originale, [tre parafrasi])
SET = [
 ("P1", "Mostrami i prodotti con uno sconto maggiore del 20%",
  ["Quali prodotti hanno uno sconto oltre il 20%?", "Elenca i prodotti scontati di più del 20 per cento", "Voglio vedere i prodotti il cui sconto supera il 20%"]),
 ("P2", "Mostrami i prodotti con un rating compreso tra 3 e 4.5",
  ["Quali prodotti hanno un rating tra 3 e 4.5?", "Elenca i prodotti con valutazione da 3 a 4.5", "Dammi i prodotti il cui rating va da 3 a 4.5 compresi"]),
 ("P3", "Mostrami i prodotti che non sono biologici",
  ["Quali prodotti non sono biologici?", "Elenca i prodotti non bio", "Fammi vedere solo i prodotti che non risultano biologici"]),
 ("P4", "Mostrami i prodotti biologici oppure quelli con uno sconto superiore al 30%",
  ["Quali prodotti sono biologici o hanno uno sconto oltre il 30%?", "Elenca i prodotti bio e anche quelli scontati di più del 30%", "Voglio i prodotti biologici, più quelli con sconto maggiore del 30%"]),
 ("P5", "Mostrami i prodotti biologici con un rating di almeno 4",
  ["Quali prodotti biologici hanno rating 4 o superiore?", "Elenca i prodotti bio con valutazione minima 4", "Dammi i prodotti biologici che hanno un rating non inferiore a 4"]),
 ("P6", "Espandi le recensioni dei prodotti in righe separate",
  ["Metti ogni recensione dei prodotti su una riga a parte", "Trasforma le recensioni dei prodotti in righe singole", "Voglio una riga per ogni recensione dei prodotti"]),
 ("P7", "Collega ogni ordine all'utente che lo ha effettuato",
  ["Associa ogni ordine al suo utente", "Per ogni ordine, aggiungi i dati dell'utente che l'ha fatto", "Unisci gli ordini con gli utenti che li hanno effettuati"]),
 ("P8", "Raggruppa i prodotti per categoria",
  ["Dividi i prodotti in gruppi in base alla categoria", "Organizza i prodotti per categoria", "Fammi vedere i prodotti raggruppati per categoria"]),
 ("P9", "Mostrami gli ordini superiori a 100 euro insieme all'utente che li ha effettuati",
  ["Quali ordini superano i 100 euro? Mostrali con il relativo utente", "Collega gli ordini di importo maggiore di 100 euro ai loro utenti", "Elenca gli ordini oltre 100 euro con i dati di chi li ha fatti"]),
 ("P10", "Mostrami le recensioni dei prodotti con un voto superiore a 4",
  ["Quali recensioni hanno un voto oltre 4?", "Elenca le recensioni dei prodotti con voto maggiore di 4", "Voglio vedere le recensioni con voto più alto di 4"]),
 ("P11", "Mostrami i prodotti senza nessuno sconto",
  ["Quali prodotti non hanno alcuno sconto?", "Elenca i prodotti con sconto pari a zero", "Fammi vedere i prodotti che non sono scontati"]),
 ("P12", "Unisci i prodotti biologici e quelli scontati in un'unica collezione, senza duplicati",
  ["Metti insieme i prodotti bio e quelli scontati in una sola collezione, senza ripetizioni", "Crea un'unica collezione con i prodotti biologici e quelli scontati, evitando i duplicati", "Fondi in una collezione sola i prodotti biologici e i prodotti in sconto, senza doppioni"]),
]
MAP = {p: orig for _, orig, ps in SET for p in ps}
_orig_expected = V.expected
V.expected = lambda nl, C: _orig_expected(MAP.get(nl, nl), C)

OUT, OUT_SUM = V.res("paraphrase.csv"), V.res("paraphrase_riepilogo.csv")
FIELDS = ["modello", "id", "variante", "query_nl", "valida", "tentativi", "tempo_gen_s", "query_jcoql", "esito", "dettaglio"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["gemini", "gemma4", "llama32", "llama"])
    ap.add_argument("--gen-timeout", type=int, default=1500)
    ap.add_argument("--exec-timeout", type=int, default=120)
    ap.add_argument("--pause-gemini", type=int, default=20)
    ap.add_argument("--wait-rate-limit", type=int, default=70)
    ap.add_argument("--max-rate-retries", type=int, default=4)
    ap.add_argument("--tuned", action="store_true", help="prompt tuned (llama-server v3); le righe sono salvate come <modello>-tuned")
    a = ap.parse_args()
    C = V.load_collections_mongo()
    rows = list(csv.DictReader(open(OUT, encoding="utf-8-sig"))) if os.path.exists(OUT) else []
    done = {(r["modello"], r["query_nl"]) for r in rows}
    new_file = not os.path.exists(OUT)
    fh = open(OUT, "a", newline="", encoding="utf-8-sig"); w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file: w.writeheader()
    for m in a.models:
        lab = m + "-tuned" if a.tuned else m
        rr = requests.post(f"{V.BACKEND}/api/set_llm", params={"llm_type": m})
        if rr.status_code != 200:
            print(f"!! impossibile selezionare {m}"); continue
        if a.tuned:
            r2 = requests.post(f"{V.BACKEND}/api/set_local_prompt_mode", params={"mode": "tuned"})
            if r2.status_code != 200:
                print("!! il backend non ha /api/set_local_prompt_mode"); return
        print(f"=== modello {lab} ===")
        for pid, orig, ps in SET:
            for v, nl in enumerate([orig] + ps):
                if (lab, nl) in done: continue
                row = R.one_run(m, pid, nl, 1, C, a.gen_timeout, a.exec_timeout)
                tries = 0
                while R.is_rate_limited(row) and tries < a.max_rate_retries:
                    tries += 1; print(f"   quota/timeout: attendo {a.wait_rate_limit}s ({tries}/{a.max_rate_retries})")
                    time.sleep(a.wait_rate_limit)
                    row = R.one_run(m, pid, nl, 1, C, a.gen_timeout, a.exec_timeout)
                if m == "gemini" and a.pause_gemini: time.sleep(a.pause_gemini)
                out = {"modello": lab, "id": pid, "variante": "originale" if v == 0 else f"parafrasi {v}", "query_nl": nl,
                       "valida": row["valida"], "tentativi": row["tentativi"], "tempo_gen_s": row["tempo_gen_s"],
                       "query_jcoql": row["query_jcoql"], "esito": row["esito"], "dettaglio": row["dettaglio"]}
                w.writerow(out); fh.flush(); rows.append(out)
                print(f"[{lab}] {pid:4} {out['variante']:11} {row['esito'][:26]:26} {row['tempo_gen_s']}s")
    fh.close()
    try: requests.post(f"{V.BACKEND}/api/set_local_prompt_mode", params={"mode": "compact"})
    except Exception: pass
    summ = []
    for m in [x + "-tuned" if a.tuned else x for x in a.models]:
        for pid, _, _ in SET + [("TOT", 0, 0)]:
            rs = [r for r in rows if r["modello"] == m and (pid == "TOT" or r["id"] == pid)]
            if not rs: continue
            o = [r for r in rs if r["variante"] == "originale"]; p = [r for r in rs if r["variante"] != "originale"]
            f = lambda L: sum(r["esito"].startswith("ESATTO") for r in L)
            summ.append({"modello": m, "id": pid, "originale_esatta": f"{f(o)}/{len(o)}", "parafrasi_esatte": f"{f(p)}/{len(p)}"})
    with open(OUT_SUM, "w", newline="", encoding="utf-8-sig") as fo:
        sw = csv.DictWriter(fo, fieldnames=list(summ[0])); sw.writeheader(); sw.writerows(summ)
    print("\nRIEPILOGO")
    for s in summ:
        if s["id"] == "TOT": print(f"{s['modello']:8} originali {s['originale_esatta']:>6}   parafrasi {s['parafrasi_esatte']:>6}")
    print("scritti", OUT, "e", OUT_SUM)

if __name__ == "__main__":
    main()
