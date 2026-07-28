#!/usr/bin/env python3
"""
JCO Framework Executor - Fix Classpath per ClassLoader Resources e gestione dinamica JAR
"""
import os
import re
import subprocess
from pathlib import Path

class JCoFrameworkExecutor:
    def __init__(self, mongo_uri="mongodb://localhost:27017", database="jcoql_test"):
        # Percorsi dinamici basati sulla HOME dell'utente per evitare path assoluti rigidi
        user_home = Path.home()
        self.jco_base = user_home / "jcoql-project" / "jco-framework"
        self.data_path = user_home / ".data" / ".zunTestScripts"
        
        self.mongo_uri = mongo_uri
        self.database_name = database
        
        self._setup_directories()
    
    def _setup_directories(self):
        """Crea le cartelle temporanee di supporto per log, report e script di esecuzione."""
        self.data_path.mkdir(parents=True, exist_ok=True)
        (self.data_path.parent / ".zunLogs").mkdir(exist_ok=True)
        (self.data_path.parent / ".zunReports").mkdir(exist_ok=True)
    
    def _get_latest_jar(self, search_path, pattern):
        """
        Cerca tutti i file JAR corrispondenti al pattern nella directory indicata,
        estrae il numero di versione dal nome del file e restituisce il percorso
        del JAR con la versione più recente (es. seleziona la 4.x.x anziché la 3.x.x).
        """
        jars = [j for j in search_path.rglob(pattern) if "-sources" not in str(j) and "-javadoc" not in str(j)]
        if not jars:
            return None
        
        def extract_version_key(path):
            # Estrae tutti i numeri di versione (es. "4.1.1" -> [4, 1, 1]) per un ordinamento semantico corretto
            match = re.search(r'-(\d+(?:\.\d+)+)', path.name)
            if match:
                return [int(x) for x in match.group(1).split('.')]
            return [0]

        # Ordina in base alla versione estratta ed estrae l'ultima (quella più recente)
        jars_sorted = sorted(jars, key=extract_version_key)
        return str(jars_sorted[-1])

    def execute(self, jcoql_query):
        """Esegui query JCoQL con JCo Framework"""
        try:
            # 1. Scrittura della query JCoQL e del file prolog temporanei
            query_file = self.data_path / "query.jcoql"
            query_file.write_text(jcoql_query, encoding='utf-8')
            
            prolog_file = self.data_path / "setup_mongodb.prolog"
            # ✅ SCRIVI il comando per selezionare il database
            prolog_file.write_text(
                f"USE DATABASE {self.database_name};\n",
                encoding='utf-8'
            )
            
            # 2. Scrittura delle proprietà di connessione al database MongoDB
            conn_props = self.data_path / "mongodb_connection.properties"
            conn_props.write_text(
                f"mongodb.host=localhost\n"
                f"mongodb.port=27017\n"
                f"mongodb.database={self.database_name}\n"  # ← Chiave corretta!
                f"mongodb.uri={self.mongo_uri}\n"
                "mongodb.replicaSet=\n"
                "mongodb.user=\n"
                "mongodb.password=\n"
                "mongodb.useSSL=false\n",
                encoding='utf-8'
            )
            
            # 3. Scrittura delle configurazioni generali per il Launcher Java
            main_props = self.data_path / "mongodb_test.properties"

            # Formattazione percorsi con '/' per compatibilità con l'engine Java su Windows/Unix
            prolog_path_str = str(prolog_file).replace('\\', '/')
            query_path_str = str(query_file).replace('\\', '/')
            conn_path_str = str(conn_props).replace('\\', '/')

            # database nel properties principale
            main_props.write_text(
                f"fileInProlog={prolog_path_str}\n"
                f"fileInTest={query_path_str}\n"
                "testName=PythonAutomatedTest\n"
                f"keyPropertyFile={conn_path_str}\n"
                f"mongodb.database={self.database_name}\n" 
                f"mongodb.uri={self.mongo_uri}\n"            
                "toScreen=true\n",
                encoding='utf-8'
            )
            
            # 4. Costruzione dinamica del Classpath Java isolando le librerie corrette
            gradle_cache = Path.home() / ".gradle/caches/modules-2/files-2.1"

            # Recupero delle dipendenze garantendo la versione più recente
            jar_patterns = [
                (gradle_cache / "org.antlr/antlr-runtime", "antlr-runtime-*.jar"),
                (gradle_cache / "org.slf4j/slf4j-api", "slf4j-api-*.jar"),
                (gradle_cache / "org.slf4j/slf4j-log4j12", "slf4j-log4j12-*.jar"),
                (gradle_cache / "log4j/log4j", "log4j-*.jar"),
                (gradle_cache / "commons-logging/commons-logging", "commons-logging-*.jar"),
                
                # Dipendenze MongoDB
                (gradle_cache / "org.mongodb/bson", "bson-*.jar"),
                (gradle_cache / "org.mongodb/mongodb-driver-core", "mongodb-driver-core-*.jar"),
                (gradle_cache / "org.mongodb/mongodb-driver-sync", "mongodb-driver-sync-*.jar"),
                (gradle_cache / "org.mongodb/mongodb-driver", "mongodb-driver-*.jar"),
                (gradle_cache / "org.mongodb/mongo-java-driver", "mongo-java-driver-*.jar"),
                
                # Jackson (JSON Serializer) -> Aggiunti per risolvere JsonProcessingException
                (gradle_cache / "com.fasterxml.jackson.core/jackson-core", "jackson-core-*.jar"),
                (gradle_cache / "com.fasterxml.jackson.core/jackson-databind", "jackson-databind-*.jar"),
                (gradle_cache / "com.fasterxml.jackson.core/jackson-annotations", "jackson-annotations-*.jar"),
                
                # Dipendenze Spring Framework
                (gradle_cache / "org.springframework/spring-context", "spring-context-*.jar"),
                (gradle_cache / "org.springframework/spring-core", "spring-core-*.jar"),
                (gradle_cache / "org.springframework/spring-beans", "spring-beans-*.jar"),
                (gradle_cache / "org.springframework/spring-aop", "spring-aop-*.jar"),
                (gradle_cache / "org.springframework/spring-jcl", "spring-jcl-*.jar"),
                (gradle_cache / "org.springframework/spring-expression", "spring-expression-*.jar")
            ]

            classpath_parts = [
                # Radice del framework e risorse di configurazione
                str(self.jco_base),
                str(self.jco_base / "config"),

                # Classi compilate e risorse dei moduli del framework JCoQL
                str(self.jco_base / "jcoql-engine/build/classes/java/main"),
                str(self.jco_base / "jcoql-engine/build/resources/main"),
                str(self.jco_base / "jcoql-model/build/classes/java/main"),
                str(self.jco_base / "jcoql-model/build/resources/main"),
                str(self.jco_base / "jcoql-engine-mongodb/build/classes/java/main"),
                str(self.jco_base / "jcoql-engine-mongodb/build/resources/main"),

                # Librerie JAR locali dei singoli moduli
                str(self.jco_base / "jcoql-model/lib/*"),
                str(self.jco_base / "jcoql-ds-core/lib/*"),
            ]

            # Inserimento nel Classpath dei file JAR più recenti individuati nella cache Gradle
            for base_path, pattern in jar_patterns:
                if base_path.exists():
                    latest_jar = self._get_latest_jar(base_path, pattern)
                    if latest_jar:
                        classpath_parts.append(latest_jar)

            # Aggiunta generica dei JAR presenti nelle directory libs del framework
            for libs_dir in self.jco_base.rglob("libs"):
                if libs_dir.is_dir():
                    classpath_parts.append(str(libs_dir / "*"))

            # Assemblaggio finale della stringa Classpath con il separatore di sistema ';' (Windows) o ':' (Linux/Mac)
            classpath_sep = ";" if os.name == "nt" else ":"
            classpath = classpath_sep.join(classpath_parts)
            
            # 5. Definizione del comando di avvio del processo Java
            cmd = [
                        'java',
                        f'-Dmongodb.database={self.database_name}',  # ← AGGIUNGI QUESTA RIGA
                        '-cp', classpath,
                        'jco.ql.engine.JcoScriptLauncher',
                        str(main_props)
                    ]
            
            # 6. Esecuzione del subprocesso con cattura dell'output
            result = subprocess.run(
                cmd,
                cwd=str(self.jco_base),
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )

            # ✅ DEBUG LOGGING - AGGIUNGI QUESTE RIGHE
            print(f"\n{'='*60}")
            print(f"🔍 JCO FRAMEWORK DEBUG")
            print(f"{'='*60}")
            print(f"Database: {self.database_name}")
            print(f"Return code: {result.returncode}")
            print(f"STDOUT length: {len(result.stdout)}")

            # ✅ AGGIUNGI QUESTA RICERCA:
            if "firstBatch" in result.stdout:
                print("✅ 'firstBatch' TROVATO nel output!")
                # Mostra 500 chars PRIMA di firstBatch
                idx = result.stdout.find("firstBatch")
                print(f"\nContext intorno a 'firstBatch':\n{result.stdout[max(0, idx-200):idx+500]}")
            else:
                print("❌ 'firstBatch' NON trovato!")
                print(f"\n📄 FULL STDOUT:\n{result.stdout}")

            print(f"{'='*60}\n")
            
            if result.returncode == 0 and "ECCEZIONE:" not in result.stdout:
                parsed_results = self._parse_output(result.stdout)
                return {
                    'success': True,
                    'raw_output': result.stdout,
                    'results': parsed_results,
                    'doc_count': parsed_results.get('doc_count', 0),
                    'executor': 'jco_framework'
                }
            else:
                return {
                    'success': False,
                    'error': result.stderr or result.stdout,
                    'raw_output': result.stdout,
                    'executor': 'jco_framework'
                }
                
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'JCO Framework timeout (>30 secondi)',
                'executor': 'jco_framework'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'executor': 'jco_framework'
            }
    
    def _parse_output(self, output):
        """Parse output JCO per estrarre i documenti JSON"""
        import re
        import json
        
        # Estrai il firstBatch dal MongoDB command reply
        match = re.search(r'"firstBatch":\s*(\[.*?\])', output, re.DOTALL)
        if match:
            try:
                documents_json = match.group(1)
                documents = json.loads(documents_json)
                # ✅ Ritorna SEMPRE un dizionario
                return {
                    'text': json.dumps(documents, indent=2),
                    'doc_count': len(documents)
                }
            except:
                pass
        
        # Fallback: ritorna testo grezzo
        return {
            'text': output,
            'doc_count': 0
        }