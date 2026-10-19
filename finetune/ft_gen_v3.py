"""
ft_gen_v3.py - dati NUOVI per v3 (join). Non modifica ne' sostituisce ft_gen.py: lo importa e scrive in una cartella a parte.

Cosa cambia rispetto a v1/v2 (solo per i join):
  A. alias POSIZIONALI: il primo collezione dichiarata e' sempre x, la seconda sempre y;
     condizione sempre  .<alias del titolare della FK>.<fk> = .<alias dell'altra>._id
     (il titolare della FK puo' stare per primo o per secondo: 50%). Join su array: x/y posizionali, elemento sempre e,
     tabella temporanea sempre chaintemp1.
  B. database piu' grandi: 3-5 collezioni "vere", piu' relazioni per coppia e 0-2 collezioni derivate distrattore
     ({a}_with_{b}, documenti {o:..., u:...}) come orders_with_users nel jcoql_test.
  C. coppie con ENTRAMBE le relazioni (FK + array): la richiesta nomina il campo, cosi' non e' ambigua.
  D. piu' join: per database --joins-per-db join (circa 30% su array quando esiste una relazione array) + altri esempi
     (filtri/array/group/set/proiezioni/NULL/group_filter/merge) per non far dimenticare il resto.
  Facoltativo: --eval-dbs N database SOLO di valutazione (split heldout), con schemi grandi, per misurare i join su schemi grandi.

Uso (venv del backend, da finetune\\):
    ..\\venv\\Scripts\\python.exe .\\ft_gen_v3.py --v3-dbs 40 --eval-dbs 6 --seed 7 --out out_v3
Scrive in out_v3: dataset_meta.jsonl, dataset_train.jsonl, databases.json (stesso formato di ft_gen.py).
"""
import argparse, json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ft_gen as g
from ft_prompt import build_tuned_prompt

MAX_PROMPT_CHARS = 2800          # v2: massimo osservato 1682 caratteri = 691 token (2.4 car/token); 2800 car = circa 1170 token -> usare max_length 1280 per v3
VERBS = g.JOIN_VERBS2


def make_database_v3(rng, idx, style, null_rate=0.3):
    domains = rng.sample(list(g.VOCAB), k=rng.choice([2, 2, 3]))
    ents = []
    for d in domains:
        ents += list(g.VOCAB[d])
    rng.shuffle(ents)
    ents = ents[:rng.choice([3, 4, 4, 5])]
    plan = {}
    for e in ents:
        cname = e["plural_en"] if style == "en" else g.slug(e["it"])
        if cname in plan:
            continue
        fields = list(e["fields"])
        drop = rng.sample(range(len(fields)), k=rng.choice([0, 0, 1, 2]))
        kept = [f for i, f in enumerate(fields) if i not in drop]
        specs = [g._style_field(f, style) for f in (kept if len(kept) >= 4 else fields)]
        specs = [(n, it, "null", ex) if k in ("text", "enum") and rng.random() < null_rate else (n, it, k, ex)
                 for n, it, k, ex in specs]
        plan[cname] = {"entity_it": e["it"], "entity_en": e["en"], "specs": specs,
                       "n": rng.randint(25, 40), "prefix": g.slug(e["en"])[:4]}
    ids = {c: [f"{p['prefix']}_{i:03d}" for i in range(1, p["n"] + 1)] for c, p in plan.items()}
    names = list(plan)
    rels = []                      # (holder, target, kind, fieldname)
    used_names = {c: set(s[0] for s in plan[c]["specs"]) for c in plan}

    def add_rel(a, b, kind):
        if kind == "ref":
            nm = f"{plan[b]['entity_en']}_id" if style == "en" else f"id_{b}"
            if nm in used_names[a]:
                return False
            plan[a]["specs"].append((nm, "riferimento", "ref", b))
        else:
            base = "items" if style == "en" else "righe"
            nm = base if base not in used_names[a] else f"{base}_{b}"
            if nm in used_names[a]:
                return False
            refsub = f"{plan[b]['entity_en']}_id" if style == "en" else f"id_{b}"
            qtysub = "quantity" if style == "en" else "quantita"
            plan[a]["specs"].append((nm, "elementi", "arr_ref", (b, refsub, qtysub)))
        used_names[a].add(nm)
        rels.append((a, b, kind, nm))
        return True

    if len(names) >= 2:
        pairs = [(a, b) for a in names for b in names if a != b]
        rng.shuffle(pairs)
        linked = set()
        for a, b in pairs:                          # una relazione per coppia, la direzione e' casuale
            if frozenset((a, b)) in linked or rng.random() > 0.55:
                continue
            linked.add(frozenset((a, b)))
            add_rel(a, b, rng.choice(["ref", "ref", "arr_ref"]))
        for a, b, kind, _ in list(rels):            # alcune coppie hanno ANCHE l'altra relazione (FK + array)
            if rng.random() < 0.3:
                add_rel(a, b, "arr_ref" if kind == "ref" else "ref")
    colls = {}
    for cname, p in plan.items():
        docs = []
        for _id in ids[cname]:
            d = {"_id": _id}
            for spec in p["specs"]:
                d[spec[0]] = g._gen_field(rng, spec, ids)
            docs.append(d)
        colls[cname] = {"entity_it": p["entity_it"], "entity_en": p["entity_en"], "specs": p["specs"], "docs": docs}
    # collezioni derivate (distrattori): risultato di un JOIN gia' salvato, documenti {o: doc di A, u: doc di B}
    direct = [r for r in rels if r[2] == "ref"]
    rng.shuffle(direct)
    for a, b, _, fk in direct[:rng.choice([0, 1, 1, 2])]:
        ka, kb = rng.choice([("o", "u"), ("a", "b"), ("p", "q")])
        byid = {d["_id"]: d for d in colls[b]["docs"]}
        docs = [{"_id": f"{ka}{kb}_{i:03d}", ka: d, kb: byid[d[fk]]} for i, d in enumerate(colls[a]["docs"], 1)]
        colls[f"{a}_with_{b}"] = {"entity_it": "risultati dell'unione", "entity_en": "joined", "specs": [], "docs": docs, "derived": True}
    return {"name": f"ft_{style}_{idx:03d}", "style": style, "collections": colls, "rels": rels}


