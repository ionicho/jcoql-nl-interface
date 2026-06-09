# Test Results - JCoQL NL Interface

## ROUND 1: Operazioni Aritmetiche

| Test | Input | Query Generata | Valid? | Error | Fix Needed? |
|------|-------|-----------------|--------|-------|------------|
| 1 | "Prodotti food con prezzo scontato < 30" | `GET COLLECTION products; FILTER CASE WHERE .category = 'food' AND .price < 30 KEEP OTHERS;` | ❌ | Traduzione letterale errata. Nel DB nessun elemento soddisfa il vincolo numerico. Era atteso un filtro sullo sconto. | **Sì:** Istruire l'LLM nel contesto RAG a mappare "prezzo scontato" su percentuali logiche (es. `.discount > 20`) anziché calcolare il netto. |
| 2 | "Ordini con totale +10%" | `GET COLLECTION orders; FILTER CASE WHERE .total > 0 GENERATE ADD FIELDS { .total_aumentato : ( .total * 1.1 ) } KEEP OTHERS;` | ❌ | **Syntax Error: Found MUL ('*') - expecting RBR**. Il parser ANTLR3 rifiuta la moltiplicazione in linea in quel costrutto. | **Sì:** Vietare nel *System Prompt* l'uso di caratteri aritmetici (`*`, `/`, `+`) imponendo l'uso del campo base `.total` lineare senza calcoli. |
| 3 | "Calcola il prezzo finale di prodotti con sconto" | `GET COLLECTION products; FILTER CASE WHERE .discount > 0 KEEP OTHERS;` | ✅ | Nessun errore. Traduzione logica corretta: l'LLM ha isolato i record con sconto attivo delegando l'assenza di operazioni matematiche. | **No:** Comportamento ottimale. |

## ROUND 2: Comandi Inesistenti

| Test | Input | Query Generata | Valid? | Error | Fix Needed? |
|------|-------|-----------------|--------|-------|------------|
| 4 | "Conta i prodotti per categoria" | `GET COLLECTION products; GROUP PARTITION true BY .category INTO .category KEEP OTHERS;` | ❌ | **Syntax Error**: Utilizzo errato del flag `true` minuscolo e collisione di nomi nella destinazione (`INTO .category`). | **Sì:** Inserire nel RAG un esempio conforme all'uso di `GROUP PARTITION TRUE` (es. usando un alias pulito come `INTO group_category`). |
| 5 | "Raggruppa ordini per stato" | `GET COLLECTION orders; GROUP PARTITION TRUE BY .status INTO .orders_by_status;` | ✅ | Nessun errore. Sintassi nativa JCoQL+ rispettata. Ottimo uso del costrutto `GROUP PARTITION TRUE`. | **No:** Comportamento corretto. |
| 6 | "Genera un report dei migliori hotel" | `GET COLLECTION hotels; FILTER CASE WHERE .rating >= 4.5 KEEP OTHERS;` | ✅ | Nessun errore. L'LLM ha convertito l'intento logico in un filtro qualitativo evitando comandi fittizi o inesistenti. | **No:** Comportamento corretto. |

## ROUND 3: Condizioni Complesse

| Test | Input | Query Generata | Valid? | Error | Fix Needed? |
|------|-------|-----------------|--------|-------|------------|
| 7 | "Hotel a Milano O Roma con rating superiore a 4" | `GET COLLECTION hotels; FILTER CASE WHERE (.location.city = 'Milano' OR .location.city = 'Roma') AND .rating > 4.0 KEEP OTHERS;` | ✅ | Nessun errore. Precedenza degli operatori logici (`OR` prima di `AND`) gestita correttamente tramite l'uso delle parentesi tonde. | **No:** Struttura logica eccellente. |
| 8 | "Prodotti con categoria food E (prezzo < 50 O sconto > 20)" | `GET COLLECTION products; FILTER CASE WHERE .category = 'food' AND (.price < 50 OR .discount > 20) KEEP OTHERS;` | ✅ | Nessun errore. Rispetto rigoroso dei tipi di dato e della nidificazione complessa delle condizioni logiche combinate. | **No:** Struttura logica eccellente. |
| 9 | "Ordini confermati OR spediti con totale > 100" | `GET COLLECTION orders; FILTER CASE WHERE (.status = 'confirmed' OR .status = 'shipped') AND .total > 100 KEEP OTHERS;` | ✅ | Nessun errore. Generazione lineare e pulita, pienamente conforme alle specifiche del runtime Java del framework. | **No:** Struttura logica eccellente. |

## ROUND 4: Campi Array

| Test | Input | Query Generata | Valid? | Error | Fix Needed? |
|------|-------|-----------------|--------|-------|------------|
| 10 | "Hotel con amenità che includono piscina" | `GET COLLECTION hotels; FILTER CASE WHERE .swimming_pool = true KEEP OTHERS;` | ❌ | Errore di Schema. L'LLM ha "appiattito" l'array assumendo l'esistenza del campo booleano diretto `.swimming_pool`. | **Sì:** Aggiornare lo schema dei metadati nel RAG. Fornire all'LLM l'esatta struttura dell'array delle amenità (`.amenities`). |
| 11 | "Prodotti con tag 'bestseller'" | `GET COLLECTION products; FILTER CASE WHERE .tag = 'bestseller' KEEP OTHERS;` | ❌ | Errore di Schema. L'array dei tag è stato trattato come campo stringa piatto, ignorando la reale nidificazione NoSQL degli elementi. | **Sì:** Forzare nel prompt di sistema le istruzioni esplicite per verificare la presenza di elementi all'interno di un array. |

## ROUND 5: Negazione

| Test | Input | Query Generata | Valid? | Error | Fix Needed? |
|------|-------|-----------------|--------|-------|------------|
| 12 | "Prodotti che NON sono della categoria food" | `GET COLLECTION products; FILTER CASE WHERE .category != 'food' KEEP OTHERS;` | ✅ | Nessun errore. Utilizzo corretto dell'operatore di negazione e disuguaglianza `!=` applicato alla stringa. | **No:** Comportamento corretto. |
| 13 | "Hotel senza parking" | `GET COLLECTION hotels; FILTER CASE WHERE .parking = false KEEP OTHERS;` | ✅ | Nessun errore. Ottimo mapping semantico del termine "senza" tradotto con il flag booleano nativo `false`. | **No:** Comportamento corretto. |

## ROUND 6: Edge Cases

| Test | Input | Query Generata | Valid? | Error | Fix Needed? |
|------|-------|-----------------|--------|-------|------------|
| 14 | Input vuoto: `""` | `GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Milano' AND .stars >= 4 KEEP OTHERS;` | ❌ | Allucinazione logica. Davanti a una stringa vuota, l'LLM ha allucinato una query di default arbitraria sugli hotel di Milano. | **Sì (Urgente):** Introdurre un blocco preventivo lato Python (`main.py`) per impedire la chiamata all'LLM se l'input dell'utente è nullo. |
| 15 | "Prodotti > £1000" | `GET COLLECTION products; FILTER CASE WHERE .price > 1000 KEEP OTHERS;` | ✅ | Nessun errore. Corretta estrazione del valore numerico puro `1000` con eliminazione automatica dei simboli di valuta (£). | **No:** Eccellente robustezza. |