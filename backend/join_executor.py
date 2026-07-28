"""
JoinExecutor - Esegue JOIN tra database diversi usando il JCo Framework

Logica:
1. Esegui query su Database 1 → results_db1
2. Esegui query su Database 2 → results_db2
3. Merge risultati basato su join key
4. Ritorna merged results
"""

import logging
import json
from backend.executors.executor_factory import ExecutorType

join_logger = logging.getLogger('join_executor')


class JoinExecutor:
    """
    Esegue JOIN tra risultati di più database tramite JCo Framework
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
        Esegue JOIN tra due database usando SOLO JCo Framework
        """
        if not join_config:
            join_logger.warning("join_config è vuoto")
            return []
        
        db1_name = join_config.get('db1')
        db2_name = join_config.get('db2')
        join_type = join_config.get('joinType', 'INNER').upper()
        join_key_db1 = join_config.get('joinKey', '.user_id')
        join_key_db2 = join_config.get('db2JoinKey', '.id')
        
        join_logger.info("🔗 JOIN EXECUTION")
        join_logger.info(f"   Type: {join_type}")
        join_logger.info(f"   DB1: {db1_name} (key: {join_key_db1})")
        join_logger.info(f"   DB2: {db2_name} (key: {join_key_db2})")
        
        try:
            # ✅ STEP 1: Esegui su Database 1
            join_logger.info(f"⚡ Esecuzione su {db1_name}...")
            self.db_registry.set_current_database(db1_name)
            
            join_logger.info(f"DEBUG - Creando executor JCo per db={db1_name}")
            executor_db1 = self.executor_factory.create_executor(
                ExecutorType("jco_framework"),
                mongo_uri="mongodb://localhost:27017",
                database=db1_name
            )
            
            if executor_db1 is None:
                join_logger.error(f"❌ CRITICO: create_executor ha ritornato None per {db1_name}!")
                return []
                
            join_logger.info("   ✅ Executor DB1 creato")
            
            results_db1 = executor_db1.execute(jcoql_query)
            if isinstance(results_db1, dict) and 'results' in results_db1:
                results_data = results_db1['results']
                
                # Parsa i risultati di JCo Framework
                if isinstance(results_data, dict) and 'text' in results_data:
                    try:
                        results_db1 = json.loads(results_data['text'])
                    except (json.JSONDecodeError, TypeError):
                        results_db1 = results_data.get('text', [])
                else:
                    results_db1 = results_data if isinstance(results_data, list) else []

            join_logger.info(f"   ✅ DB1 risultati: {len(results_db1)}")
            
            # ✅ STEP 2: Esegui su Database 2
            join_logger.info(f"⚡ Esecuzione su {db2_name}...")
            self.db_registry.set_current_database(db2_name)
            
            join_logger.info(f"DEBUG - Creando executor JCo per db={db2_name}")
            executor_db2 = self.executor_factory.create_executor(
                ExecutorType("jco_framework"),
                mongo_uri="mongodb://localhost:27017",
                database=db2_name
            )
            
            if executor_db2 is None:
                join_logger.error(f"❌ CRITICO: create_executor ha ritornato None per {db2_name}!")
                return []
                
            join_logger.info("   ✅ Executor DB2 creato")
            
            results_db2 = executor_db2.execute(jcoql_query)
            if isinstance(results_db2, dict) and 'results' in results_db2:
                results_data = results_db2['results']
                
                # Parsa i risultati di JCo Framework
                if isinstance(results_data, dict) and 'text' in results_data:
                    try:
                        results_db2 = json.loads(results_data['text'])
                    except (json.JSONDecodeError, TypeError):
                        results_db2 = results_data.get('text', [])
                else:
                    results_db2 = results_data if isinstance(results_data, list) else []

            join_logger.info(f"   ✅ DB2 risultati: {len(results_db2)}")
            
            # 🔍 DEBUG: Stampa i primi record
            if results_db1:
                join_logger.info(f"🔍 SAMPLE DB1 doc: {results_db1[0]}")
                join_logger.info(f"🔍 SAMPLE DB1 key ('{join_key_db1}'): {self._extract_join_key(results_db1[0], join_key_db1)}")
            
            if results_db2:
                join_logger.info(f"🔍 SAMPLE DB2 doc: {results_db2[0]}")
                join_logger.info(f"🔍 SAMPLE DB2 key ('{join_key_db2}'): {self._extract_join_key(results_db2[0], join_key_db2)}")

            # ✅ STEP 3: Merge basato su join key
            merged = self._merge_results(
                results_db1, results_db2,
                join_key_db1, join_key_db2,
                join_type, db1_name, db2_name
            )
            
            join_logger.info(f"   🔗 Merged risultati: {len(merged)}")
            
            return merged
            
        except Exception as err:
            join_logger.error(f"❌ JCo JOIN Error: {err}", exc_info=True)
            raise
    
    def _extract_join_key(self, doc: dict, key_path: str):
        """
        Estrae il valore della chiave da un documento.
        Se viene richiesto '.id' e la chiave esatta non c'è, controlla prima 'user_id' e poi '_id'.
        """
        if not isinstance(doc, dict):
            return None

        path = key_path.lstrip('.')
        parts = path.split('.')
        
        value = doc
        for part in parts:
            if isinstance(value, dict):
                # 1. Tenta la chiave esatta
                if part in value:
                    value = value.get(part)
                # 2. Se viene richiesto 'id' ma non esiste, controlla se c'è 'user_id' per matchare con DB1
                elif part == 'id':
                    if 'user_id' in value:
                        value = value.get('user_id')
                    elif '_id' in value:
                        value = value.get('_id')
                    else:
                        return None
                else:
                    return None
            else:
                return None
        
        return str(value) if value is not None else None

    def _merge_results(self, results_db1, results_db2, key_db1, key_db2, join_type, db1_name, db2_name):
        """
        Merge dei risultati basato su join key con supporto alle relazioni 1:N / N:N.
        """
        merged = []
        
        # Indicizzazione dei documenti di DB2 per chiave
        db2_index = {}
        for doc in results_db2:
            key_val = self._extract_join_key(doc, key_db2)
            if key_val is not None:
                db2_index.setdefault(key_val, []).append(doc)
        
        # INNER JOIN
        if join_type == 'INNER':
            for doc1 in results_db1:
                key_val = self._extract_join_key(doc1, key_db1)
                if key_val is not None and key_val in db2_index:
                    for doc2 in db2_index[key_val]:
                        merged.append({
                            f"{db1_name}": doc1,
                            f"{db2_name}": doc2,
                            "_join_key": key_val,
                            "_source": [db1_name, db2_name]
                        })
        
        # LEFT JOIN
        elif join_type == 'LEFT':
            for doc1 in results_db1:
                key_val = self._extract_join_key(doc1, key_db1)
                matches = db2_index.get(key_val, []) if key_val is not None else []
                if matches:
                    for doc2 in matches:
                        merged.append({
                            f"{db1_name}": doc1,
                            f"{db2_name}": doc2,
                            "_join_key": key_val,
                            "_source": [db1_name, db2_name]
                        })
                else:
                    merged.append({
                        f"{db1_name}": doc1,
                        f"{db2_name}": None,
                        "_join_key": key_val,
                        "_source": [db1_name]
                    })
        
        # RIGHT JOIN
        elif join_type == 'RIGHT':
            db1_index = {}
            for doc in results_db1:
                key_val = self._extract_join_key(doc, key_db1)
                if key_val is not None:
                    db1_index.setdefault(key_val, []).append(doc)
            
            for doc2 in results_db2:
                key_val = self._extract_join_key(doc2, key_db2)
                matches = db1_index.get(key_val, []) if key_val is not None else []
                if matches:
                    for doc1 in matches:
                        merged.append({
                            f"{db1_name}": doc1,
                            f"{db2_name}": doc2,
                            "_join_key": key_val,
                            "_source": [db1_name, db2_name]
                        })
                else:
                    merged.append({
                        f"{db1_name}": None,
                        f"{db2_name}": doc2,
                        "_join_key": key_val,
                        "_source": [db2_name]
                    })
        
        # FULL OUTER JOIN
        elif join_type == 'FULL':
            db1_keys_matched = set()
            
            for doc1 in results_db1:
                key_val = self._extract_join_key(doc1, key_db1)
                matches = db2_index.get(key_val, []) if key_val is not None else []
                if matches:
                    db1_keys_matched.add(key_val)
                    for doc2 in matches:
                        merged.append({
                            f"{db1_name}": doc1,
                            f"{db2_name}": doc2,
                            "_join_key": key_val,
                            "_source": [db1_name, db2_name]
                        })
                else:
                    merged.append({
                        f"{db1_name}": doc1,
                        f"{db2_name}": None,
                        "_join_key": key_val,
                        "_source": [db1_name]
                    })
            
            for doc2 in results_db2:
                key_val = self._extract_join_key(doc2, key_db2)
                if key_val is not None and key_val not in db1_keys_matched:
                    merged.append({
                        f"{db1_name}": None,
                        f"{db2_name}": doc2,
                        "_join_key": key_val,
                        "_source": [db2_name]
                    })
        
        return merged