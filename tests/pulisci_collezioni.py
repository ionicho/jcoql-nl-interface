import sys
from pymongo import MongoClient

BASE = {"products", "orders", "users", "category_translations"}
db = MongoClient("mongodb://localhost:27017")["jcoql_test"]

extra = sorted(c for c in db.list_collection_names() if c not in BASE and not c.startswith("system."))
missing = sorted(BASE - set(db.list_collection_names()))

print("Da eliminare:", extra or "nessuna")
if missing:
    print("ATTENZIONE, collezioni di base mancanti:", missing)

if "--drop" in sys.argv:
    for c in extra:
        db.drop_collection(c)
    print("Eliminate", len(extra), "collezioni.")
    print("Rimaste:", sorted(db.list_collection_names()))
else:
    print("Prova a vuoto: aggiungi --drop per eliminare davvero.")
