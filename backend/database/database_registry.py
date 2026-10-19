"""
Database Registry - Gestisce connessioni multiple a MongoDB e, dal
03/10/2026, anche a database JCO DS (J-CO Document Store, il server
alternativo dei professori: https://github.com/JcoProjectTeam).
"""
from pymongo import MongoClient
from backend.database.schema_discovery import MongoSchemaDiscoverer, JcoDsSchemaDiscoverer
from typing import Dict, Optional
from backend.logging_config import get_db_logger
db_logger = get_db_logger()

class DatabaseRegistry:
    """
    Registra e gestisce multiple connessioni, a MongoDB o a JCO DS.

    NOTA: self.databases NON è {nome: connessione_mongo}, ma
    {nome: dict_con_metadati} — ogni valore è un dizionario con le chiavi
    "uri", "database_name", "schema", "client" (per i database MongoDB,
    il vero pymongo.MongoClient — None per quelli JCO DS, che non hanno
    un client Python persistente, vedi sotto), "collections" (conteggio
    già calcolato in add_database), "server" (None per un database
    MongoDB — comportamento storico implicito — oppure
    {"type": "jcods", "host":..., "port":...} per un database JCO DS) e
    "collections_list" (solo per JCO DS: i nomi delle collection indicati
    a mano in assenza di una "SHOW COLLECTIONS" in JCoQL, vedi
    schema_discovery.JcoDsSchemaDiscoverer). Chi consuma self.databases
    altrove nel progetto deve tenerne conto: db_registry.databases[nome]
    non ha metodi come .list_collection_names(), solo
    db_registry.databases[nome]["client"] li ha (e solo per MongoDB).
    """

    def __init__(self):
        self.databases: Dict[str, dict] = {}
        self.current_database: Optional[str] = None

    def add_database(self, db_name: str, database_name: str, mongo_uri: str = None,
                      server: Optional[dict] = None, collections: Optional[list] = None):
        """
        Connette un nuovo database (MongoDB se `server` è None — il
        comportamento di sempre, invariato — oppure JCO DS se `server` è
        {"type": "jcods", "host": ..., "port": ...}) e ne scopre subito
        lo schema.

        NOTA: la schema discovery avviene qui in modo SINCRONO/bloccante
        in entrambi i casi — questa chiamata non ritorna finché non ha
        ispezionato tutte le collection del database (per MongoDB: fino
        a 100 documenti a collection via pymongo; per JCO DS: una query
        GET COLLECTION per ogni nome in `collections`, eseguita come
        sottoprocesso Java). Per un database con molte collection o
        irraggiungibile, add_database può impiegare diversi secondi o
        bloccarsi sul timeout di connessione prima di fallire nel blocco
        except sotto.
        """
        server_type = (server or {}).get("type", "mongodb")
        db_logger.info(f"🔗 Tentativo connessione database '{db_name}' (server={server_type})...")
        db_logger.debug(f"   Database: {database_name}")

        try:
            if server_type == "mongodb":
                db_logger.debug(f"   URI: {mongo_uri}")
                discoverer = MongoSchemaDiscoverer(mongo_uri, database_name)
                schema = discoverer.discover_schema(sample_size=100)
                client = discoverer.client
            else:
                if not collections:
                    raise ValueError(
                        "Per un database JCO DS indica almeno una collection "
                        "(JCoQL non ha un comando per elencarle automaticamente)."
                    )
                db_logger.debug(f"   JCO DS {server.get('host')}:{server.get('port')} — collection: {collections}")
                discoverer = JcoDsSchemaDiscoverer(
                    host=server.get("host"),
                    port=server.get("port"),
                    database_name=database_name,
                    collections=collections,
                )
                schema = discoverer.discover_schema(sample_size=100)
                client = None  # nessun client Python persistente per JCO DS

            self.databases[db_name] = {
                "uri": mongo_uri,
                "database_name": database_name,
                "schema": schema,
                "client": client,
                "collections": len(schema),
                "server": server,
                "collections_list": collections,
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
    
    def _server_descriptor(self, info: dict) -> dict:
        """
        Descrittore del server a cui appartiene un database, usato dal
        frontend per raggruppare l'elenco database per server (sezione
        con il nome/tipo di server come sottotitolo). Per i database
        MongoDB "server" è sempre None in self.databases (comportamento
        storico, mai cambiato) — qui si sintetizza un descrittore
        equivalente a quello usato realmente per connettersi (vedi
        add_database: mongo_uri di default "mongodb://localhost:27017"),
        così ANCHE i database MongoDB hanno un "server" coerente da
        mostrare, senza dover distinguere un caso None nel frontend.
        """
        server = info.get("server")
        if server:
            return server
        return {"type": "mongodb", "host": "localhost", "port": 27017}

    def list_databases(self) -> list:
        """Lista tutti i database registrati"""
        return [
            {
                "name": db_name,
                "uri": info["uri"],
                "database": info["database_name"],
                "collections": info["collections"],
                "current": db_name == self.current_database,
                "server": self._server_descriptor(info)
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
            "is_current": db_name == self.current_database,
            "server": self._server_descriptor(info),
            "collections_list": info.get("collections_list")
        }

    def close_all(self):
        """
        Chiude tutte le connessioni MongoDB aperte. Chiamata da main.py
        nell'evento "shutdown" di FastAPI.

        NOTA 03/10/2026: un database JCO DS non ha un "client" Python
        persistente (vedi add_database) — info["client"] è None per
        quelle entry, quindi va saltato esplicitamente invece di provare
        a chiamare .close() su None (AttributeError, comunque già
        ingoiato dall'except sotto, ma così non genera nemmeno un
        warning fuorviante ad ogni avvio/arresto).
        """
        for db_name, info in self.databases.items():
            if not info.get("client"):
                continue
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