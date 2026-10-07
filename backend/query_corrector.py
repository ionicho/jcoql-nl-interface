"""
Query Corrector - Corregge errori comuni di sintassi JCoQL

Questo modulo fix automaticamente errori comuni che il LLM genera,
come "ISNOTNULL" (senza spazi) invece di "IS NOT NULL", o la parola chiave FIELD mancante.

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
    Normalizza la sintassi dei test di nullità secondo il lexer ufficiale.

    FIX 07/10/2026: il lexer JCoQL+ definisce i token come
        ISNULL    : 'IS' WS 'NULL'
        ISNOTNULL : 'IS' WS 'NOT' WS 'NULL'
    cioè SCRITTI CON GLI SPAZI ("IS NULL", "IS NOT NULL"). Verificato dal
    vivo con /api/execute: "FIELD .campo IS NOT NULL" e "IS NULL" vengono
    eseguiti correttamente, mentre "ISNOTNULL" / "ISNULL" (senza spazi)
    sono rifiutati con "Syntax Error ... Found ID ('ISNOTNULL')".
    La versione precedente di questa funzione faceva l'esatto contrario
    (convertiva "IS NOT NULL" in "ISNOTNULL") e rompeva query giuste.

    Correzioni applicate:
    1. "ISNOTNULL" / "ISNULL" senza spazi  -> "IS NOT NULL" / "IS NULL"
    2. ".campo IS [NOT] NULL" senza FIELD   -> "FIELD .campo IS [NOT] NULL"
       (la parola chiave FIELD è obbligatoria prima del riferimento al campo)

    Returns:
        (query_corretta, is_modified)
    """
    original = query

    # 1) forme senza spazi -> forme con spazi (prima ISNOTNULL, poi ISNULL)
    query = re.sub(r'\bISNOTNULL\b', 'IS NOT NULL', query)
    query = re.sub(r'\bISNULL\b', 'IS NULL', query)

    # 2) FIELD mancante: ".campo IS [NOT] NULL" non preceduto da FIELD
    def _add_field(m):
        return f"{m.group(1)}FIELD {m.group(2)} {m.group(3)}"
    query = re.sub(
        r'(?<!FIELD )(\bWHERE\s+|\bAND\s+|\bOR\s+|\bNOT\s+|\(\s*)(\.[\w.]+)\s+(IS\s+(?:NOT\s+)?NULL)\b',
        _add_field, query)

    modified = query != original
    if modified:
        corrector_logger.info("Correzione IS NULL / IS NOT NULL applicata")
        corrector_logger.debug(f"Query PRIMA:  {original}")
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