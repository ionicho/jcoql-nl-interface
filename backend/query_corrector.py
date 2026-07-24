"""
Query Corrector - Corregge errori comuni di sintassi JCoQL

Questo modulo fix automaticamente errori comuni che il LLM genera,
come "IS NOT NULL" invece di "ISNOTNULL".
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
    # Cerca pattern come "WHERE .fieldname IS NOT NULL"
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
    # Cerca pattern come "FIELD .fieldname IS NOT NULL"
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
    
    # Se la query è un messaggio di errore (non JCoQL), non correggerla
    # Il LLM a volte genera messaggi descrittivi invece di query
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