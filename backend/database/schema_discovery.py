"""
Schema Discovery - Introspection dinamica di MongoDB
"""
from pymongo import MongoClient
from collections import defaultdict
import logging

# Inizializza il logger
discovery_logger = logging.getLogger('schema_discovery')

class MongoSchemaDiscoverer:
    """
    Scopre lo schema di un database MongoDB
    Introspection profonda di collezioni, campi annidati e frequenze.
    """
    
    def __init__(self, mongo_uri: str, database_name: str):
        """
        Inizializza il discoverer e connette a MongoDB
        
        Args:
            mongo_uri: URI MongoDB (es: mongodb://localhost:27017)
            database_name: Nome del database (es: jcoql_test o qualsiasi altro)
        """
        self.mongo_uri = mongo_uri
        self.database_name = database_name
        self.client = None
        self.database = None
        
        # Connetti a MongoDB
        self._connect()
    
    def _connect(self):
        """Connette a MongoDB e seleziona il database"""
        try:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            # Verifica la connessione
            self.client.admin.command('ping')
            self.database = self.client[self.database_name]
            discovery_logger.info(f"✅ Connesso a {self.database_name}")
        except Exception as err:
            discovery_logger.error(f"❌ Errore connessione a {self.database_name}: {err}")
            raise
    
    def discover_schema(self, sample_size=100) -> dict:
        """
        Scopre lo schema di TUTTE le collezioni nel database selezionato.
        
        Returns:
            dict: {
                'collection_name': {
                    'total_documents': int,
                    'sampled_documents': int,
                    'fields': {
                        'field_name': {'types': ['string'], 'frequency': 1.0, 'examples': [...]},
                        ...
                    }
                },
                ...
            }
        """
        if self.database is None:
            discovery_logger.warning(f"Database non connesso: {self.database_name}")
            return {}
        
        schema = {}
        
        try:
            # Recupera dinamicamente le collezioni del database corrente
            collection_names = self.database.list_collection_names()

            # Esclude le collection temporanee interne
            # (nlquery*, chaintemp*) dalla scoperta dello schema — se una
            # di queste fosse rimasta per caso in MongoDB nel momento esatto
            # in cui questa scansione parte (es. un vecchio residuo da
            # prima di un fix di pulizia, o un avvio del backend proprio
            # durante l'esecuzione di una query), verrebbe altrimenti
            # "scoperta" come se fosse una collection vera, e l'LLM
            # potrebbe arrivare a referenziarla in una query generata come
            # se fosse un dato reale dell'utente (osservato dal vivo: un
            # GET COLLECTION su un nome nlquery<hex>).
            collection_names = [
                c for c in collection_names
                if not (c.startswith('nlquery') or c.startswith('chaintemp'))
            ]

            discovery_logger.info(f"🔍 Scoperta collezioni in {self.database_name}: {collection_names}")
            
            for collection_name in collection_names:
                schema[collection_name] = self.discover_collection_schema(collection_name, sample_size)
            
            return schema
            
        except Exception as err:
            discovery_logger.error(f"❌ Errore discovery schema: {err}")
            return {}
    
    def discover_collection_schema(self, collection_name: str, sample_size: int = 100) -> dict:
        """
        Scopre lo schema di UNA collezione effettuando ispezione profonda (nested).
        
        Args:
            collection_name: Nome della collezione
            sample_size: Numero massimo di documenti da campionare
        """
        try:
            collection = self.database[collection_name]
            
            # Conta documenti totali
            total_docs = collection.count_documents({})
            
            # Campiona i primi documenti
            samples = list(collection.find().limit(sample_size))
            
            if not samples:
                discovery_logger.debug(f"  📭 Collezione vuota: {collection_name}")
                return {
                    "total_documents": 0,
                    "sampled_documents": 0,
                    "fields": {}
                }
            
            # Inizializza il tracciamento dei campi
            fields_info = defaultdict(lambda: {
                'types': set(),
                'count': 0,
                'examples': []
            })
            
            # Estrai i campi da tutti i campioni (inclusi quelli annidati)
            for doc in samples:
                self._extract_fields(doc, fields_info)
            
            # Converti nel formato finale dict
            # NOTA: 'frequency' è relativa al CAMPIONE (len(samples)), non
            # al totale dei documenti della collection. Se sample_size
            # (default 100) è minore di total_documents, la frequenza è
            # una stima statistica, non un valore esatto — accettabile
            # per dare all'LLM un'idea di "quanto è comune questo campo",
            # ma da non trattare come dato certo su collection molto
            # grandi o eterogenee.
            fields = {}
            for field_path, info in fields_info.items():
                fields[field_path] = {
                    'types': list(info['types']),
                    'frequency': info['count'] / len(samples),
                    'examples': info['examples'][:3] # Mantiene max 3 esempi
                }
            
            discovery_logger.debug(f"  📋 {collection_name}: mappati {len(fields)} campi")
            
            return {
                "total_documents": total_docs,
                "sampled_documents": len(samples),
                "fields": fields
            }
            
        except Exception as err:
            discovery_logger.error(f"❌ Errore discovery collezione {collection_name}: {err}")
            return {}

    def _extract_fields(self, doc: dict, fields_info: dict, prefix: str = ""):
        """Estrae tutti i campi da un documento in modo ricorsivo."""
        for key, value in doc.items():
            # _id non va escluso dallo schema mostrato all'LLM nel prompt:
            # è spesso l'identificativo vero usato come chiave di join
            # (es. products._id, non un separato "product_id"), e l'LLM,
            # non sapendo che esiste, indovina un altro campo (osservato:
            # .d.name invece di .d._id in un JOIN concatenato).

            # Costruisci il percorso del campo (es: "address.city")
            field_path = f"{prefix}.{key}" if prefix else key
            
            # Determina il tipo
            value_type = self._get_type(value)
            
            # Aggiorna statistiche
            fields_info[field_path]['types'].add(value_type)
            fields_info[field_path]['count'] += 1
            
            # Salva esempi solo se non è un oggetto o un array completo
            if value_type not in ['array', 'object']:
                if len(fields_info[field_path]['examples']) < 3:
                    try:
                        """
                        Gli esempi finiscono nello schema che
                        GET /api/databases/<nome> restituisce al frontend
                        come JSON. Un valore Mongo non nativo (tipicamente
                        l'ObjectId di _id nelle collection create da un
                        SAVE AS, dove _id lo genera MongoDB, ma anche
                        datetime, Decimal128...) farebbe fallire
                        jsonable_encoder di FastAPI con un 500
                        ("'ObjectId' object is not iterable"), osservato il
                        05/10 durante il round 3 della campagna di test.
                        Qui si converte in stringa tutto cio' che non e'
                        gia' un tipo JSON nativo (la risposta della
                        generazione non era coinvolta: il 500 era solo sul
                        refresh dello schema). Il tipo del campo resta
                        quello calcolato da _get_type (invariato per il
                        prompt).
                        """
                        if value is None or isinstance(value, (str, int, float, bool)):
                            example_value = value
                        else:
                            example_value = str(value)
                        fields_info[field_path]['examples'].append(example_value)
                    except:
                        pass
            
            # Se è un oggetto annidato, vai in ricorsione
            if isinstance(value, dict):
                self._extract_fields(value, fields_info, field_path)
            
            # Se è un array di oggetti, analizza il primo elemento per capirne la struttura
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                self._extract_fields(value[0], fields_info, field_path)

    def _get_type(self, value) -> str:
        """
        Mappa il tipo Python al tipo MongoDB in stringa.

        NOTA: l'ordine dei controlli non è arbitrario. In Python `bool` è
        una sottoclasse di `int` (isinstance(True, int) vale True), quindi
        il controllo `isinstance(value, bool)` deve stare PRIMA di
        `isinstance(value, int)` — altrimenti ogni valore booleano
        verrebbe classificato come 'integer' invece che 'boolean'. Se
        aggiungi altri tipi in futuro, tieni a mente questa gerarchia.
        """
        if isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, int):
            return 'integer'
        elif isinstance(value, float):
            return 'number'
        elif isinstance(value, str):
            return 'string'
        elif isinstance(value, list):
            return 'array'
        elif isinstance(value, dict):
            return 'object'
        elif value is None:
            return 'null'
        else:
            return 'unknown'
    
    def close(self):
        """
        Chiude la connessione a MongoDB di QUESTA istanza.

        NOTA: nel flusso reale dell'app (DatabaseRegistry.add_database,
        vedi database_registry.py) questo metodo non viene mai chiamato:
        il discoverer viene creato, usato una volta per scoprire lo
        schema, poi solo il suo .client viene estratto e conservato dentro
        db_registry.databases[nome]["client"] — l'oggetto discoverer in
        sé viene scartato, ma la connessione (il client) resta viva e
        verrà chiusa più avanti da DatabaseRegistry.close_all(). Questo
        metodo resta utile se usi MongoSchemaDiscoverer da solo (script,
        test manuali) senza passare dal registry.
        """
        if self.client:
            self.client.close()
            discovery_logger.info(f"✅ Connessione chiusa a {self.database_name}")


