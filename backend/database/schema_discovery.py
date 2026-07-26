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
            # Evita di tracciare l'ID interno di MongoDB (opzionale, se serve levalo)
            if key == '_id':
                continue
            
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
                        fields_info[field_path]['examples'].append(value)
                    except:
                        pass
            
            # Se è un oggetto annidato, vai in ricorsione
            if isinstance(value, dict):
                self._extract_fields(value, fields_info, field_path)
            
            # Se è un array di oggetti, analizza il primo elemento per capirne la struttura
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                self._extract_fields(value[0], fields_info, field_path)

    def _get_type(self, value) -> str:
        """Mappa il tipo Python al tipo MongoDB in stringa."""
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
        """Chiude la connessione a MongoDB"""
        if self.client:
            self.client.close()
            discovery_logger.info(f"✅ Connessione chiusa a {self.database_name}")