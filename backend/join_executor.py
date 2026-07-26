"""
JoinExecutor - Esegue JOIN tra database diversi

Logica:
1. Esegui query su Database 1 → results_db1
2. Esegui query su Database 2 → results_db2
3. Merge risultati basato su join key
4. Ritorna merged results
"""

import logging
from backend.executors.executor_factory import ExecutorType

join_logger = logging.getLogger('join_executor')


class JoinExecutor:
    """
    Esegue JOIN tra risultati di più database
    """
    
    def __init__(self, executor_factory, parser, db_registry):
        """
        Args:
            executor_factory: ExecutorFactory per creare executor
            parser: Parser ANTLR per validazione
            db_registry: DatabaseRegistry con i database
        """
        self.executor_factory = executor_factory
        self.parser = parser
        self.db_registry = db_registry
    
    def execute_join(self, jcoql_query: str, join_config: dict):
        """
        Esegue JOIN tra due database
        """
        if not join_config:
            join_logger.warning("join_config è vuoto")
            return []
        
        db1_name = join_config.get('db1')
        db2_name = join_config.get('db2')
        join_type = join_config.get('joinType', 'INNER')
        join_key_db1 = join_config.get('joinKey', '.user_id')
        join_key_db2 = join_config.get('db2JoinKey', '.id')
        
        join_logger.info(f"🔗 JOIN EXECUTION")
        join_logger.info(f"   Type: {join_type}")
        join_logger.info(f"   DB1: {db1_name} (key: {join_key_db1})")
        join_logger.info(f"   DB2: {db2_name} (key: {join_key_db2})")
        
        try:
            # ✅ STEP 1: Esegui su Database 1
            join_logger.info(f"⚡ Esecuzione su {db1_name}...")
            self.db_registry.set_current_database(db1_name)
            
            join_logger.info(f"DEBUG - Creando executor con: ExecutorType('python_translator'), db={db1_name}")
            executor_db1 = self.executor_factory.create_executor(
                ExecutorType("python_translator"),
                mongo_uri="mongodb://localhost:27017",
                database=db1_name
            )
            
            join_logger.info(f"DEBUG - Executor ritornato: {executor_db1}")
            join_logger.info(f"DEBUG - Tipo: {type(executor_db1)}")
            
            if executor_db1 is None:
                join_logger.error(f"❌ CRITICO: create_executor ha ritornato None per {db1_name}!")
                return []
                
            join_logger.info(f"   ✅ Executor DB1 creato")
            
            results_db1 = executor_db1.execute(jcoql_query)
            if isinstance(results_db1, dict) and 'results' in results_db1:
                results_db1 = results_db1['results']
            
            join_logger.info(f"   ✅ DB1 risultati: {len(results_db1)}")
            
            # ✅ STEP 2: Esegui su Database 2
            join_logger.info(f"⚡ Esecuzione su {db2_name}...")
            self.db_registry.set_current_database(db2_name)
            
            join_logger.info(f"DEBUG - Creando executor con: ExecutorType('python_translator'), db={db2_name}")
            executor_db2 = self.executor_factory.create_executor(
                ExecutorType("python_translator"),
                mongo_uri="mongodb://localhost:27017",
                database=db2_name
            )
            
            join_logger.info(f"DEBUG - Executor ritornato: {executor_db2}")
            join_logger.info(f"DEBUG - Tipo: {type(executor_db2)}")
            
            if executor_db2 is None:
                join_logger.error(f"❌ CRITICO: create_executor ha ritornato None per {db2_name}!")
                return []
                
            join_logger.info(f"   ✅ Executor DB2 creato")
            
            results_db2 = executor_db2.execute(jcoql_query)
            if isinstance(results_db2, dict) and 'results' in results_db2:
                results_db2 = results_db2['results']
            
            join_logger.info(f"   ✅ DB2 risultati: {len(results_db2)}")
            
            # ✅ STEP 3: Merge basato su join key
            merged = self._merge_results(
                results_db1, results_db2,
                join_key_db1, join_key_db2,
                join_type, db1_name, db2_name
            )
            
            join_logger.info(f"   🔗 Merged risultati: {len(merged)}")
            
            return merged
            
        except Exception as err:
            join_logger.error(f"❌ Errore JOIN: {err}", exc_info=True)
            return []
    
    def _extract_join_key(self, doc: dict, key_path: str):
        """
        Estrae il valore della chiave da un documento
        
        Es: ".user_id" → doc['user_id']
            ".author.id" → doc['author']['id']
        """
        # Rimuovi il punto iniziale
        path = key_path.lstrip('.')
        
        # Split per accesso nested (es: author.id)
        parts = path.split('.')
        
        value = doc
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        
        return value
    
    def _merge_results(self, results_db1, results_db2, key_db1, key_db2, join_type, db1_name, db2_name):
        """
        Merge risultati basato su join key
        
        INNER: Solo righe dove join_key_db1 = join_key_db2
        LEFT: Tutte da DB1 + match da DB2
        RIGHT: Tutte da DB2 + match da DB1
        FULL: Unione di LEFT e RIGHT
        """
        merged = []
        
        # Crea index per DB2 per lookup veloce
        db2_index = {}
        for doc in results_db2:
            key_val = self._extract_join_key(doc, key_db2)
            if key_val:
                db2_index[key_val] = doc
        
        # INNER JOIN: itera DB1, cerca match in DB2
        if join_type == 'INNER':
            for doc1 in results_db1:
                key_val = self._extract_join_key(doc1, key_db1)
                if key_val in db2_index:
                    # Merge i due documenti
                    merged_doc = {
                        f"{db1_name}": doc1,
                        f"{db2_name}": db2_index[key_val],
                        "_join_key": key_val,
                        "_source": [db1_name, db2_name]
                    }
                    merged.append(merged_doc)
        
        # LEFT JOIN: tutte da DB1 + match da DB2
        elif join_type == 'LEFT':
            for doc1 in results_db1:
                key_val = self._extract_join_key(doc1, key_db1)
                doc2 = db2_index.get(key_val)
                merged_doc = {
                    f"{db1_name}": doc1,
                    f"{db2_name}": doc2,
                    "_join_key": key_val,
                    "_source": [db1_name] + ([db2_name] if doc2 else [])
                }
                merged.append(merged_doc)
        
        # RIGHT JOIN: tutte da DB2 + match da DB1
        elif join_type == 'RIGHT':
            db1_index = {}
            for doc in results_db1:
                key_val = self._extract_join_key(doc, key_db1)
                if key_val:
                    db1_index[key_val] = doc
            
            for doc2 in results_db2:
                key_val = self._extract_join_key(doc2, key_db2)
                doc1 = db1_index.get(key_val)
                merged_doc = {
                    f"{db1_name}": doc1,
                    f"{db2_name}": doc2,
                    "_join_key": key_val,
                    "_source": ([db1_name] if doc1 else []) + [db2_name]
                }
                merged.append(merged_doc)
        
        # FULL OUTER JOIN: unione di LEFT e RIGHT
        elif join_type == 'FULL':
            left_results = self._merge_results(results_db1, results_db2, key_db1, key_db2, 'LEFT', db1_name, db2_name)
            merged = left_results
            
            # Aggiungi record da DB2 che non sono in DB1
            db1_keys = set()
            for doc in results_db1:
                key_val = self._extract_join_key(doc, key_db1)
                if key_val:
                    db1_keys.add(key_val)
            
            for doc2 in results_db2:
                key_val = self._extract_join_key(doc2, key_db2)
                if key_val not in db1_keys:
                    merged_doc = {
                        f"{db1_name}": None,
                        f"{db2_name}": doc2,
                        "_join_key": key_val,
                        "_source": [db2_name]
                    }
                    merged.append(merged_doc)
        
        return merged