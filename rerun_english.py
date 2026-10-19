"""
rerun_english.py - le stesse 78 richieste di rerun_extended.py, scritte in INGLESE.
L'atteso (oracolo) resta quello delle richieste italiane: ogni richiesta inglese e' mappata alla sua
corrispondente italiana (EN2IT). Cosi' il confronto italiano/inglese e' pulito: stessi dati, stesso oracolo.

Richiede nella stessa cartella: rerun_extended.py, rerun_rounds.py, extended_tests.py, repeatability.py, verify_execution.py.
Output: extended_runs_en.csv, extended_riepilogo_en.csv (i file italiani non vengono toccati).

ATTENZIONE: ogni chiamata a /api/generate scrive anche in test_campaign_log.csv:
    copy test_campaign_log.csv test_campaign_log_prima_inglese.csv

Uso (backend avviato su localhost:8000), stessi argomenti di rerun_extended.py:
    .\\venv\\Scripts\\python.exe .\\rerun_english.py --selftest
    .\\venv\\Scripts\\python.exe .\\rerun_english.py --models gemini
    .\\venv\\Scripts\\python.exe .\\rerun_english.py --models gemma4 llama llama32 --modes compact
    .\\venv\\Scripts\\python.exe .\\rerun_english.py --models llama --modes tuned
"""
import sys
import verify_execution as V
import rerun_rounds as RR
import extended_tests as X
import rerun_extended as RE

EN = {
"R1": [
 "Show me all the users",
 "Show me the products with a discount greater than 20%",
 "Show me the organic products with a rating of at least 4",
 "Show me the organic products or the ones with a discount above 30%",
 "Expand the reviews of the products into separate rows",
 "Link each order to the user who placed it",
 "Group the products by category",
 "Merge the organic products and the discounted ones into a single collection, without duplicates"],
"R2": [
 "Show me the products that are not organic",
 "Show me the organic products with a rating of at least 4, or the ones with a discount above 50%",
 "Show me the orders above 100 euros together with the user who placed them",
 "Show me the reviews of the products with a rating above 4",
 "Count how many products there are for each category"],
"R3": [
 "Show me the products with a rating between 3 and 4.5",
 "Show me the products with a discount between 10% and 30%",
 "Show me the products with no discount",
 "Show me the products with a rating below 3",
 "Show me the organic products with a discount greater than 20%",
 "Show me the non-organic products with a rating of at least 4",
 "Show me the products that are not organic and have no discount",
 "Show me the organic products or the ones with a rating of at least 4.5",
 "Show me the products with a discount above 40%, or with a rating below 2",
 "Show me the organic products with a discount above 10%, or the ones with a rating of at least 4.5",
 "Show me the non-organic products or the ones with a discount above 50%",
 "Show me the reviews of the products with a rating equal to 5",
 "Show me the reviews of the products with a rating below 3",
 "Show me the reviews of the organic products only",
 "Expand the items of the orders into separate rows",
 "Link each review to the user who wrote it",
 "Show me the orders below 50 euros together with the user who placed them",
 "Link each order to the products purchased",
 "Link each user to their orders",
 "Group the orders by user",
 "Group the organic products by category",
 "Group the products into organic and non-organic",
 "Merge the products with a rating of at least 4 and the ones with a discount above 30% into a single collection, without duplicates",
 "Merge the organic products and the ones with no discount into a single collection, keeping the duplicates",
 "Merge the orders above 100 euros and the ones below 20 euros into a single collection",
 "Add to each order a field with the total increased by 22% VAT",
 "Add to each product a field with the difference between 5 and the rating",
 "Show me only the category and the rating of each product"],
"F": [
 "Show me the products in the food category",
 "Show me the products with a price above 1000 euros",
 "Show me the products with a price below 300 euros",
 "Show me the products in the electronics category with a discount of at least 15%",
 "Show me the products in the books or sports category",
 "Show me the products that are not in the food category",
 "Show me the products with more than 50 pieces in stock",
 "Show me the products with a price between 200 and 700 euros",
 "Show me the premium users",
 "Show me the users older than 40",
 "Show me the users who live in Torino",
 "Show me the active users with a verified email",
 "Show me the users who are not premium",
 "Show me the orders with status confirmed",
 "Show me the orders with priority urgent",
 "Show me the orders without a tracking number",
 "Show me the orders with a total above 500 euros",
 "Show me the orders that have not been cancelled",
 "Show me the orders with a total between 200 and 600 euros",
 "Group the users by city",
 "Group the orders by status",
 "Show me only the name and the price of each product"],
"D": [
 "Show me the reviews with a rating equal to 5 of the organic products only",
 "Show me the orders above 500 euros together with the user who placed them, only for premium users",
 "Link each order to the user who placed it and to the products purchased",
 "Show me the reviews written by premium users",
 "Group the reviews by rating",
 "Group by category the products with a discount greater than 10%",
 "Group the orders by the city of the user who placed them",
 "Show me the products that are both organic and have a rating of at least 4, using the intersection",
 "Show me the products with a rating of at least 4 excluding the organic ones, using the set difference",
 "Merge the food, electronics and books products into a single collection, without duplicates",
 "Show me the products that are organic or have a discount above 20%, and that also have a rating of at least 4",
 "Translate the category of each product using the category dictionary",
 "Show me the orders with an assigned tracking number and a total above 300 euros",
 "Show me the reviews with a rating equal to 3 together with the user who wrote them",
 "Show me the reviews with a rating of at least 4 of the products with a discount above 10%"],
}
# stessa struttura di rerun_extended.GROUPS (R1 R2 R3 F D), nello stesso ordine
IT_GROUPS = [(n, qs) for n, qs in RE.GROUPS]
EN2IT = {}
for name, qs in IT_GROUPS:
    assert len(qs) == len(EN[name]), f"{name}: {len(qs)} italiane contro {len(EN[name])} inglesi"
    for it, en in zip(qs, EN[name]):
        EN2IT[en] = it

def install():
    orig = V.expected
    def exp(nl, C):
        it = EN2IT.get(nl, nl)
        return X.expected_new(it, C) if it in X.NEW_ALL else orig(it, C)
    V.expected = exp

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        install()
        import json
        base = "backend/database"
        C = V.load_collections_seed(base)
        C["category_translations"] = json.load(open(f"{base}/data_category_translations.json", encoding="utf-8"))
        bad = 0
        for name, qs in EN.items():
            for q in qs:
                e = V.expected(q, C)
                if not e: bad += 1
                print(name, "atteso", e["n"] if e else "MANCA", "|", q)
        print("\nrichieste:", len(EN2IT), "| senza atteso:", bad); sys.exit(0)
    install()
    RE.GROUPS[:] = [(n, EN[n]) for n, _ in IT_GROUPS]
    RE.OUT, RE.OUT_SUM = "extended_runs_en.csv", "extended_riepilogo_en.csv"
    RE.X.install = lambda: None      # l'install di rerun_extended wrapperebbe di nuovo: non serve, gia' fatto
    RE.main()
