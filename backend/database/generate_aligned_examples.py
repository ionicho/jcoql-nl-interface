#!/usr/bin/env python3
"""
Genera esempi JCoQL allineati allo schema MongoDB reale
Sostituisce esempi generici con esempi basati su campi effettivi

Script one-shot: produce examples/validated/jcoql_examples_SCHEMA_ALIGNED.txt
(89 esempi: 20 hotels, 25 products, 20 users, 12 orders, 12 restaurants),
uno dei file di esempio caricati da load_examples.py nel corpus RAG di
ChromaDB. Ogni query qui sotto è scritta a mano per usare solo campi che
esistono davvero nei dataset di sample_data.py (es. .location.city per
hotels, non nomi di campo inventati) — da qui il nome "SCHEMA_ALIGNED".

quasi tutto un lungo elenco di dizionari {title, description, query} organizzati per collection.
Alla fine del file, save_examples() scrive tutto su disco nel formato 
"Titolo: / Descrizione: / Query:" letto da load_examples.py (parse_examples_file, FORMATO 2).
"""

examples = []

# ========================================
# HOTELS (20 esempi)
# ========================================
examples.extend([
    {
        "title": "Hotel a Milano",
        "description": "Hotel nella città di Milano",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Milano' KEEP OTHERS;"
    },
    {
        "title": "Hotel rating alto",
        "description": "Hotel con rating superiore a 4",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .rating > 4.0 KEEP OTHERS;"
    },
    {
        "title": "Hotel economici",
        "description": "Hotel con prezzo inferiore a 150 euro",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .price_per_night < 150 KEEP OTHERS;"
    },
    {
        "title": "Hotel Milano rating alto",
        "description": "Hotel a Milano con rating maggiore di 4",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Milano' AND .rating > 4.0 KEEP OTHERS;"
    },
    {
        "title": "Hotel con parcheggio",
        "description": "Hotel che hanno parcheggio disponibile",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .parking = true KEEP OTHERS;"
    },
    {
        "title": "Hotel 5 stelle",
        "description": "Hotel con classificazione 5 stelle",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .stars = 5 KEEP OTHERS;"
    },
    {
        "title": "Hotel con wifi",
        "description": "Hotel con connessione wifi",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .wifi = true KEEP OTHERS;"
    },
    {
        "title": "Hotel fascia media",
        "description": "Hotel con prezzo tra 100 e 200 euro",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .price_per_night IN_RANGE [100, 200] KEEP OTHERS;"
    },
    {
        "title": "Hotel Roma disponibili",
        "description": "Hotel a Roma con disponibilità",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Roma' AND .available = true KEEP OTHERS;"
    },
    {
        "title": "Hotel con colazione",
        "description": "Hotel che includono colazione",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .breakfast_included = true KEEP OTHERS;"
    },
    {
        "title": "Hotel Firenze 4 stelle",
        "description": "Hotel a Firenze con 4 stelle",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Firenze' AND .stars = 4 KEEP OTHERS;"
    },
    {
        "title": "Hotel grandi",
        "description": "Hotel con più di 100 camere",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .rooms > 100 KEEP OTHERS;"
    },
    {
        "title": "Hotel Venezia prezzo alto",
        "description": "Hotel a Venezia con prezzo maggiore di 200",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Venezia' AND .price_per_night > 200 KEEP OTHERS;"
    },
    {
        "title": "Hotel rating ottimo",
        "description": "Hotel con rating maggiore o uguale a 4.5",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .rating >= 4.5 KEEP OTHERS;"
    },
    {
        "title": "Hotel senza parcheggio",
        "description": "Hotel che non hanno parcheggio",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .parking = false KEEP OTHERS;"
    },
    {
        "title": "Hotel 3 o 4 stelle",
        "description": "Hotel con 3 o 4 stelle",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .stars = 3 OR .stars = 4 KEEP OTHERS;"
    },
    {
        "title": "Hotel Napoli economici",
        "description": "Hotel a Napoli sotto i 120 euro",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Napoli' AND .price_per_night < 120 KEEP OTHERS;"
    },
    {
        "title": "Hotel con servizi completi",
        "description": "Hotel con parcheggio e wifi",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .parking = true AND .wifi = true KEEP OTHERS;"
    },
    {
        "title": "Hotel Italia rating medio",
        "description": "Hotel in Italia con rating tra 3.5 e 4.5",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .location.country = 'Italy' AND .rating IN_RANGE [3.5, 4.5] KEEP OTHERS;"
    },
    {
        "title": "Hotel Bologna disponibili",
        "description": "Hotel disponibili a Bologna",
        "query": "GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Bologna' AND .available = true KEEP OTHERS;"
    }
])


