"""
Configurazione logging per JCoQL Engine
Modulo responsabile della gestione e formattazione dei log su console e file.
"""
import logging
import os
import sys  # Importato per rilevare il sistema operativo e configurare sys.stdout / sys.stderr
from datetime import datetime

# ==============================================================================
# FIX UTF-8 PER WINDOWS
# ==============================================================================
# Su Windows la console usa spesso codifiche legacy (es. CP1252) che non supportano
# le emoji (come 🚀, 📦, 🔧, ✅). Questa reconfigurazione forza l'output a usare UTF-8,
# evitando il crash per UnicodeEncodeError.
if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding="utf-8")

# ==============================================================================
# CREAZIONE DIRECTORY E FILE DI LOG
# ==============================================================================
# Definizione della cartella 'logs' all'interno della directory di lavoro corrente
LOG_DIR = os.path.join(os.getcwd(), 'logs')

# Crea la cartella 'logs' se non esiste già (exist_ok=True evita errori se la cartella c'è già)
os.makedirs(LOG_DIR, exist_ok=True)

# Genera un nome file univoco contenente il timestamp corrente (es. jcoql_engine_20260723_161800.log)
LOG_FILE = os.path.join(LOG_DIR, f'jcoql_engine_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')


# ==============================================================================
# INIZIALIZZAZIONE LOGGING
# ==============================================================================
def setup_logging():
    """
    Configura il logger principale (root) destinando l'output sia alla console
    che al file fisico di log.

    IMPORTANTE PER CHI TOCCA QUESTO FILE: va chiamata UNA SOLA VOLTA per
    processo (oggi succede a livello di modulo in main.py, riga 99, quando
    main.py viene importato). Ogni chiamata aggiunge un nuovo handler al
    logger root con logger.addHandler(...) — chiamarla di nuovo altrove
    (es. dentro un endpoint, o reimportando il modulo in un contesto che
    lo rieseguisse) duplicherebbe gli handler e ogni riga di log
    apparirebbe ripetuta N volte in console/file.

    Returns:
        tuple: (logger root configurato, percorso assoluto del file di log)
    """
    
    # Recupera il logger root principale di Python
    logger = logging.getLogger()
    
    # Imposta il livello di cattura minimo globale a DEBUG (cattura qualsiasi tipo di log)
    logger.setLevel(logging.DEBUG)

    # 🤫 Silenzia i log rumorosi di PyMongo (heartbeat ogni 10s)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    
    # Definisce la struttura grafica della riga di log:
    # Es: 2026-07-23 16:18:00 - root - INFO - 🚀 JCoQL Engine avviato
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # --- Handler 1: Console ---
    # Invia i messaggi sullo schermo (stdout)
    # Impostiamo esplicitamente stream=sys.stdout per assicurarci di usare lo stream UTF-8 sistemato sopra
    console_handler = logging.StreamHandler(sys.stdout)
    
    # Mostra in console solo i log di livello INFO, WARNING, ERROR, CRITICAL (ignora DEBUG per pulizia)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # --- Handler 2: File ---
    # Salva tutti i dettagli dei log nel file con codifica UTF-8 garantita
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    
    # Nel file salviamo TUTTO, compresi i log dettagliati di livello DEBUG
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # --- Log di benvenuto / Avvio ---
    logger.info("=" * 70)
    logger.info("🚀 JCoQL Engine avviato")
    logger.info("=" * 70)
    logger.info(f"Log file: {LOG_FILE}")
    
    return logger, LOG_FILE


# ==============================================================================
# LOGGER SPECIFICI PER SOTTO-MODULI (PATTERN SINGLETON)
# ==============================================================================
# Variabili globali per memorizzare le istanze dei logger ed evitarne la ricreazione
startup_logger = None
query_logger = None
db_logger = None

def get_startup_logger():
    """Ritorna il logger dedicato alla fase di avvio (startup)"""
    global startup_logger
    if startup_logger is None:
        startup_logger = logging.getLogger('startup')
    return startup_logger

def get_query_logger():
    """Ritorna il logger dedicato all'esecuzione delle query"""
    global query_logger
    if query_logger is None:
        query_logger = logging.getLogger('query')
    return query_logger

def get_db_logger():
    """Ritorna il logger dedicato alle operazioni sul Database"""
    global db_logger
    if db_logger is None:
        db_logger = logging.getLogger('database')
    return db_logger