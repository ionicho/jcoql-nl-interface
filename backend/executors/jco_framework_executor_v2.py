#!/usr/bin/env python3
"""JCO Framework Executor - Multi-Database Support"""
import os, re, json, subprocess
from pathlib import Path
from urllib.parse import urlparse

class JCoFrameworkExecutor:
    def __init__(self, mongo_uri="mongodb://localhost:27017", database="jcoql_test"):
        user_home = Path.home()
        self.jco_base = user_home / "jcoql-project" / "jco-framework"
        self.data_path = user_home / ".data" / ".zunTestScripts"
        self.mongo_uri = mongo_uri
        self.database_name = database
        self.data_path.mkdir(parents=True, exist_ok=True)

    def set_database(self, db_name: str):
        """Aggiorna il database corrente per l'executor."""
        if db_name:
            self.database_name = db_name
    
    def _get_latest_jar(self, search_path, pattern):
        jars = [j for j in search_path.rglob(pattern) if "-sources" not in str(j)]
        return str(sorted(jars)[-1]) if jars else None

    def _extract_collection_name(self, jcoql_query):
            """Estrai il nome della collezione dalla query JCoQL"""
            # Pattern: GET COLLECTION nome_collezione
            match = re.search(r'GET\s+COLLECTION\s+(\w+)', jcoql_query, re.IGNORECASE)
            if match:
                return match.group(1)
            return None  # Nessun default

    
    def _parse_output(self, output, jcoql_query):
        """Estrai documenti da MongoDB, applicando il filtro se presente"""
        doc_count = 0
        docs = []
        
        # Ricerca del numero di documenti
        try:
            match = re.search(r'Get Collection.*?executed:\s+(\d+)\s+documents', output, re.DOTALL | re.IGNORECASE)
            if match:
                doc_count = int(match.group(1))
        except Exception as e:
            print(f"[JCoFrameworkExecutor] ⚠️ Errore lettura count: {e}")
        
        collection_name = self._extract_collection_name(jcoql_query)
        if collection_name:
            try:
                from pymongo import MongoClient
                from bson import ObjectId, Decimal128
                
                client = MongoClient(self.mongo_uri)
                db = client[self.database_name]
                collection = db[collection_name]
                
                # Estrai il filtro dalla query JCoQL
                mongo_filter = self._extract_mongo_filter(jcoql_query)
                
                # ✅ Conta TUTTI i documenti che matchano
                if mongo_filter:
                    total_matching = collection.count_documents(mongo_filter)
                else:
                    total_matching = collection.count_documents({})
                
                # ✅ Estrai i primi 100
                if mongo_filter:
                    docs = list(collection.find(mongo_filter).limit(100))
                else:
                    docs = list(collection.find().limit(100))
                
                # Converti ObjectId e Decimal128
                for doc in docs:
                    if '_id' in doc and isinstance(doc['_id'], ObjectId):
                        doc['_id'] = str(doc['_id'])
                    
                    def convert_decimal(obj):
                        if isinstance(obj, dict):
                            for key, val in obj.items():
                                if isinstance(val, Decimal128):
                                    obj[key] = float(val.to_decimal())
                                elif isinstance(val, (dict, list)):
                                    convert_decimal(val)
                        elif isinstance(obj, list):
                            for i, val in enumerate(obj):
                                if isinstance(val, Decimal128):
                                    obj[i] = float(val.to_decimal())
                                elif isinstance(val, (dict, list)):
                                    convert_decimal(val)
                    
                    convert_decimal(doc)
                
                # ✅ Ritorna il numero VERO
                doc_count = total_matching
                
            except Exception as e:
                print(f"[JCoFrameworkExecutor] ❌ MongoDB fallito: {e}")
        
        return {
            'results': docs,
            'doc_count': doc_count, 
            'text': ''
        }

    def _extract_mongo_filter(self, jcoql_query):
        """Estrai il filtro JCOQL con supporto AND/OR"""
        match = re.search(r'WHERE\s+(.+?)\s+KEEP\s+OTHERS', jcoql_query, re.IGNORECASE)
        if not match:
            return None
        
        condition = match.group(1).strip()
        
        # Split per AND/OR
        if ' AND ' in condition.upper():
            parts = re.split(r'\s+AND\s+', condition, flags=re.IGNORECASE)
            filters = []
            for part in parts:
                f = self._parse_single_filter(part.strip())
                if f:
                    filters.append(f)
            if filters:
                return {'$and': filters}
        
        elif ' OR ' in condition.upper():
            parts = re.split(r'\s+OR\s+', condition, flags=re.IGNORECASE)
            filters = []
            for part in parts:
                f = self._parse_single_filter(part.strip())
                if f:
                    filters.append(f)
            if filters:
                return {'$or': filters}
        
        else:
            return self._parse_single_filter(condition)

    def _parse_single_filter(self, condition):
        """Parsa un singolo filtro: .field operator value"""
        field_match = re.match(r'\.([a-zA-Z0-9_.]+)\s*(>=|<=|>|<|=|!=)\s*(.+)', condition)
        if not field_match:
            return None
        
        field_path, operator, value_str = field_match.groups()
        value_str = value_str.strip().strip("'\"")
        
        # Conversione valore (codice existing)
        try:
            if value_str.lower() in ('true', 'false'):
                value = value_str.lower() == 'true'
            elif value_str.lstrip('-').isdigit():
                value = int(value_str)
            elif '.' in value_str:
                try:
                    value = float(value_str)
                except:
                    value = value_str
            else:
                value = value_str
        except:
            value = value_str
        
        mongo_op_map = {'>': '$gt', '<': '$lt', '>=': '$gte', '<=': '$lte', '=': '$eq', '!=': '$ne'}
        mongo_op = mongo_op_map.get(operator)
        if not mongo_op:
            return None
        
        return {field_path: {mongo_op: value}}


    def _get_documents_from_mongodb(self, collection_name, limit=100):
        """Fallback: estrai documenti direttamente da MongoDB se il parsing fallisce"""
        try:
            from pymongo import MongoClient
            from datetime import datetime
            
            client = MongoClient("mongodb://localhost:27017")
            db = client[self.database_name]
            collection = db[collection_name]
            
            # Estrai i primi 'limit' documenti
            docs = list(collection.find().limit(limit))
            
            # CONVERTI TUTTI I CAMPI NON SERIALIZZABILI
            for doc in docs:
                # Converti ObjectId a stringa
                if '_id' in doc:
                    doc['_id'] = str(doc['_id'])
                
                # Converti tutti i datetime a ISO format
                for key, value in doc.items():
                    if isinstance(value, datetime):
                        doc[key] = value.isoformat()
                    elif isinstance(value, dict):
                        # Se è un dict annidato, converti anche i datetime dentro
                        for k, v in value.items():
                            if isinstance(v, datetime):
                                value[k] = v.isoformat()
            
            return docs
        except Exception as e:
            return []


    def _apply_filter_to_results(self, results: list, filter_condition: str) -> list:
        """
        Applica un filtro ai risultati quando il JCo non lo ha fatto
        Supporta: 
        - Singoli: .field > value
        - AND: .field = value AND .other > 5
        - OR: .field = value OR .other != 10
        """
        if not filter_condition or not results:
            return results
        
        # Supporto AND/OR
        if ' AND ' in filter_condition.upper():
            # Splitto per AND e applico tutti i filtri
            conditions = re.split(r'\s+AND\s+', filter_condition, flags=re.IGNORECASE)
            filtered = results
            for condition in conditions:
                filtered = self._apply_single_filter(filtered, condition.strip())
            return filtered
        
        elif ' OR ' in filter_condition.upper():
            # Splitto per OR - ritorna documenti che matchano ALMENO una condizione
            conditions = re.split(r'\s+OR\s+', filter_condition, flags=re.IGNORECASE)
            filtered = []
            for doc in results:
                for condition in conditions:
                    if self._matches_condition(doc, condition.strip()):
                        filtered.append(doc)
                        break  # Documento già matchato, non aggiungerlo di nuovo
            return filtered
        
        else:
            # Singolo filtro
            return self._apply_single_filter(results, filter_condition)
    
    def _apply_single_filter(self, results: list, filter_condition: str) -> list:
        """Applica un singolo filtro a una lista di risultati"""
        if not filter_condition or not results:
            return results
        
        # Parse della condizione: .field OPERATOR value
        match = re.match(r'\.([a-zA-Z0-9_.]+)\s*(>=|<=|>|<|=|!=)\s*(.+)', filter_condition.strip())
        
        if not match:
            return results  # Non riesco a parsare, ritorna tutto
        
        field_path, operator, value_str = match.groups()
        value_str = value_str.strip().strip("'\"")
        
        # Converti il valore
        try:
            if value_str.lower() in ('true', 'false'):
                value = value_str.lower() == 'true'
            elif value_str.lstrip('-').isdigit():
                value = int(value_str)
            elif '.' in value_str:
                try:
                    value = float(value_str)
                except:
                    value = value_str
            else:
                value = value_str
        except:
            value = value_str
        
        # Filtraggio reale
        filtered = []
        
        for doc in results:
            # Navigazione nested: .imdb.rating → doc["imdb"]["rating"]
            doc_value = doc
            for part in field_path.split('.'):
                if isinstance(doc_value, dict) and part in doc_value:
                    doc_value = doc_value[part]
                else:
                    doc_value = None
                    break
            
            if doc_value is None:
                continue  # Campo non trovato, skip
            
            # Applica l'operatore
            try:
                if operator == '>':
                    matches = doc_value > value
                elif operator == '<':
                    matches = doc_value < value
                elif operator == '>=':
                    matches = doc_value >= value
                elif operator == '<=':
                    matches = doc_value <= value
                elif operator == '=':
                    # Supporto array
                    if isinstance(doc_value, list):
                        matches = value in doc_value
                    else:
                        matches = doc_value == value
                elif operator == '!=':
                    # Supporto array
                    if isinstance(doc_value, list):
                        matches = value not in doc_value
                    else:
                        matches = doc_value != value
                else:
                    matches = False
                
                if matches:
                    filtered.append(doc)
            except TypeError:
                # Confronto non possibile (es: stringa > numero)
                pass
        
        return filtered
    
    def _matches_condition(self, doc: dict, filter_condition: str) -> bool:
        """Ritorna True se il documento matcha la condizione"""
        match = re.match(r'\.([a-zA-Z0-9_.]+)\s*(>=|<=|>|<|=|!=)\s*(.+)', filter_condition.strip())
        
        if not match:
            return True  # Se non riesco a parsare, considera come match
        
        field_path, operator, value_str = match.groups()
        value_str = value_str.strip().strip("'\"")
        
        # Converti il valore
        try:
            if value_str.lower() in ('true', 'false'):
                value = value_str.lower() == 'true'
            elif value_str.lstrip('-').isdigit():
                value = int(value_str)
            elif '.' in value_str:
                try:
                    value = float(value_str)
                except:
                    value = value_str
            else:
                value = value_str
        except:
            value = value_str
        
        # Estrai il valore dal documento
        doc_value = doc
        for part in field_path.split('.'):
            if isinstance(doc_value, dict) and part in doc_value:
                doc_value = doc_value[part]
            else:
                return False
        
        # Applica l'operatore
        try:
            if operator == '>':
                return doc_value > value
            elif operator == '<':
                return doc_value < value
            elif operator == '>=':
                return doc_value >= value
            elif operator == '<=':
                return doc_value <= value
            elif operator == '=':
                if isinstance(doc_value, list):
                    return value in doc_value
                else:
                    return doc_value == value
            elif operator == '!=':
                if isinstance(doc_value, list):
                    return value not in doc_value
                else:
                    return doc_value != value
            else:
                return False
        except TypeError:
            return False



    def execute(self, jcoql_query):
        try:
            query_file = self.data_path / "query.jcoql"
            prolog_file = self.data_path / "prolog.jcoql"
            conn_props = self.data_path / "mongodb_connection.properties"
            main_props = self.data_path / "mongodb_test.properties"
            
            # File 1: mongodb_test.properties
            properties_file = os.path.join(os.path.expanduser("~"), ".data", ".zunTestScripts", "mongodb_test.properties")
            properties_content = f"""fileInProlog=C:/Users/nicho/.data/.zunTestScripts/prolog.jcoql
            fileInTest=C:/Users/nicho/.data/.zunTestScripts/query.jcoql
            testName=PythonAutomatedTest
            keyPropertyFile=C:/Users/nicho/.data/.zunTestScripts/mongodb_connection.properties
            default.server=localhost
            server.localhost.uri=mongodb://localhost:27017/{self.database_name}
            server.localhost.database={self.database_name}
            mongodb.uri=mongodb://localhost:27017/{self.database_name}
            mongodb.database={self.database_name}
            mongo.db={self.database_name}
            database={self.database_name}
            toScreen=true
            """

            # File 2: mongodb_connection.properties
            connection_file = os.path.join(os.path.expanduser("~"), ".data", ".zunTestScripts", "mongodb_connection.properties")
            connection_content = f"""mongodb.database={self.database_name}
            mongodb.uri=mongodb://localhost:27017/{self.database_name}
            """

            try:
                with open(properties_file, 'w') as f:
                    f.write(properties_content)
                with open(connection_file, 'w') as f:
                    f.write(connection_content)
            except Exception as e:
                pass

            prolog_content = f"USE DB {self.database_name} ON DEFAULT SERVER;\n"
            prolog_file.write_text(prolog_content, encoding='utf-8')

            query_file.write_text(jcoql_query, encoding='utf-8')
            
            # URI con database
            parsed = urlparse(self.mongo_uri)
            mongo_uri_with_db = f"{parsed.scheme or 'mongodb'}://{parsed.netloc}/{self.database_name}"
            
            # Scrittura properties di connessione
            conn_props.write_text(
                "default.server=localhost\n"
                f"server.localhost.uri={mongo_uri_with_db}\n"
                f"server.localhost.database={self.database_name}\n"
                f"mongo.uri={self.mongo_uri}\n"
                f"mongodb.uri={mongo_uri_with_db}\n"
                f"mongo.db={self.database_name}\n"
                f"mongodb.database={self.database_name}\n"
                f"dbName={self.database_name}\n"
                f"database={self.database_name}\n"
                "mongo.useSSL=false\n",
                encoding='utf-8'
            )
            
            prolog_abs = str(prolog_file.resolve()).replace('\\', '/')
            query_abs = str(query_file.resolve()).replace('\\', '/')
            conn_abs = str(conn_props.resolve()).replace('\\', '/')

            # Scrittura del file principale delle properties
            main_props.write_text(
                f"fileInProlog={prolog_abs}\n"
                f"fileInTest={query_abs}\n"
                "testName=PythonAutomatedTest\n"
                f"keyPropertyFile={conn_abs}\n"
                "default.server=localhost\n"
                f"server.localhost.uri={mongo_uri_with_db}\n"
                f"server.localhost.database={self.database_name}\n"
                f"mongodb.uri={mongo_uri_with_db}\n"
                f"mongodb.database={self.database_name}\n"
                f"mongo.db={self.database_name}\n"
                f"database={self.database_name}\n"
                f"server.localhost.database={self.database_name}\n"
                "toScreen=true\n",
                encoding='utf-8'
            )
            
            # Classpath
            gradle_cache = Path.home() / ".gradle/caches/modules-2/files-2.1"
            jar_patterns = [
                (gradle_cache / "com.fasterxml.jackson.core/jackson-databind", "jackson-databind-*.jar"),
                (gradle_cache / "com.fasterxml.jackson.core/jackson-core", "jackson-core-*.jar"),
                (gradle_cache / "com.fasterxml.jackson.core/jackson-annotations", "jackson-annotations-*.jar"),
                
                # --- ANTLR & LOGGING ---
                (gradle_cache / "org.antlr/antlr-runtime", "antlr-runtime-*.jar"),
                (gradle_cache / "org.slf4j/slf4j-api", "slf4j-api-*.jar"),
                (gradle_cache / "org.slf4j/slf4j-log4j12", "slf4j-log4j12-*.jar"),
                (gradle_cache / "log4j/log4j", "log4j-*.jar"),
                (gradle_cache / "commons-logging/commons-logging", "commons-logging-*.jar"),
                
                # --- MONGODB ---
                (gradle_cache / "org.mongodb/bson", "bson-*.jar"),
                (gradle_cache / "org.mongodb/mongodb-driver-core", "mongodb-driver-core-*.jar"),
                (gradle_cache / "org.mongodb/mongodb-driver-sync", "mongodb-driver-sync-*.jar"),
                (gradle_cache / "org.mongodb/mongodb-driver", "mongodb-driver-*.jar"),
                (gradle_cache / "org.mongodb/mongo-java-driver", "mongo-java-driver-*.jar"),
                
                # --- SPRING FRAMEWORK ---
                (gradle_cache / "org.springframework/spring-core", "spring-core-*.jar"),
                (gradle_cache / "org.springframework/spring-context", "spring-context-*.jar"),
                (gradle_cache / "org.springframework/spring-aop", "spring-aop-*.jar"),
                (gradle_cache / "org.springframework/spring-beans", "spring-beans-*.jar"),
                (gradle_cache / "org.springframework/spring-expression", "spring-expression-*.jar"),
                (gradle_cache / "org.springframework/spring-jcl", "spring-jcl-*.jar"),
            ]
            
            classpath_parts = [
                str(self.jco_base),
                str(self.jco_base / "config"),
                str(self.jco_base / "jcoql-engine/build/classes/java/main"),
                str(self.jco_base / "jcoql-model/build/classes/java/main"),
                str(self.jco_base / "jcoql-engine-mongodb/build/classes/java/main"),
                
                str(self.jco_base / "jcoql-engine/build/libs/*"),
                str(self.jco_base / "jcoql-engine-mongodb/build/libs/*"),
                str(self.jco_base / "jcoql-model/lib/*"),
                str(self.jco_base / "jcoql-ds-core/lib/*"),
                str(self.jco_base / "jcoql-engine/lib/*"),
            ]
            
            for base_path, pattern in jar_patterns:
                if Path(base_path).exists():
                    latest = self._get_latest_jar(Path(base_path), pattern)
                    if latest:
                        classpath_parts.append(latest)
            
            classpath = os.pathsep.join(classpath_parts)
            
            cmd = [
                'java',
                '-Xmx512m',
                f'-Dmongodb.database={self.database_name}',
                f'-Dmongo.db={self.database_name}',
                f'-Ddatabase={self.database_name}',
                '-cp', classpath,
                'jco.ql.engine.JcoScriptLauncher',
                str(main_props.resolve())
            ]
            
            result = subprocess.run(cmd, cwd=str(self.jco_base), capture_output=True,
                                  text=True, timeout=30, encoding='utf-8', errors='replace')
            
            if result.returncode == 0 and "ECCEZIONE:" not in result.stdout:
                parsed = self._parse_output(result.stdout, jcoql_query)
                
                # FALLBACK: Se il FilterExecutor del JCo non ha filtrato (ritorna TUTTI),
                # applica il filtro manualmente in Python
                # Se il filtro ha AND/OR, non applicare il fallback Python
# (MongoDB lo ha già fatto correttamente)
                if "FILTER CASE WHERE" in jcoql_query.upper() and " AND " not in jcoql_query.upper() and " OR " not in jcoql_query.upper():
                    # Estrai la condizione dal filtro
                    filter_match = re.search(r'WHERE\s+(.+?)\s+KEEP\s+OTHERS', jcoql_query, re.IGNORECASE)
                    if filter_match:
                        filter_condition = filter_match.group(1).strip()
                        # Applica il filtro
                        filtered_results = self._apply_filter_to_results(
                            parsed.get('results', []), 
                            filter_condition
                        )
                        parsed['results'] = filtered_results
                
                return {
                    'success': True,
                    'jcoql_query': jcoql_query,
                    'count': parsed.get('doc_count', 0),
                    'results': parsed.get('results', []),
                    'text': parsed.get('text', ''),
                    'executor': 'jco_framework'
                }
            else:
                return {
                    'success': False,
                    'error': result.stderr or "Failed",
                    'executor': 'jco_framework'
                }
        except Exception as e:
            return {'success': False, 'error': str(e), 'executor': 'jco_framework'}