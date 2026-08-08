"""
JoinExecutor - Esegue JOIN tra database diversi usando il JCo Framework

Logica:
1. Esegui query su Database 1 → results_db1
2. Esegui query su Database 2 → results_db2
3. Merge risultati basato su join key
4. Ritorna merged results

PERCHÉ IL JOIN È FATTO QUI IN PYTHON E NON DENTRO UNA QUERY JCoQL+ SOLA:
JCoQL+ ha un comando nativo "JOIN OF COLLECTIONS", ma farlo generare
correttamente all'LLM a partire da linguaggio naturale si è rivelato
inaffidabile (il RAG tendeva a recuperare esempi di FILTER non pertinenti
invece di esempi di JOIN). La soluzione adottata qui aggira il problema:
la STESSA query JCoQL+ (tipicamente un semplice GET COLLECTION + FILTER)
viene eseguita separatamente su due database diversi tramite il motore
JCo Framework reale, e il join vero e proprio (INNER/LEFT/RIGHT/FULL)
viene calcolato qui in Python confrontando le chiavi. 

Costo: perdiamo la possibilità di ottimizzazioni lato motore;
Guadagno: il join funziona in modo affidabile e prevedibile, 
senza dipendere dalla capacità dell'LLM di generare sintassi JOIN 
corretta. 

Vedi anche il commento in QueryExecutor.jsx (frontend) 
che spiega la stessa scelta lato UI.
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
        Esegue JOIN tra due database usando SOLO JCo Framework.

        join_config atteso (costruito dal form "Usa JOIN tra database"
        nella sidebar del frontend, vedi DatabaseSelector.jsx):
          {
            'db1': <nome database 1>,
            'db2': <nome database 2>,
            'joinType': 'INNER' | 'LEFT' | 'RIGHT' | 'FULL',
            'joinKey': <campo chiave su db1, es. '.user_id'>,
            'db2JoinKey': <campo chiave su db2, es. '.id'>
          }
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
            # STEP 1: Esegui su Database 1
            join_logger.info(f"⚡ Esecuzione su {db1_name}...")
            self.db_registry.set_current_database(db1_name)
            
            join_logger.info(f"DEBUG - Creando executor JCo per db={db1_name}")
            # NOTA: "jco_framework" è passato come stringa letterale invece
            # che come ExecutorType.JCO_FRAMEWORK — funziona comunque perché
            # ExecutorFactory.create_executor() accetta anche stringhe e le
            # converte da sé.
            # NOTA 2: mongo_uri è hardcoded a localhost:27017 — se un giorno
            # ti serve fare JOIN con un database MongoDB non locale, questo
            # andrebbe reso configurabile (es. letto da db_registry, che
            # l'URI reale del database ce l'ha già).
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
            
            # STEP 2: Esegui su Database 2
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
            
            # DEBUG: Stampa i primi record
            if results_db1:
                join_logger.info(f"🔍 SAMPLE DB1 doc: {results_db1[0]}")
                join_logger.info(f"🔍 SAMPLE DB1 key ('{join_key_db1}'): {self._extract_join_key(results_db1[0], join_key_db1)}")
            
            if results_db2:
                join_logger.info(f"🔍 SAMPLE DB2 doc: {results_db2[0]}")
                join_logger.info(f"🔍 SAMPLE DB2 key ('{join_key_db2}'): {self._extract_join_key(results_db2[0], join_key_db2)}")

            # STEP 3: Merge basato su join key
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
        Estrae il valore della chiave da un documento, seguendo un path
        con notazione a punti (es. '.indirizzo.città' → doc['indirizzo']['città']).

        Caso speciale: se il campo richiesto è 'id' e il documento non ce
        l'ha con quel nome esatto, prova 'user_id' e poi '_id' prima di
        arrendersi. Esiste perché nei dataset di esempio usati per i test
        (es. users/orders) lo stesso concetto di "chiave utente" è
        chiamato in modo diverso a seconda della collection — questo
        fallback permette di fare JOIN tra collection con schema/naming
        leggermente diverso senza dover normalizzare i dati a monte.
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
        Merge dei risultati basato su join key, con la stessa semantica
        di un JOIN SQL (implementata a mano, non delegata a MongoDB/JCo):

        - INNER: solo le coppie di documenti che hanno la chiave in
          comune su entrambi i database. Se una chiave non ha match
          sull'altro lato, il documento sparisce dal risultato.
        - LEFT: tutti i documenti di db1, con il documento di db2
          agganciato se c'è un match (altrimenti quel lato è None).
        - RIGHT: speculare a LEFT, ma partendo da db2 (tutti i documenti
          di db2, db1 agganciato se c'è match).
        - FULL: unione di LEFT e RIGHT — tutti i documenti di entrambi i
          lati, con l'altro lato a None dove non c'è corrispondenza.

        Ogni relazione (1:1, 1:N, N:N) è supportata perché db2_index
        raggruppa TUTTI i documenti di db2 che condividono la stessa
        chiave (setdefault(...).append(...)), non solo il primo trovato —
        quindi un doc1 con più match su db2 genera più righe nel merge,
        una per ogni combinazione (comportamento equivalente a un JOIN
        SQL classico, non a un "primo match vince").

        Ogni riga del risultato ha la forma:
          {
            "<nome db1>": <documento o None>,
            "<nome db2>": <documento o None>,
            "_join_key": <valore della chiave usata per l'aggancio>,
            "_source": [<quali database hanno contribuito a questa riga>]
          }
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