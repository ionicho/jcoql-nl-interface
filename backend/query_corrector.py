"""
Query Corrector - Corregge errori comuni di sintassi JCoQL

Questo modulo fix automaticamente errori comuni che il LLM genera,
come "IS NOT NULL" invece di "ISNOTNULL".

STATO ATTUALE:
nonostante il nome e il docstring parlino di "errori comuni" al plurale,
oggi è implementato UN solo correttore (ISNOTNULL, sotto). L'architettura
è però pensata per essere estesa: correct_query() applica in sequenza
"tutti i corrector" registrati — se in futuro l'LLM genera altri errori
sistematici (es. un altro operatore scritto con spazi quando il parser
vuole una parola unica), il pattern da seguire è:
  1. scrivere una nuova funzione correct_<nome>_syntax(query) -> (str, bool)
     sul modello di correct_isnotnull_syntax qui sotto
  2. richiamarla dentro correct_query(), aggiungendo una entry alla
     lista `corrections` se ha modificato qualcosa
Così il chiamante (main.py) continua a ricevere una singola lista di
correzioni applicate, senza dover sapere quanti/quali correttori esistono.
"""
import logging
import re

# Logger per il corrector
corrector_logger = logging.getLogger('query_corrector')


def correct_isnotnull_syntax(query: str) -> tuple[str, bool]:
    """
    Corregge la sintassi di ISNOTNULL.
    
    Il LLM a volte genera "IS NOT NULL" (con spazi) quando il parser
    richiede "ISNOTNULL" (senza spazi).
    
    Esempi:
    ❌ BEFORE: WHERE .field IS NOT NULL KEEP
    ✅ AFTER:  WHERE FIELD .field ISNOTNULL KEEP
    
    Args:
        query: Query JCoQL potenzialmente errata
    
    Returns:
        (query_corretta, is_modified) - query corretta e flag se è stata modificata
    """
    # Flag per tracciare se la query è stata modificata
    modified = False
    original_query = query
    
    # Pattern 1: ".field IS NOT NULL" → "FIELD .field ISNOTNULL"
    # Caso in cui l'LLM ha OMESSO del tutto la keyword "FIELD" richiesta
    # dalla grammatica JCoQL+ (genera "WHERE .campo IS NOT NULL" invece
    # di "WHERE FIELD .campo ISNOTNULL") — qui la aggiungiamo noi.
    pattern1 = r'WHERE\s+(\.\w+)\s+IS\s+NOT\s+NULL'
    if re.search(pattern1, query):
        corrector_logger.info(f"Correzione 1: Converto '.field IS NOT NULL' → 'FIELD .field ISNOTNULL'")
        query = re.sub(
            pattern1,
            lambda m: f"WHERE FIELD {m.group(1)} ISNOTNULL",
            query
        )
        modified = True
    
    # Pattern 2: "IS NOT NULL" nel contesto FIELD → "ISNOTNULL"
    # Caso diverso dal precedente: qui la keyword "FIELD" c'è già (l'LLM
    # l'ha generata correttamente), sbaglia solo la spaziatura di
    # ISNOTNULL. Applicato DOPO il pattern 1: a quel punto, se il
    # pattern 1 ha già agito, la query non contiene più il testo
    # "IS NOT NULL" (l'ha già trasformato in ISNOTNULL) — i due
    # pattern intercettano due varianti di errore diverse e non si
    # sovrappongono mai sullo stesso frammento di testo.
    pattern2 = r'FIELD\s+(\.\w+)\s+IS\s+NOT\s+NULL'
    if re.search(pattern2, query):
        corrector_logger.info(f"Correzione 2: Converto 'FIELD .field IS NOT NULL' → 'FIELD .field ISNOTNULL'")
        query = re.sub(
            pattern2,
            lambda m: f"FIELD {m.group(1)} ISNOTNULL",
            query
        )
        modified = True
    
    # Log se la query è stata modificata
    if modified:
        corrector_logger.debug(f"Query PRIMA:  {original_query}")
        corrector_logger.debug(f"Query DOPO:   {query}")
    
    return query, modified


def correct_query(query: str) -> tuple[str, list]:
    """
    Applica TUTTI i corrector alla query.
    
    Questo è il punto di ingresso principale per correggere errori comuni.
    
    Args:
        query: Query JCoQL potenzialmente errata
    
    Returns:
        (query_corretta, lista_correzioni) - query corretta e lista delle correzioni applicate
    """
    # Se la query è None o vuota, ritorna come è
    # Questo succede quando il LLM fallisce a generare una query valida
    if not query or query is None:
        corrector_logger.warning("Query None o vuota - nessuna correzione applicata")
        return query, []
    
    # Se la query è un messaggio di errore (non JCoQL), non è da correggere
    # Il LLM a volte genera messaggi descrittivi invece di query
    # NOTA: il prefisso "QUERY:" è controllato anche a monte, in main.py
    # (prima ancora di chiamare correct_query) — qui è un controllo
    # ridondante/difensivo, utile se in futuro correct_query() viene
    # richiamata da un altro punto del codice che non fa già quel check.
    if query.startswith("QUERY:") or query.startswith("Operazione"):
        corrector_logger.info("Query è un messaggio del sistema - nessuna correzione")
        return query, []
    
    # Lista delle correzioni applicate
    corrections = []
    
    # Applica correctore ISNOTNULL
    query, is_modified = correct_isnotnull_syntax(query)
    if is_modified:
        corrections.append("ISNOTNULL syntax corrected")
    
    return query, corrections