# PRODUCTS (25 esempi)
examples.extend([
    {
        "title": "Prodotti elettronica",
        "description": "Prodotti della categoria elettronica",
        "query": "GET COLLECTION products; FILTER CASE WHERE .category = 'electronics' KEEP OTHERS;"
    },
    {
        "title": "Prodotti economici",
        "description": "Prodotti con prezzo inferiore a 100",
        "query": "GET COLLECTION products; FILTER CASE WHERE .price < 100 KEEP OTHERS;"
    },
    {
        "title": "Prodotti in sconto",
        "description": "Prodotti con sconto maggiore di 10%",
        "query": "GET COLLECTION products; FILTER CASE WHERE .discount > 10 KEEP OTHERS;"
    },
    {
        "title": "Prodotti disponibili",
        "description": "Prodotti con stock maggiore di zero",
        "query": "GET COLLECTION products; FILTER CASE WHERE .stock > 0 KEEP OTHERS;"
    },
    {
        "title": "Prodotti rating alto",
        "description": "Prodotti con rating maggiore di 4",
        "query": "GET COLLECTION products; FILTER CASE WHERE .rating > 4.0 KEEP OTHERS;"
    },
    {
        "title": "Elettronica economica",
        "description": "Prodotti elettronica sotto i 500 euro",
        "query": "GET COLLECTION products; FILTER CASE WHERE .category = 'electronics' AND .price < 500 KEEP OTHERS;"
    },
    {
        "title": "Prodotti biologici",
        "description": "Prodotti con certificazione biologica",
        "query": "GET COLLECTION products; FILTER CASE WHERE .organic = true KEEP OTHERS;"
    },
    {
        "title": "Prodotti fascia media",
        "description": "Prodotti con prezzo tra 50 e 200",
        "query": "GET COLLECTION products; FILTER CASE WHERE .price IN_RANGE [50, 200] KEEP OTHERS;"
    },
    {
        "title": "Prodotti scontati oltre 20%",
        "description": "Prodotti con sconto maggiore o uguale a 20",
        "query": "GET COLLECTION products; FILTER CASE WHERE .discount >= 20 KEEP OTHERS;"
    },
    {
        "title": "Prodotti abbigliamento",
        "description": "Prodotti categoria abbigliamento",
        "query": "GET COLLECTION products; FILTER CASE WHERE .category = 'clothing' KEEP OTHERS;"
    },
    {
        "title": "Prodotti esauriti",
        "description": "Prodotti con stock uguale a zero",
        "query": "GET COLLECTION products; FILTER CASE WHERE .stock = 0 DROP OTHERS;"
    },
    {
        "title": "Prodotti brand specifico",
        "description": "Prodotti del brand Samsung",
        "query": "GET COLLECTION products; FILTER CASE WHERE .brand = 'Samsung' KEEP OTHERS;"
    },
    {
        "title": "Prodotti con recensioni",
        "description": "Prodotti con almeno una recensione",
        "query": "GET COLLECTION products; FILTER CASE WHERE SIZE(.reviews) > 0 KEEP OTHERS;"
    },
    {
        "title": "Libri disponibili",
        "description": "Prodotti categoria libri con stock",
        "query": "GET COLLECTION products; FILTER CASE WHERE .category = 'books' AND .stock > 0 KEEP OTHERS;"
    },
    {
        "title": "Prodotti sport",
        "description": "Prodotti categoria sport",
        "query": "GET COLLECTION products; FILTER CASE WHERE .category = 'sports' KEEP OTHERS;"
    },
    {
        "title": "Prodotti costosi",
        "description": "Prodotti con prezzo maggiore di 1000",
        "query": "GET COLLECTION products; FILTER CASE WHERE .price > 1000 KEEP OTHERS;"
    },
    {
        "title": "Elettronica rating ottimo",
        "description": "Elettronica con rating maggiore di 4.5",
        "query": "GET COLLECTION products; FILTER CASE WHERE .category = 'electronics' AND .rating > 4.5 KEEP OTHERS;"
    },
    {
        "title": "Prodotti senza descrizione",
        "description": "Prodotti che mancano di descrizione",
        "query": "GET COLLECTION products; FILTER CASE WHERE WITHOUT .description KEEP OTHERS;"
    },
    {
        "title": "Food biologico",
        "description": "Prodotti food con certificazione bio",
        "query": "GET COLLECTION products; FILTER CASE WHERE .category = 'food' AND .organic = true KEEP OTHERS;"
    },
    {
        "title": "Prodotti sconto moderato",
        "description": "Prodotti con sconto tra 10 e 25%",
        "query": "GET COLLECTION products; FILTER CASE WHERE .discount IN_RANGE [10, 25] KEEP OTHERS;"
    },
    {
        "title": "Elettronica stock basso",
        "description": "Elettronica con stock minore di 10",
        "query": "GET COLLECTION products; FILTER CASE WHERE .category = 'electronics' AND .stock < 10 KEEP OTHERS;"
    },
    {
        "title": "Prodotti Apple",
        "description": "Prodotti del brand Apple",
        "query": "GET COLLECTION products; FILTER CASE WHERE .brand = 'Apple' KEEP OTHERS;"
    },
    {
        "title": "Prodotti rating medio",
        "description": "Prodotti con rating tra 3 e 4",
        "query": "GET COLLECTION products; FILTER CASE WHERE .rating IN_RANGE [3.0, 4.0] KEEP OTHERS;"
    },
    {
        "title": "Prodotti economici scontati",
        "description": "Prodotti sotto 50 euro con sconto",
        "query": "GET COLLECTION products; FILTER CASE WHERE .price < 50 AND .discount > 0 KEEP OTHERS;"
    },
    {
        "title": "Clothing rating alto",
        "description": "Abbigliamento con rating sopra 4",
        "query": "GET COLLECTION products; FILTER CASE WHERE .category = 'clothing' AND .rating > 4.0 KEEP OTHERS;"
    }
])