def _it(db, c):
    return db["collections"][c]["entity_it"]


def gen_join_v3(rng, db, want):
    """want: 'direct' | 'array'. Alias posizionali, titolare della FK a destra o a sinistra."""
    rels = [r for r in db["rels"] if r[2] == ("ref" if want == "direct" else "arr_ref")]
    if not rels:
        return None
    a, b, kind, fk = rng.choice(rels)                      # a = titolare della FK / dell'array, b = collezione referenziata
    both = any(r[0] == a and r[1] == b and r[2] != kind for r in db["rels"])
    verb = rng.choice(VERBS)
    ids_b = {d["_id"] for d in db["collections"][b]["docs"]}
    dbn = db["name"]
    A, B = db["collections"][a], db["collections"][b]
    if kind == "ref":
        swap = rng.random() < 0.5                          # True: la collezione con la FK e' dichiarata per seconda
        first, second = (b, a) if swap else (a, b)
        ha, oa = ("y", "x") if swap else ("x", "y")        # alias del titolare e dell'altra
        q = f"JOIN OF COLLECTIONS {first}@{dbn} AS x, {second}@{dbn} AS y CASE WHERE .{ha}.{fk} = .{oa}._id;"
        pf, ps = _it(db, first), _it(db, second)
        forms = [f"{verb} {pf} e {ps}", f"{verb} {pf} con {ps}", f"{verb} {pf} con {ps} corrispondenti",
                 f"{verb} i dati di {pf} e di {ps}", f"{verb} {pf} insieme a {ps}"]
        if swap is False:
            forms += [f"{verb} ogni {pf} con il suo riferimento in {ps}"]
        nl = rng.choice(forms)
        if both:
            nl += f", usando il campo {fk}"
        n = sum(1 for d in A["docs"] if d[fk] in ids_b)
        return dict(family="join_direct", coll=a, nl=nl, query=q, expected=n)
    refsub = [s for s in db["collections"][a]["specs"] if s[0] == fk][0][3][1]
    swap = rng.random() < 0.4
    first, second = ("b", "tmp") if swap else ("tmp", "b")
    ha, oa = ("y", "x") if swap else ("x", "y")
    left = f"{b}@{dbn} AS x, chaintemp1@{dbn} AS y" if swap else f"chaintemp1@{dbn} AS x, {b}@{dbn} AS y"
    q = (f"GET COLLECTION {a}; EXPAND UNPACK TRUE ARRAY .{fk} TO .e; SAVE AS chaintemp1@{dbn}; "
         f"GET COLLECTION chaintemp1; JOIN OF COLLECTIONS {left} CASE WHERE .{ha}.e.item.{refsub} = .{oa}._id;")
    pa, pb = _it(db, a), _it(db, b)
    nl = rng.choice([f"{verb} {pa} con {pb}", f"{verb} {pa} e {pb}", f"{verb} {pa} con {pb} corrispondenti",
                     f"{verb} i dati di {pa} e di {pb}"])
    if both:
        nl += f", espandendo prima il campo {fk}"
    else:
        nl = rng.choice([nl, f"{verb} ogni elemento di {fk} di {pa} con {pb}"])
    n = sum(1 for d in A["docs"] for it_ in d[fk] if it_[refsub] in ids_b)
    return dict(family="join_array", coll=a, nl=nl, query=q, expected=n)


