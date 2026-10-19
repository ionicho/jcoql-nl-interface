"""
Database Persistence - Salva i database connessi su disco

Così quando il server si riavvia, i database rimangono connessi

NOTA — salva/ricarica solo l'ELENCO dei database connessi (nome, mongo_uri,
database_name). Non ha niente a che fare con "quale database è
attualmente selezionato" (l'ultimo su cui hai lavorato) — quello è uno
stato diverso: vive solo in memoria come attributo
db_registry.current_database (vedi backend/database/database_registry.py,
metodo set_current_database) e NON viene persistito su disco. Quindi ad
ogni riavvio del server, l'elenco dei database connessi torna come prima
(grazie a load_databases_from_file), ma il database "corrente" si
resetta e va riselezionato. Diverso dal motore Java J-CO Framework
(jco-framework, progetto separato), che invece la persiste su file
(current_database.txt) perché lì ogni comando gira in un processo JVM
nuovo — qui invece il processo FastAPI resta lo stesso, quindi la memoria
basta finché il server non si riavvia.

NOTA DI SICUREZZA: mongo_uri può contenere credenziali (utente/password)
se il database è protetto da autenticazione. Qui viene salvato in chiaro
in connected_databases.json. Accettabile per un progetto di tesi che
gira in locale, ma da NON portare così com'è in un contesto con dati
sensibili o server esposti — andrebbe quantomeno escluso da git (verifica
che sia nel .gitignore) o cifrato.
"""
import json
import os
import logging

persistence_logger = logging.getLogger('persistence')

# NOTA: path relativo, non assoluto — il file viene creato/letto nella
# cartella da cui il processo Python viene avviato (la working directory),
# non necessariamente nella root del progetto. Funziona perché in pratica
# il server si avvia sempre da lì (uvicorn main:app dalla root), ma è
# un'assunzione implicita: se in futuro si lanciasse main.py da un'altra cartella, 
# il file salterebbe fuori altrove o non verrebbe trovato.
PERSISTENCE_FILE = 'connected_databases.json'


def save_databases_to_file(registry):
    """
    Salva su connected_databases.json l'elenco dei database attualmente
    connessi nel registry (registry.databases), uno per uno: nome logico,
    URI Mongo e nome del database fisico. Viene chiamata ogni volta che
    un database viene aggiunto/rimosso, così il file resta sempre
    allineato allo stato in memoria.
    """
    try:
        databases_data = {}

        for db_name, db_info in registry.databases.items():
            entry = {
                'name': db_name,
                'mongo_uri': db_info.get('mongo_uri'),
                'database_name': db_info.get('database_name')
            }
            # AGGIUNTO 03/10/2026 — integrazione JCO DS: salvate solo se
            # presenti (un database MongoDB non ha "server" in
            # registry.databases, vedi database_registry.py), così un
            # file scritto da una versione precedente di questo modulo
            # resta nello stesso formato di sempre per i database Mongo.
            server = db_info.get('server')
            if server:
                entry['server'] = server
                entry['collections_list'] = db_info.get('collections_list')
            databases_data[db_name] = entry

        with open(PERSISTENCE_FILE, 'w') as f:
            json.dump(databases_data, f, indent=2)
        
        persistence_logger.info(f"✅ {len(databases_data)} database salvati su file")
        
    except Exception as err:
        persistence_logger.error(f"Errore salvataggio database: {err}")


def load_databases_from_file(registry):
    """
    Da chiamare una volta sola all'avvio del server (in main.py, evento
    "startup"): rilegge connected_databases.json e per ognuno richiama
    registry.add_database(...), che si occupa di ristabilire davvero la
    connessione MongoDB. Se il file non esiste (prima esecuzione, o è
    stato cancellato) non è un errore: semplicemente si parte senza
    database extra già connessi.

    NOTA: se uno dei database salvati non è più raggiungibile (es. era su
    un URI che nel frattempo non risponde più), l'errore di connessione
    finisce loggato qui sotto ma non blocca il caricamento degli altri
    database nel file — ognuno viene tentato indipendentemente dal loop.
    """
    if not os.path.exists(PERSISTENCE_FILE):
        persistence_logger.info("Nessun file di salvataggio database trovato")
        return

    try:
        with open(PERSISTENCE_FILE, 'r') as f:
            databases_data = json.load(f)
        
        count = 0
        for db_name, db_info in databases_data.items():
            registry.add_database(
                db_name=db_name,
                mongo_uri=db_info.get('mongo_uri'),
                database_name=db_info['database_name'],
                # .get(): assenti in un file scritto prima del 03/10/2026
                # (solo database MongoDB) — add_database li tratta come
                # un database MongoDB, esattamente come già faceva.
                server=db_info.get('server'),
                collections=db_info.get('collections_list'),
            )
            count += 1
        
        persistence_logger.info(f"✅ {count} database caricati da file")
        
    except Exception as err:
        persistence_logger.error(f"Errore caricamento database: {err}")