"""
Test Campaign Logger (AGGIUNTO 03/10/2026) - registra ogni generazione
NL->JCoQL su un file CSV per la campagna di test multi-modello (vedi
jcoql-prossimi-passi.md): validità, numero di tentativi e tempo di
generazione, per confrontare le prestazioni di Gemini/Gemma4/Llama3.1/
Llama3.2 su un campione ampio di richieste.

CSV invece di un vero .xlsx: openpyxl non è installata in questo
progetto (verificato nel venv), e CSV non richiede nessuna libreria
aggiuntiva — il file si apre comunque nativamente in Excel (doppio
click, o Dati > Da testo/CSV). A campagna conclusa, il CSV può essere
convertito in un .xlsx formattato (colori per esito, colonne
dimensionate) come fatto per il primo confronto a 4 modelli del
03/10 (test_llm_locali.xlsx).
"""
import csv
import os
from datetime import datetime

# Path relativo (non assoluto): stessa convenzione di
# backend/database_persistence.py (PERSISTENCE_FILE) — il file viene
# creato/letto nella working directory da cui parte il processo Python
# (la root del progetto, uvicorn main:app viene sempre lanciato da lì),
# non in questa cartella backend/.
LOG_FILE = 'test_campaign_log.csv'

HEADERS = [
    'timestamp', 'modello', 'database', 'query_nl', 'query_jcoql',
    'valida', 'tentativi', 'tempo_generazione_s', 'parser'
]


def log_generation(model: str, database: str, nl_query: str, jcoql_query: str,
                    is_valid: bool, attempts: int, generation_time_seconds: float,
                    parser_name: str):
    """
    Accoda una riga a test_campaign_log.csv, creandolo con l'intestazione
    se non esiste ancora (una riga per OGNI generazione via /api/generate,
    chiamata lì — vedi main.py).

    Chi chiama questa funzione deve avvolgerla in un try/except: un
    errore qui (file aperto con lock esclusivo in Excel su Windows,
    permessi, disco pieno) non deve mai far fallire la generazione vera
    e propria, solo il log della campagna di test.

    encoding='utf-8-sig' (UTF-8 con BOM): senza, Excel su Windows apre
    il CSV con la codifica sbagliata e mostra lettere accentate
    italiane (à, è, ò...) come caratteri corrotti al doppio click —
    il BOM glielo evita.
    """
    file_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(HEADERS)
        writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            model,
            database or '',
            nl_query,
            jcoql_query,
            'SI' if is_valid else 'NO',
            attempts,
            round(generation_time_seconds, 3),
            parser_name,
        ])
