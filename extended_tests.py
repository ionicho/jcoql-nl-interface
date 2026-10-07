"""
extended_tests.py - 37 richieste nuove (22 comuni + 15 difficili) con oracolo, da affiancare alle 41 dei round 1-3.

Contiene: NEW_SETS (gruppo, richieste) e expected_new(nl, C): atteso calcolato dai dati (stessi formati di verify_execution.expected).
Autotest sui JSON seed, senza backend:
    .\\venv\\Scripts\\python.exe .\\extended_tests.py
"""
import json, re, sys
import verify_execution as V

F = "F"   # richieste comuni (frequenti), nuove
D = "D"   # richieste difficili (catene, 3 collezioni, intersezione/differenza, dizionario...)
NEW_SETS = [
 (F, [
  "Mostrami i prodotti della categoria food",
  "Mostrami i prodotti con un prezzo superiore a 1000 euro",
  "Mostrami i prodotti con un prezzo inferiore a 300 euro",
  "Mostrami i prodotti della categoria electronics con uno sconto di almeno 15%",
  "Mostrami i prodotti della categoria books oppure sports",
  "Mostrami i prodotti che non sono della categoria food",
  "Mostrami i prodotti con più di 50 pezzi in magazzino",
  "Mostrami i prodotti con un prezzo compreso tra 200 e 700 euro",
  "Mostrami gli utenti premium",
  "Mostrami gli utenti con più di 40 anni",
  "Mostrami gli utenti che vivono a Torino",
  "Mostrami gli utenti attivi con l'email verificata",
  "Mostrami gli utenti che non sono premium",
  "Mostrami gli ordini con stato confirmed",
  "Mostrami gli ordini con priorità urgent",
  "Mostrami gli ordini senza numero di tracking",
  "Mostrami gli ordini con un totale superiore a 500 euro",
  "Mostrami gli ordini che non sono stati cancellati",
  "Mostrami gli ordini con un totale compreso tra 200 e 600 euro",
  "Raggruppa gli utenti per città",
  "Raggruppa gli ordini per stato",
  "Mostrami solo il nome e il prezzo di ogni prodotto"]),
 (D, [
  "Mostrami le recensioni con voto uguale a 5 dei soli prodotti biologici",
  "Mostrami gli ordini superiori a 500 euro insieme all'utente che li ha effettuati, solo per gli utenti premium",
  "Collega ogni ordine all'utente che lo ha effettuato e ai prodotti acquistati",
  "Mostrami le recensioni scritte da utenti premium",
  "Raggruppa le recensioni per voto",
  "Raggruppa per categoria i prodotti con uno sconto maggiore del 10%",
  "Raggruppa gli ordini per città dell'utente che li ha effettuati",
  "Mostrami i prodotti che sono sia biologici sia con un rating di almeno 4, usando l'intersezione",
  "Mostrami i prodotti con un rating di almeno 4 escludendo quelli biologici, usando la differenza tra insiemi",
  "Unisci in un'unica collezione i prodotti food, electronics e books, senza duplicati",
  "Mostrami i prodotti biologici o con uno sconto superiore al 20%, che abbiano anche un rating di almeno 4",
  "Traduci la categoria di ogni prodotto usando il dizionario delle categorie",
  "Mostrami gli ordini con un numero di tracking assegnato e un totale superiore a 300 euro",
  "Mostrami le recensioni con voto uguale a 3 insieme all'utente che le ha scritte",
  "Mostrami le recensioni con voto di almeno 4 dei prodotti con uno sconto superiore al 10%"]),
]
NEW_ALL = [q for _, qs in NEW_SETS for q in qs]

def _proj(keys):
    def chk(docs):
        bad = sum(1 for d in docs if ({k.split(".")[-1] for k in V._flat(d)} - {"_id"}) != keys)
        return (bad == 0, f"{bad} documenti con campi diversi da {sorted(keys)}")
    return chk