# USERS (20 esempi)
examples.extend([
    {
        "title": "Utenti maggiorenni",
        "description": "Utenti con età maggiore o uguale a 18",
        "query": "GET COLLECTION users; FILTER CASE WHERE .age >= 18 KEEP OTHERS;"
    },
    {
        "title": "Utenti premium",
        "description": "Utenti con account premium",
        "query": "GET COLLECTION users; FILTER CASE WHERE .premium = true KEEP OTHERS;"
    },
    {
        "title": "Utenti attivi",
        "description": "Utenti con status attivo",
        "query": "GET COLLECTION users; FILTER CASE WHERE .active = true KEEP OTHERS;"
    },
    {
        "title": "Utenti Milano",
        "description": "Utenti residenti a Milano",
        "query": "GET COLLECTION users; FILTER CASE WHERE .city = 'Milano' KEEP OTHERS;"
    },
    {
        "title": "Utenti email verificata",
        "description": "Utenti con email verificata",
        "query": "GET COLLECTION users; FILTER CASE WHERE .email_verified = true KEEP OTHERS;"
    },
    {
        "title": "Utenti giovani",
        "description": "Utenti con età inferiore a 30",
        "query": "GET COLLECTION users; FILTER CASE WHERE .age < 30 KEEP OTHERS;"
    },
    {
        "title": "Utenti premium attivi",
        "description": "Utenti premium e attivi",
        "query": "GET COLLECTION users; FILTER CASE WHERE .premium = true AND .active = true KEEP OTHERS;"
    },
    {
        "title": "Utenti senza email",
        "description": "Utenti che non hanno email registrata",
        "query": "GET COLLECTION users; FILTER CASE WHERE WITHOUT .email KEEP OTHERS;"
    },
    {
        "title": "Utenti Roma o Milano",
        "description": "Utenti da Roma o Milano",
        "query": "GET COLLECTION users; FILTER CASE WHERE .city = 'Roma' OR .city = 'Milano' KEEP OTHERS;"
    },
    {
        "title": "Utenti con ordini",
        "description": "Utenti con almeno un ordine",
        "query": "GET COLLECTION users; FILTER CASE WHERE SIZE(.orders) > 0 KEEP OTHERS;"
    },
    {
        "title": "Utenti adulti",
        "description": "Utenti con età maggiore di 30",
        "query": "GET COLLECTION users; FILTER CASE WHERE .age > 30 KEEP OTHERS;"
    },
    {
        "title": "Utenti fascia età",
        "description": "Utenti con età tra 25 e 45",
        "query": "GET COLLECTION users; FILTER CASE WHERE .age IN_RANGE [25, 45] KEEP OTHERS;"
    },
    {
        "title": "Utenti senza telefono",
        "description": "Utenti senza numero telefono",
        "query": "GET COLLECTION users; FILTER CASE WHERE WITHOUT .phone KEEP OTHERS;"
    },
    {
        "title": "Utenti Firenze premium",
        "description": "Utenti premium di Firenze",
        "query": "GET COLLECTION users; FILTER CASE WHERE .city = 'Firenze' AND .premium = true KEEP OTHERS;"
    },
    {
        "title": "Utenti molti ordini",
        "description": "Utenti con più di 5 ordini",
        "query": "GET COLLECTION users; FILTER CASE WHERE SIZE(.orders) > 5 KEEP OTHERS;"
    },
    {
        "title": "Utenti inattivi",
        "description": "Utenti non attivi",
        "query": "GET COLLECTION users; FILTER CASE WHERE .active = false DROP OTHERS;"
    },
    {
        "title": "Utenti Italia",
        "description": "Utenti del paese Italia",
        "query": "GET COLLECTION users; FILTER CASE WHERE .country = 'Italy' KEEP OTHERS;"
    },
    {
        "title": "Utenti senior",
        "description": "Utenti con età maggiore o uguale a 60",
        "query": "GET COLLECTION users; FILTER CASE WHERE .age >= 60 KEEP OTHERS;"
    },
    {
        "title": "Utenti email o telefono",
        "description": "Utenti con email o telefono presente",
        "query": "GET COLLECTION users; FILTER CASE WHERE .email IS NOT NULL OR .phone IS NOT NULL KEEP OTHERS;"
    },
    {
        "title": "Utenti Napoli attivi",
        "description": "Utenti attivi di Napoli",
        "query": "GET COLLECTION users; FILTER CASE WHERE .city = 'Napoli' AND .active = true KEEP OTHERS;"
    }
])


