"""
Database Registry - Gestisce connessioni multiple a MongoDB
"""
from pymongo import MongoClient
from backend.database.schema_discovery import MongoSchemaDiscoverer
from typing import Dict, Optional
from backend.logging_config import get_db_logger
db_logger = get_db_logger()

class DatabaseRegistry:
    """
    Registra e gestisce multiple connessioni MongoDB.

    NOTA: self.databases NON è {nome: connessione_mongo}, ma
    {nome: dict_con_metadati} — ogni valore è un dizionario con le chiavi
    "uri", "database_name", "schema", "client" (qui sì c'è il vero
    pymongo.MongoClient) e "collections" (conteggio già calcolato in
    add_database, vedi sotto). Chi consuma self.databases altrove nel
    progetto deve tenerne conto: db_registry.databases[nome] non ha
    metodi come .list_collection_names(), solo db_registry.databases[nome]["client"]
    li ha.
    """
    
    def __init__(self):
        self.databases: Dict[str, dict] = {}
        self.current_database: Optional[str] = None
    
    def add_database(self, db_name: str, mongo_uri: str, database_name: str):
        """
        Connette un nuovo database MongoDB e ne scopre subito lo schema.

        NOTA: la schema discovery (sample_size=100 documenti per
        collection, vedi schema_discovery.py) avviene qui in modo
        SINCRONO/bloccante — questa chiamata non ritorna finché non ha
        ispezionato tutte le collection del database. Per un database
        con molte collection o irraggiungibile, add_database può
        impiegare diversi secondi o bloccarsi sul timeout di connessione
        di pymongo prima di fallire nel blocco except sotto.
        """
        db_logger.info(f"🔗 Tentativo connessione database '{db_name}'...")
        db_logger.debug(f"   URI: {mongo_uri}")
        db_logger.debug(f"   Database: {database_name}")
        
        try:
            discoverer = MongoSchemaDiscoverer(mongo_uri, database_name)
            schema = discoverer.discover_schema(sample_size=100)
            
            self.databases[db_name] = {
                "uri": mongo_uri,
                "database_name": database_name,
                "schema": schema,
                "client": discoverer.client,
                "collections": len(schema)
            }
            
            if self.current_database is None:
                self.current_database = db_name
            
            db_logger.info(f"✅ Database '{db_name}' connesso: {len(schema)} collezioni")
            for coll in list(schema.keys())[:3]:
                db_logger.debug(f"   - {coll}")
            
            return True
            
        except Exception as e:
            db_logger.error(f"❌ Errore connessione '{db_name}': {e}", exc_info=True)
            return False
        
    def set_current_database(self, db_name: str) -> bool:
        """Seleziona il database attualmente in uso"""
        if db_name not in self.databases:
            db_logger.warning(f"❌ Database '{db_name}' non trovato")
            return False
        
        self.current_database = db_name
        db_logger.info(f"✅ Database corrente: '{db_name}'")
        return True
    
    def get_current_schema(self) -> dict:
        """Ritorna lo schema del database corrente"""
        if not self.current_database:
            return {}
        
        return self.databases[self.current_database]["schema"]
    
    def get_current_database_name(self) -> str:
        """Ritorna il nome del database attualmente in uso"""
        return self.current_database or "None"
    
    def list_databases(self) -> list:
        """Lista tutti i database registrati"""
        return [
            {
                "name": db_name,
                "uri": info["uri"],
                "database": info["database_name"],
                "collections": info["collections"],
                "current": db_name == self.current_database
            }
            for db_name, info in self.databases.items()
        ]
    
    def get_database_info(self, db_name: str) -> dict:
        """Info dettagliate di un database"""
        if db_name not in self.databases:
            return {}
        
        info = self.databases[db_name]
        return {
            "name": db_name,
            "uri": info["uri"],
            "database": info["database_name"],
            "schema": info["schema"],
            "collections": info["collections"],
            "is_current": db_name == self.current_database
        }
    
    def close_all(self):
        """
        Chiude tutte le connessioni MongoDB aperte. Chiamata da main.py
        nell'evento "shutdown" di FastAPI.
        """
        for db_name, info in self.databases.items():
            try:
                info["client"].close()
                db_logger.info(f"✅ Connessione '{db_name}' chiusa")
            except Exception as e:
                db_logger.warning(f"⚠️ Errore chiusura '{db_name}': {e}")


    def get_schema_for_all_databases(self) -> dict:
            """
            Ritorna lo schema di TUTTI i database registrati
            
            Returns:
                {
                    "jcoql_test": {
                        "users": {"total_documents": 10, "fields": {...}},
                        "orders": {...}
                    },
                    "test_db": {...},
                    ...
                }
            """
            all_schemas = {}
            
            for db_name, db_info in self.databases.items():
                all_schemas[db_name] = db_info["schema"]
            
            return all_schemas


# Istanza globale — un solo registry condiviso da tutto il processo FastAPI
db_registry = DatabaseRegistry()