# ==============================================================================
# AGGIUNTO 03/10/2026 — integrazione JCO DS (vedi database_registry.py)
# ==============================================================================
class JcoDsSchemaDiscoverer:
    """
    Scopre lo schema di un database JCO DS (J-CO Document Store), il
    server alternativo a MongoDB dei professori
    (https://github.com/JcoProjectTeam), campionando i documenti
    attraverso il motore Java stesso (JCoFrameworkExecutor) invece che
    con un client Python del protocollo DS — non esiste un client Python
    per quel protocollo binario proprietario, mentre il motore Java sa
    già parlarci (stesso percorso validato a mano con "USE DB ... ON
    SERVER 'jcods' '...'; GET COLLECTION x@y;").

    LIMITE NOTO: a differenza di MongoSchemaDiscoverer, qui le collection
    da ispezionare vanno indicate esplicitamente (parametro `collections`
    del costruttore) — JCoQL non ha un comando per elencare le collection
    di un database (non esiste un "SHOW COLLECTIONS"), quindi non c'è modo
    di scoprirle automaticamente come con database.list_collection_names()
    di pymongo. Chi registra un database JCO DS deve già sapere quali
    collection vuole esporre all'interfaccia.
    """

    def __init__(self, host: str, port: int, database_name: str, collections: list):
        self.host = host
        self.port = port
        self.database_name = database_name
        self.collections = collections or []

    def discover_schema(self, sample_size: int = 100) -> dict:
        # Import locale per evitare un import circolare a livello modulo
        # (jco_framework_executor_v2.py non importa questo file, ma
        # tenerlo locale evita comunque di caricare l'intero executor —
        # con tutta la logica di costruzione del classpath Java — ogni
        # volta che schema_discovery.py viene importato per il solo
        # ramo MongoDB, che è il caso comune).
        from backend.executors.jco_framework_executor_v2 import JCoFrameworkExecutor
        executor = JCoFrameworkExecutor()

        schema = {}
        for collection_name in self.collections:
            schema[collection_name] = self.discover_collection_schema(executor, collection_name, sample_size)
        return schema

    def discover_collection_schema(self, executor, collection_name: str, sample_size: int = 100) -> dict:
        """
        Una query completa per collection (USE DB + GET COLLECTION), non
        una sola sessione riutilizzata — ogni chiamata a executor.execute()
        lancia un sottoprocesso Java indipendente (stesso funzionamento
        del resto dell'app), quindi il costo è lo stesso di qualunque
        altra query eseguita dall'interfaccia.
        """
        query = (
            f"USE DB {self.database_name} ON SERVER 'jcods' 'http://{self.host}:{self.port}';\n"
            f"GET COLLECTION {collection_name}@{self.database_name};"
        )
        try:
            result = executor.execute(query, timeout=30)
        except Exception as err:
            discovery_logger.error(f"❌ Errore discovery collezione JCO DS '{collection_name}': {err}")
            return {"total_documents": 0, "sampled_documents": 0, "fields": {}}

        if not result.get('success'):
            discovery_logger.warning(f"⚠️ Discovery JCO DS '{collection_name}' fallita: {result.get('error')}")
            return {"total_documents": 0, "sampled_documents": 0, "fields": {}}

        samples = (result.get('results') or [])[:sample_size]
        if not samples:
            discovery_logger.debug(f"  📭 Collezione JCO DS vuota: {collection_name}")
            return {"total_documents": result.get('count', 0), "sampled_documents": 0, "fields": {}}

        fields_info = defaultdict(lambda: {'types': set(), 'count': 0, 'examples': []})
        for doc in samples:
            self._extract_fields(doc, fields_info)

        fields = {}
        for field_path, info in fields_info.items():
            fields[field_path] = {
                'types': list(info['types']),
                'frequency': info['count'] / len(samples),
                'examples': info['examples'][:3]
            }

        discovery_logger.debug(f"  📋 {collection_name} (JCO DS): mappati {len(fields)} campi")

        return {
            "total_documents": result.get('count', len(samples)),
            "sampled_documents": len(samples),
            "fields": fields
        }

    # Stessa identica logica di estrazione/tipizzazione campi di
    # MongoSchemaDiscoverer sopra — duplicata qui apposta (non unificata
    # in un helper condiviso) per non legare un fix futuro pensato per
    # una sola delle due classi all'altra.
    def _extract_fields(self, doc, fields_info: dict, prefix: str = ""):
        if not isinstance(doc, dict):
            return
        for key, value in doc.items():
            field_path = f"{prefix}.{key}" if prefix else key
            value_type = self._get_type(value)
            fields_info[field_path]['types'].add(value_type)
            fields_info[field_path]['count'] += 1

            if value_type not in ['array', 'object']:
                if len(fields_info[field_path]['examples']) < 3:
                    try:
                        fields_info[field_path]['examples'].append(value)
                    except Exception:
                        pass

            if isinstance(value, dict):
                self._extract_fields(value, fields_info, field_path)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                self._extract_fields(value[0], fields_info, field_path)

    def _get_type(self, value) -> str:
        if isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, int):
            return 'integer'
        elif isinstance(value, float):
            return 'number'
        elif isinstance(value, str):
            return 'string'
        elif isinstance(value, list):
            return 'array'
        elif isinstance(value, dict):
            return 'object'
        elif value is None:
            return 'null'
        else:
            return 'unknown'