# ORDERS (12 esempi)
examples.extend([
    {
        "title": "Ordini spediti",
        "description": "Ordini con status spedito",
        "query": "GET COLLECTION orders; FILTER CASE WHERE .status = 'shipped' KEEP OTHERS;"
    },
    {
        "title": "Ordini costosi",
        "description": "Ordini con totale maggiore di 500",
        "query": "GET COLLECTION orders; FILTER CASE WHERE .total > 500 KEEP OTHERS;"
    },
    {
        "title": "Ordini confermati",
        "description": "Ordini con status confermato",
        "query": "GET COLLECTION orders; FILTER CASE WHERE .status = 'confirmed' KEEP OTHERS;"
    },
    {
        "title": "Ordini urgenti",
        "description": "Ordini con priorità urgente",
        "query": "GET COLLECTION orders; FILTER CASE WHERE .priority = 'urgent' KEEP OTHERS;"
    },
    {
        "title": "Ordini senza tracking",
        "description": "Ordini senza numero tracking",
        "query": "GET COLLECTION orders; FILTER CASE WHERE WITHOUT .tracking_number KEEP OTHERS;"
    },
    {
        "title": "Ordini fascia media",
        "description": "Ordini con totale tra 100 e 300",
        "query": "GET COLLECTION orders; FILTER CASE WHERE .total IN_RANGE [100, 300] KEEP OTHERS;"
    },
    {
        "title": "Ordini consegnati",
        "description": "Ordini con status consegnato",
        "query": "GET COLLECTION orders; FILTER CASE WHERE .status = 'delivered' KEEP OTHERS;"
    },
    {
        "title": "Ordini alta priorità",
        "description": "Ordini con priorità alta o urgente",
        "query": "GET COLLECTION orders; FILTER CASE WHERE .priority = 'high' OR .priority = 'urgent' KEEP OTHERS;"
    },
    {
        "title": "Ordini economici",
        "description": "Ordini con totale inferiore a 100",
        "query": "GET COLLECTION orders; FILTER CASE WHERE .total < 100 KEEP OTHERS;"
    },
    {
        "title": "Ordini pending",
        "description": "Ordini in attesa",
        "query": "GET COLLECTION orders; FILTER CASE WHERE .status = 'pending' KEEP OTHERS;"
    },
    {
        "title": "Ordini molti item",
        "description": "Ordini con più di 3 articoli",
        "query": "GET COLLECTION orders; FILTER CASE WHERE SIZE(.items) > 3 KEEP OTHERS;"
    },
    {
        "title": "Ordini cancelled",
        "description": "Ordini cancellati",
        "query": "GET COLLECTION orders; FILTER CASE WHERE .status = 'cancelled' DROP OTHERS;"
    }
])


