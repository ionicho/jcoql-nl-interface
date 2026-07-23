"""
Database Registry - Gestisce connessioni multiple a MongoDB
"""
from pymongo import MongoClient
from backend.database.schema_discovery import MongoSchemaDiscoverer
from typing import Dict, Optional

class DatabaseRegistry:
    """Registra e gestisce multiple connessioni MongoDB"""
    
    def __init__(self):
        self.databases: Dict[str, dict] = {}
        self.current_database: Optional[str] = None
    
    def add_database(self, db_name: str, mongo_uri: str, database_name: str):
        """Aggiungi un database alla registry"""
        try:
            # ✅ NUOVO: Usa la classe MongoSchemaDiscoverer
            discoverer = MongoSchemaDiscoverer(mongo_uri, database_name)
            schema = discoverer.discover_schema(sample_size=100)
            
            # Salva in registry
            self.databases[db_name] = {
                "uri": mongo_uri,
                "database_name": database_name,
                "schema": schema,
                "client": discoverer.client,
                "collections": len(schema)
            }
            
            # Se primo database, impostalo come current
            if self.current_database is None:
                self.current_database = db_name
            
            print(f"✅ Database '{db_name}' aggiunto con {len(schema)} collezioni")
            return True
            
        except Exception as e:
            print(f"❌ Errore aggiunta database '{db_name}': {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def set_current_database(self, db_name: str) -> bool:
        """Seleziona il database attualmente in uso"""
        if db_name not in self.databases:
            print(f"❌ Database '{db_name}' non trovato")
            return False
        
        self.current_database = db_name
        print(f"✅ Database corrente: '{db_name}'")
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
        """Chiudi tutte le connessioni"""
        for db_name, info in self.databases.items():
            try:
                info["client"].close()
                print(f"✅ Connessione '{db_name}' chiusa")
            except Exception as e:
                print(f"⚠️ Errore chiusura '{db_name}': {e}")

# Istanza globale
db_registry = DatabaseRegistry()