def _check_translate(docs, P, T):
    tr = {t["key"]: t["value"] for t in T}
    src = {str(p["_id"]): p for p in P}
    ok = 0
    for d in docs:
        p = src.get(str(d.get("_id")))
        if p is None:
            continue
        want = tr.get(p["category"])
        vals = [v for k, v in V._flat(d).items() if isinstance(v, str) and k.split(".")[-1] != "category"]
        if want in vals:
            ok += 1
    return (ok == len(P) and len(docs) == len(P), f"{ok}/{len(P)} documenti con la categoria tradotta")

def expected_new(nl, C):
    P, O, U = C["products"], C["orders"], C["users"]
    T = C.get("category_translations") or []
    t = nl.strip().rstrip(".").strip()
    uid = {str(u["_id"]): u for u in U}
    pid = {str(p["_id"]) for p in P}
    prod = {str(p["_id"]): p for p in P}
    revs = [(p, r) for p in P for r in (p.get("reviews") or [])]
    items = [(o, i) for o in O for i in (o.get("items") or [])]
    cat = lambda p: p.get("category")
    R = {
     "Mostrami i prodotti della categoria food": lambda: V.sel(P, lambda d: cat(d) == "food"),
     "Mostrami i prodotti con un prezzo superiore a 1000 euro": lambda: V.sel(P, lambda d: d["price"] > 1000),
     "Mostrami i prodotti con un prezzo inferiore a 300 euro": lambda: V.sel(P, lambda d: d["price"] < 300),
     "Mostrami i prodotti della categoria electronics con uno sconto di almeno 15%": lambda: V.sel(P, lambda d: cat(d) == "electronics" and V.disc(d) >= 15),
     "Mostrami i prodotti della categoria books oppure sports": lambda: V.sel(P, lambda d: cat(d) in ("books", "sports")),
     "Mostrami i prodotti che non sono della categoria food": lambda: V.sel(P, lambda d: cat(d) != "food"),
     "Mostrami i prodotti con più di 50 pezzi in magazzino": lambda: V.sel(P, lambda d: d["stock"] > 50),
     "Mostrami i prodotti con un prezzo compreso tra 200 e 700 euro": lambda: V.sel(P, lambda d: 200 <= d["price"] <= 700),
     "Mostrami gli utenti premium": lambda: V.sel(U, lambda d: d.get("premium") is True),
     "Mostrami gli utenti con più di 40 anni": lambda: V.sel(U, lambda d: d["age"] > 40),
     "Mostrami gli utenti che vivono a Torino": lambda: V.sel(U, lambda d: d["city"] == "Torino"),
     "Mostrami gli utenti attivi con l'email verificata": lambda: V.sel(U, lambda d: d.get("active") is True and d.get("email_verified") is True),
     "Mostrami gli utenti che non sono premium": lambda: V.sel(U, lambda d: d.get("premium") is not True),
     "Mostrami gli ordini con stato confirmed": lambda: V.sel(O, lambda d: d["status"] == "confirmed"),
     "Mostrami gli ordini con priorità urgent": lambda: V.sel(O, lambda d: d["priority"] == "urgent"),
     "Mostrami gli ordini senza numero di tracking": lambda: V.sel(O, lambda d: d.get("tracking_number") is None),
     "Mostrami gli ordini con un totale superiore a 500 euro": lambda: V.sel(O, lambda d: d["total"] > 500),
     "Mostrami gli ordini che non sono stati cancellati": lambda: V.sel(O, lambda d: d["status"] != "cancelled"),
     "Mostrami gli ordini con un totale compreso tra 200 e 600 euro": lambda: V.sel(O, lambda d: 200 <= d["total"] <= 600),
     "Raggruppa gli utenti per città": lambda: V.cnt(len({u["city"] for u in U}), "n gruppi"),
     "Raggruppa gli ordini per stato": lambda: V.cnt(len({o["status"] for o in O}), "n gruppi"),
     "Mostrami solo il nome e il prezzo di ogni prodotto": lambda: {"kind": "custom", "n": len(P), "check": _proj({"name", "price"})},
     # difficili
     "Mostrami le recensioni con voto uguale a 5 dei soli prodotti biologici": lambda: V.cnt(sum(1 for p, r in revs if r["rating"] == 5 and V.organic(p))),
     "Mostrami gli ordini superiori a 500 euro insieme all'utente che li ha effettuati, solo per gli utenti premium":
        lambda: V.cnt(sum(1 for o in O if o["total"] > 500 and str(o.get("user_id")) in uid and uid[str(o["user_id"])].get("premium") is True)),
     "Collega ogni ordine all'utente che lo ha effettuato e ai prodotti acquistati":
        lambda: V.cnt(sum(1 for o, i in items if str(o.get("user_id")) in uid and str(i["product_id"]) in pid)),
     "Mostrami le recensioni scritte da utenti premium": lambda: V.cnt(sum(1 for p, r in revs if uid.get(str(r.get("user")), {}).get("premium") is True)),
     "Raggruppa le recensioni per voto": lambda: V.cnt(len({r["rating"] for p, r in revs}), "n gruppi"),
     "Raggruppa per categoria i prodotti con uno sconto maggiore del 10%": lambda: V.cnt(len({cat(p) for p in P if V.disc(p) > 10}), "n gruppi"),
     "Mostrami i prodotti che sono sia biologici sia con un rating di almeno 4, usando l'intersezione": lambda: V.sel(P, lambda d: V.organic(d) and V.rate(d) >= 4),
     "Mostrami i prodotti con un rating di almeno 4 escludendo quelli biologici, usando la differenza tra insiemi": lambda: V.sel(P, lambda d: V.rate(d) >= 4 and not V.organic(d)),
     "Unisci in un'unica collezione i prodotti food, electronics e books, senza duplicati": lambda: V.sel(P, lambda d: cat(d) in ("food", "electronics", "books")),
     "Mostrami i prodotti biologici o con uno sconto superiore al 20%, che abbiano anche un rating di almeno 4":
        lambda: V.sel(P, lambda d: (V.organic(d) or V.disc(d) > 20) and V.rate(d) >= 4),
     "Traduci la categoria di ogni prodotto usando il dizionario delle categorie": lambda: {"kind": "custom", "n": len(P), "check": lambda docs: _check_translate(docs, P, T)},
     "Mostrami gli ordini con un numero di tracking assegnato e un totale superiore a 300 euro": lambda: V.sel(O, lambda d: d.get("tracking_number") is not None and d["total"] > 300),
     "Mostrami le recensioni con voto uguale a 3 insieme all'utente che le ha scritte": lambda: V.cnt(sum(1 for p, r in revs if r["rating"] == 3 and str(r.get("user")) in uid)),
     "Mostrami le recensioni con voto di almeno 4 dei prodotti con uno sconto superiore al 10%": lambda: V.cnt(sum(1 for p, r in revs if r["rating"] >= 4 and V.disc(p) > 10)),
    }
    R["Raggruppa gli ordini per città dell'utente che li ha effettuati"] = lambda: V.cnt(
        len({uid[str(o["user_id"])]["city"] for o in O if str(o.get("user_id")) in uid}), "n gruppi")
    fn = R.get(t)
    return fn() if fn else None

def install():
    """Fa riconoscere le richieste nuove a V.expected (le vecchie restano invariate)."""
    orig = V.expected
    V.expected = lambda nl, C: (expected_new(nl, C) if nl in NEW_ALL else orig(nl, C))

if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/jcoql-project/jcoql-nl-interface/backend/database"
    C = V.load_collections_seed(base)
    C["category_translations"] = json.load(open(f"{base}/data_category_translations.json", encoding="utf-8"))
    for g, qs in NEW_SETS:
        for q in qs:
            e = expected_new(q, C)
            n = e["n"] if e else "??"
            print(f"{g} atteso {n!s:>3} ({e['kind'] if e else 'MANCA'})  {q}")