# RESTAURANTS (12 esempi)
examples.extend([
    {
        "title": "Ristoranti Roma",
        "description": "Ristoranti nella città di Roma",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .city = 'Roma' KEEP OTHERS;"
    },
    {
        "title": "Ristoranti rating alto",
        "description": "Ristoranti con rating maggiore di 4",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .rating > 4.0 KEEP OTHERS;"
    },
    {
        "title": "Ristoranti aperti",
        "description": "Ristoranti con status aperto",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .status = 'open' KEEP OTHERS;"
    },
    {
        "title": "Ristoranti italiani",
        "description": "Ristoranti con cucina italiana",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .cuisine = 'Italian' KEEP OTHERS;"
    },
    {
        "title": "Ristoranti con terrazza",
        "description": "Ristoranti con posti esterni",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .outdoor_seating = true KEEP OTHERS;"
    },
    {
        "title": "Ristoranti gluten free",
        "description": "Ristoranti con menu senza glutine",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .gluten_free_menu = true KEEP OTHERS;"
    },
    {
        "title": "Ristoranti Milano rating",
        "description": "Ristoranti a Milano con rating sopra 4",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .city = 'Milano' AND .rating > 4.0 KEEP OTHERS;"
    },
    {
        "title": "Ristoranti economici",
        "description": "Ristoranti fascia prezzo bassa",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .price_range = '$' KEEP OTHERS;"
    },
    {
        "title": "Ristoranti giapponesi",
        "description": "Ristoranti cucina giapponese",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .cuisine = 'Japanese' KEEP OTHERS;"
    },
    {
        "title": "Ristoranti lusso",
        "description": "Ristoranti fascia prezzo alta",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .price_range = '$$$$' KEEP OTHERS;"
    },
    {
        "title": "Ristoranti Firenze aperti",
        "description": "Ristoranti aperti a Firenze",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .city = 'Firenze' AND .status = 'open' KEEP OTHERS;"
    },
    {
        "title": "Ristoranti rating ottimo",
        "description": "Ristoranti con rating maggiore o uguale a 4.5",
        "query": "GET COLLECTION restaurants; FILTER CASE WHERE .rating >= 4.5 KEEP OTHERS;"
    }
])


# SALVA FILE
def save_examples(filename):
    with open(filename, 'w', encoding='utf-8') as f:
        for i, ex in enumerate(examples, 1):
            f.write(f"Titolo: {ex['title']}\n")
            f.write(f"Descrizione: {ex['description']}\n")
            f.write(f"Query: {ex['query']}\n")
            f.write("\n")
    
    print(f"✅ Salvati {len(examples)} esempi in: {filename}")

save_examples("examples/validated/jcoql_examples_SCHEMA_ALIGNED.txt")

print(f"\n📊 BREAKDOWN:")
print(f"   Hotels: 20")
print(f"   Products: 25")
print(f"   Users: 20")
print(f"   Orders: 12")
print(f"   Restaurants: 12")
print(f"   ──────────────")
print(f"   TOTALE: {len(examples)} esempi")