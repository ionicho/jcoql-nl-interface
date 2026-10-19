"""
ft_paraphrase_v4.py - come ft_paraphrase.py (Gemini riscrive le richieste, ogni riscrittura e' controllata) ma con i controlli
delle famiglie nuove di v4. Non modifica ft_paraphrase.py: lo importa e ne estende i controlli.

Controlli aggiunti:
  - i nomi di campo nuovi che compaiono nella richiesta (es. email_copy, notti_x10) devono restare identici;
  - TRANSLATE: la riscrittura deve parlare di traduzione/dizionario; REMOVE FIELDS: di campi tolti; rinomina: di rinominare;
    ORDER BY: di ordinamento, con la direzione giusta (crescente/decrescente); DROP GROUPING FIELDS: di non ripetere il campo;
  - la proiezione dopo un filtro non deve per forza dire "solo" (nell'originale non lo dice);
  - join a tre collezioni, collezioni derivate, due EXPAND, raggruppamento per due campi: NON si parafrasano (restano le richieste
    originali, gia' in italiano corrente), perche' la riscrittura puo' perdere quale collezione o quale campo.
Uso (come ft_paraphrase.py, da finetune\\):
    ..\\venv\\Scripts\\python.exe .\\ft_paraphrase_v4.py --selftest
    ..\\venv\\Scripts\\python.exe .\\ft_paraphrase_v4.py --meta out_v4\\dataset_meta.jsonl --out out_v4
Scrive out_v4\\train_final.jsonl ed out_v4\\eval_heldout.jsonl (serve la chiave Gemini nel .env).
"""
import re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ft_paraphrase as fp

fp.PURE = re.compile(r"\b(FILTER|JOIN|GROUP|MERGE|INTERSECT|SUBTRACT|BUILD)\b|UNPACK\s+\.")
fp.NEED = [(("FILTER GENERATE BUILD" if m == "GENERATE BUILD" else m), alts) for m, alts in fp.NEED] + [
    ("TRANSLATE(", ("tradu", "dizionario", "convert", "mapp")),
    ("REMOVE FIELDS", ("sen", "tog", "rimuov", "esclud", "elimin", "nasc", "rinom", "tranne", "cancell")),
    ("ORDER BY", ("ordin", "crescent")),
    ("DROP GROUPING FIELDS", ("sen", "tog", "ripet", "elimin", "rimuov", "non ")),
    ("ADD FIELDS", ("aggiung", "in più", "in piu", "campo", "calcol", "rinom", "tradu", "con ")),
]
NO_PARAPHRASE = [
    (lambda q: "chaintemp1" in q and "JOIN OF" in q and "EXPAND" not in q, "join a tre collezioni"),
    (lambda q: "_with_" in q, "collezione derivata"),
    (lambda q: q.count("EXPAND") >= 2, "due EXPAND"),
    (lambda q: re.search(r"BY \.[\w.]+, \.[\w.]+ INTO", q) is not None, "raggruppamento per due campi"),
]
_base_check = fp.check_variant


def check_v4(orig_nl, query, v):
    for test, why in NO_PARAPHRASE:
        if test(query):
            return f"famiglia non parafrasata ({why})"
    base_nl = re.sub(r"\bsenza (i campi|il campo)\b", "campi tolti", orig_nl) if "REMOVE FIELDS" in query else orig_nl
    r = _base_check(base_nl, query, v)
    if r:
        return r
    low = v.lower()
    for tok in re.findall(r"\b\w+_\w+\b", orig_nl):         # nomi di campo nuovi: identici
        if tok.lower() not in low:
            return f"manca il nome {tok}"
    if "ORDER BY" in query:
        if " DESC" in query and "decresc" not in low:
            return "direzione ordinamento persa"
        if re.search(r" ASC;", query) and ("cresc" not in low or "decresc" in low):
            return "direzione ordinamento persa"
    if "ADD FIELDS" in query and "REMOVE FIELDS" in query and not any(a in low for a in ("rinom", "nuovo nome", "chiam")):
        return "concetto rinomina perso"
    return None


EXTRA_RULES = """- se la richiesta contiene un nome di campo nuovo con il trattino basso (es. email_copy) o un numero, riportalo IDENTICO;
- "tradotto/traducendo con il dizionario" resta una traduzione tramite dizionario; "rinominando" resta una rinomina; "senza i campi X" / "togliendo X" resta la rimozione di quei campi;
- "ordinando ... in ordine crescente/decrescente" mantiene la stessa direzione;
- "senza ripetere il campo di raggruppamento" resta tale;"""
_base_prompt = fp.make_prompt
fp.make_prompt = lambda items: _base_prompt(items).replace("Varia forma e lessico", EXTRA_RULES + "\nVaria forma e lessico")
fp.check_variant = check_v4


def selftest_v4():
    bad = 0
    cases = [
        ("GET COLLECTION m; FILTER GENERATE ADD FIELDS { .email_copy: .email };", "Mostrami iscritti aggiungendo un campo email_copy con il valore di email",
         [("Elenca gli iscritti con un campo in più, email_copy, uguale a email", True), ("Elenca gli iscritti con un campo copia dell'email", False)]),
        ("GET COLLECTION m; FILTER GENERATE REMOVE FIELDS { .eta };", "Trova iscritti senza il campo età",
         [("Dammi gli iscritti togliendo l'età", True), ("Dammi gli iscritti con l'età", False)]),
        ("GET COLLECTION s; GROUP PARTITION TRUE BY .t INTO .g ORDER BY .p TYPE NUMERIC DESC;", "Raggruppa serre per tipo, ordinando gli elementi di ogni gruppo per prezzo in ordine decrescente",
         [("Raggruppa le serre per tipo, con gli elementi di ogni gruppo ordinati per prezzo dal più alto, in ordine decrescente", True),
          ("Raggruppa le serre per tipo, con gli elementi di ogni gruppo ordinati per prezzo in ordine crescente", False)]),
        ("GET DICTIONARY d@x AS dict; GET COLLECTION c; FILTER GENERATE ADD FIELDS { .a_t: TRANSLATE(.a, dict) };", "Voglio vedere casse, traducendo prodotto con il dizionario",
         [("Mostrami le casse con il prodotto tradotto tramite il dizionario", True), ("Mostrami le casse con il prodotto", False)]),
        ("GET COLLECTION c; FILTER CASE WHERE .x > 3 GENERATE BUILD { .a: .a };", "Elenca a di ispettori con x maggiore di 3",
         [("Dammi il campo a degli ispettori con x maggiore di 3", True)]),
        ("JOIN OF COLLECTIONS a@d AS x, b@d AS y CASE WHERE .x.f = .y._id; SAVE AS chaintemp1@d; GET COLLECTION chaintemp1; JOIN OF COLLECTIONS chaintemp1@d AS x, c@d AS y CASE WHERE .x.x.g = .y._id;",
         "Mostrami a, b e c", [("Dammi a, b e c collegati", False)]),
    ]
    for q, nl, cs in cases:
        for v, want in cs:
            r = check_v4(nl, q, v); ok = (r is None) == want; bad += not ok
            print(f"{'OK ' if ok else 'ERR'} {v!r:90} -> {r or 'accettata'}")
    return bad


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        b = fp.selftest() + selftest_v4()
        sys.exit(1 if b else 0)
    fp.main()