def gen_other(rng, db):
    """Esempi non-join. Le collezioni derivate hanno specs vuote: le scartiamo."""
    real = {c: v for c, v in db["collections"].items() if v["specs"]}
    sub = {"name": db["name"], "collections": real}
    r = rng.choices(["filter", "array", "extra", "null", "null_setop", "group_filter", "merge"], weights=[4, 2, 4, 2, 1, 2, 2])[0]
    if r == "filter":
        return g.gen_filter_example(rng, sub)
    if r == "array":
        return g.gen_array_example(rng, sub)
    if r == "extra":
        return g.gen_extra_example(rng, sub)
    if r == "null":
        return g.gen_null_example(rng, sub)
    if r == "null_setop":
        return g.gen_setop_example(rng, sub, null_first=True)
    if r == "group_filter":
        return g.gen_group_example(rng, sub, force_cond=True)
    return g.gen_setop_example(rng, sub, force_op="MERGE")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v3-dbs", type=int, default=40)
    ap.add_argument("--eval-dbs", type=int, default=0, help="database di sola valutazione (schemi grandi, split heldout)")
    ap.add_argument("--joins-per-db", type=int, default=12)
    ap.add_argument("--others-per-db", type=int, default=10)
    ap.add_argument("--eval-joins-per-db", type=int, default=8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="out_v3")
    ap.add_argument("--backend-dir", default=os.path.join(HERE, "..", "backend", "database"))
    a = ap.parse_args()
    rng = random.Random(a.seed + 3000)
    os.makedirs(a.out, exist_ok=True)
    f_tr = open(os.path.join(a.out, "dataset_train.jsonl"), "w", encoding="utf-8")
    f_me = open(os.path.join(a.out, "dataset_meta.jsonl"), "w", encoding="utf-8")
    seen, dbs, stats, longest = set(), [], {}, 0
    total = a.v3_dbs + a.eval_dbs
    for i in range(total):
        split = "train" if i < a.v3_dbs else "heldout"
        for _ in range(50):                      # rigenera finche' lo schema entra nel limite (resta spazio per la richiesta)
            db = make_database_v3(rng, 700 + i, "en" if i % 2 == 0 else "it")
            db["schema"] = {c: g.discover(v["docs"], a.backend_dir) for c, v in db["collections"].items()}
            if len(build_tuned_prompt(db["name"], db["schema"], "y" * 110)) <= MAX_PROMPT_CHARS:
                break
        else:
            continue
        dbs.append(db)
        n_join = a.joins_per_db if split == "train" else a.eval_joins_per_db
        n_oth = a.others_per_db if split == "train" else 0
        has_arr = any(r[2] == "arr_ref" for r in db["rels"])
        has_dir = any(r[2] == "ref" for r in db["rels"])

        def emit(ex):
            nonlocal longest
            if ex is None or (db["name"], ex["nl"], ex["query"]) in seen:
                return False
            prompt = build_tuned_prompt(db["name"], db["schema"], ex["nl"])
            if len(prompt) > MAX_PROMPT_CHARS:
                stats["troppo_lungo"] = stats.get("troppo_lungo", 0) + 1
                return False
            seen.add((db["name"], ex["nl"], ex["query"]))
            longest = max(longest, len(prompt))
            ex = {k: v for k, v in ex.items()}
            meta = dict(db=db["name"], split=split, **ex)
            f_me.write(json.dumps(dict(instruction=prompt, input="", output=ex["query"], meta=meta), ensure_ascii=False) + "\n")
            if split == "train":
                f_tr.write(json.dumps(dict(instruction=prompt, input="", output=ex["query"]), ensure_ascii=False) + "\n")
            stats[ex["family"]] = stats.get(ex["family"], 0) + 1
            return True

        got = tries = 0
        while got < n_join and tries < 600 and (has_dir or has_arr):
            tries += 1
            want = "array" if (has_arr and (not has_dir or rng.random() < 0.3)) else "direct"
            got += emit(gen_join_v3(rng, db, want))
        got = tries = 0
        while got < n_oth and tries < 400:
            tries += 1
            got += emit(gen_other(rng, db))
    f_tr.close(); f_me.close()
    json.dump([{"name": d["name"], "style": d["style"], "split": "train" if k < a.v3_dbs else "heldout",
                "collections": {c: v["docs"] for c, v in d["collections"].items()}} for k, d in enumerate(dbs)],
              open(os.path.join(a.out, "databases.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("esempi per famiglia:", dict(sorted(stats.items())))
    print("prompt piu' lungo (caratteri):", longest, "| collezioni per database:",
          sorted(len(d["collections"]) for d in dbs))


if __name__ == "__main__":
    main()
