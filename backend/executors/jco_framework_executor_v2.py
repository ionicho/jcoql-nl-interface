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
    
    def _parse_output(self, output):
        try:
            match = re.search(r'"firstBatch":\s*(\[.*?\])', output, re.DOTALL)
            if match:
                docs = json.loads(match.group(1))
                return {'text': json.dumps(docs, indent=2), 'doc_count': len(docs), 'results': docs}
        except:
            pass
        return {'text': output, 'doc_count': 0, 'results': []}
    
    def execute(self, jcoql_query):
        try:
            query_file = self.data_path / "query.jcoql"
            prolog_file = self.data_path / "prolog.jcoql"
            conn_props = self.data_path / "mongodb_connection.properties"
            main_props = self.data_path / "mongodb_test.properties"
            
            # Scrittura del file query (pulita, senza comandi iniettati)[cite: 6]
            query_file.write_text(jcoql_query, encoding='utf-8')
            
            # Scrittura del prolog con la sintassi nativa del framework[cite: 5, 6]
            prolog_content = ""
            prolog_file.write_text(prolog_content, encoding='utf-8')
            
            # URI con database[cite: 6]
            parsed = urlparse(self.mongo_uri)
            mongo_uri_with_db = f"{parsed.scheme or 'mongodb'}://{parsed.netloc}/{self.database_name}"
            
            # Scrittura properties di connessione con mappatura del server localhost[cite: 3, 6]
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
            
            # Scrittura del file principale delle properties[cite: 4, 6]
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
            
            # Classpath[cite: 6]
            gradle_cache = Path.home() / ".gradle/caches/modules-2/files-2.1"
            jar_patterns = [
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
                f'-Dmongodb.database={self.database_name}',
                f'-Dmongo.db={self.database_name}',
                f'-Ddatabase={self.database_name}',
                '-cp', classpath, 
                'jco.ql.engine.JcoScriptLauncher', 
                str(main_props.resolve())
            ]
            
            result = subprocess.run(cmd, cwd=str(self.jco_base), capture_output=True, 
                                  text=True, timeout=30, encoding='utf-8', errors='replace')

            print(f"RAW STDOUT FROM JAVA:\n{result.stdout}\n")
            print(f"\n{'='*60}\nDatabase: {self.database_name}\nQuery: {jcoql_query}\nReturn: {result.returncode}\n{'='*60}\n")
            
            if result.returncode == 0 and "ECCEZIONE:" not in result.stdout:
                parsed = self._parse_output(result.stdout)
                return {'success': True, 'raw_output': result.stdout, 'results': parsed, 
                       'doc_count': parsed.get('doc_count', 0), 'executor': 'jco_framework'}
            else:
                return {'success': False, 'error': result.stderr or "Failed", 
                       'raw_output': result.stdout, 'executor': 'jco_framework'}
        except Exception as e:
            return {'success': False, 'error': str(e), 'executor': 'jco_framework'}