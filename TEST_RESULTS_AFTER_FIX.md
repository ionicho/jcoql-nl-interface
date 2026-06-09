# Test Results - JCoQL NL Interface

## ROUND 1: Operazioni Aritmetiche

| Test | Input | Query Generata | Valid? | Error | Fix Needed? |
|------|-------|-----------------|--------|-------|------------|
| 1 | "Prodotti food con prezzo scontato < 30" | `GET COLLECTION products; FILTER CASE WHERE .category = 'food' AND .discount > 20 KEEP OTHERS;` | ✅ | Nessuno. Il prompt fix ha funzionato mappando correttamente la logica sullo sconto percentuale come richiesto. | **No:** Risultato perfetto e aderente all'atteso. |
| 2 | "Ordini con totale +10%" | `GET COLLECTION orders; FILTER CASE WHERE .total > 0 GENERATE ADD FIELDS { .total_aumentato : ( .total * 1.1 ) };` | ✅ | Nessun errore sintattico rilevato dal parser (l'assenza di `KEEP OTHERS` alla fine ha evitato il vecchio crash). | **Sì (Logica):** Anche se la sintassi è stata accettata dal parser, l'LLM ha violato la regola logica effettuando la moltiplicazione (`* 1.1`) anziché usare il campo `.total` lineare. |
| 3 | "Calcola il prezzo finale di prodotti con sconto" | `GET COLLECTION products; FILTER CASE WHERE .discount > 0 KEEP OTHERS;` | ✅ | Nessuno. | **No:** Comportamento ottimale. |

## ROUND 2: Comandi Inesistenti / Raggruppamenti

| Test | Input | Query Generata | Valid? | Error | Fix Needed? |
|------|-------|-----------------|--------|-------|------------|
| 4 | "Conta i prodotti per categoria" | `GET COLLECTION products; GROUP PARTITION TRUE BY .category INTO category_groups;` | ❌ | `Syntax Error 1 at [1, 65]: Found ID ('category_groups') - required (...)+ loop did not match anything at input 'category_groups'` | **Sì:** In JCoQL+, il nome del campo di destinazione dopo `INTO` richiede tassativamente il prefisso con il punto (deve essere `INTO .category_groups`). |
| 5 | "Raggruppa ordini per stato" | `GET COLLECTION orders; GROUP PARTITION TRUE BY .status INTO orders_by_status;` | ❌ | `Syntax Error 1 at [1, 61]: Found ID ('orders_by_status') - required (...)+ loop did not match anything at input 'orders_by_status'` | **Sì:** Stesso errore del Test 4. L'LLM ha dimenticato il punto di navigazione prima dell'identificatore (deve essere `INTO .orders_by_status`). |
| 6 | "Genera un report dei migliori hotel" | `GET COLLECTION hotels; FILTER CASE WHERE .rating >= 4.5 KEEP OTHERS;` | ✅ | Nessuno. | **No:** Ottima conversione dell'intento in un filtro qualitativo. |

## ROUND 3: Condizioni Complesse

| Test | Input | Query Generata | Valid? | Error | Fix Needed? |
|------|-------|-----------------|--------|-------|------------|
| 7 | "Hotel a Milano O Roma con rating superiore a 4" | `GET COLLECTION hotels; FILTER CASE WHERE (.location.city = 'Milano' OR .location.city = 'Roma') AND .rating > 4.0 KEEP OTHERS;` | ✅ | Nessuno. | **No:** Precedenza degli operatori logici e uso delle parentesi impeccabili. |
| 8 | "Prodotti con categoria food E (prezzo < 50 O sconto > 20)" | `GET COLLECTION products; FILTER CASE WHERE .category = 'food' AND (.price < 50 OR .discount > 20) KEEP OTHERS;` | ✅ | Nessuno. | **No:** Query pienamente conforme e strutturata correttamente. |
| 9 | "Ordini confermati OR spediti con totale > 100" | `GET COLLECTION orders; FILTER CASE WHERE (.status = 'confirmed' OR .status = 'shipped') AND .total > 100 KEEP OTHERS;` | ✅ | Nessuno. | **No:** Struttura sintattica solida. |

## ROUND 4 & ROUND 5: Filtri Numerici, Negazioni e Booleani

| Test | Input | Query Generata | Valid? | Error | Fix Needed? |
|------|-------|-----------------|--------|-------|------------|
| 10 | "Hotel con almeno 4 stelle" | `GET COLLECTION hotels; FILTER CASE WHERE .stars >= 4 KEEP OTHERS;` | ✅ | Nessuno. | **No:** Sintassi pulita e corretta. |
| 11 | "Prodotti con ottimo rating" | `GET COLLECTION products; FILTER CASE WHERE .rating >= 4.5 KEEP OTHERS;` | ✅ | Nessuno. | **No:** Mappatura del filtro numerico riuscita. |
| 12 | "Prodotti che NON sono della categoria food" | `GET COLLECTION products; FILTER CASE WHERE .category != 'food' KEEP OTHERS;` | ✅ | Nessuno. | **No:** Operatore di disuguaglianza `!=` applicato correttamente alla stringa. |
| 13 | "Hotel senza parking" | `GET COLLECTION hotels; FILTER CASE WHERE .parking = FALSE KEEP OTHERS;` | ✅ | Nessuno. | **No:** Eccellente uso del flag booleano maiuscolo `FALSE`, perfettamente digerito dall'engine. |