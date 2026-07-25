"""
Database Persistence - Salva i database connessi su disco

Così quando il server si riavvia, i database rimangono connessi
"""
import json
import os
import logging

persistence_logger = logging.getLogger('persistence')

PERSISTENCE_FILE = 'connected_databases.json'


def save_databases_to_file(registry):
    """
    Salva i database connessi su file JSON
    """
    try:
        databases_data = {}
        
        for db_name, db_info in registry.databases.items():
            databases_data[db_name] = {
                'name': db_name,
                'mongo_uri': db_info.get('mongo_uri'),
                'database_name': db_info.get('database_name')
            }
        
        with open(PERSISTENCE_FILE, 'w') as f:
            json.dump(databases_data, f, indent=2)
        
        persistence_logger.info(f"✅ {len(databases_data)} database salvati su file")
        
    except Exception as err:
        persistence_logger.error(f"Errore salvataggio database: {err}")


def load_databases_from_file(registry):
    """
    Carica i database salvati dal file JSON
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
                mongo_uri=db_info['mongo_uri'],
                database_name=db_info['database_name']
            )
            count += 1
        
        persistence_logger.info(f"✅ {count} database caricati da file")
        
    except Exception as err:
        persistence_logger.error(f"Errore caricamento database: {err}")