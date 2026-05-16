#!/usr/bin/env python3
"""
JCO Framework Executor - Versione Funzionante
"""
import os
import subprocess
import tempfile
from pathlib import Path

class JCoFrameworkExecutor:
    def __init__(self, mongo_uri="mongodb://localhost:27017", database="jcoql_test"):
        self.jco_base = Path("C:/Users/nicho/jcoql-project/jco-framework")
        self.data_path = Path("C:/Users/nicho/.data/.zunTestScripts")
        self.mongo_host = mongo_uri.split("//")[1].split(":")[0]
        self.mongo_port = mongo_uri.split(":")[-1].split("/")[0]
        self.database = database
        
        # Verifica cartelle esistano
        self._setup_directories()
    
    def _setup_directories(self):
        """Crea cartelle necessarie"""
        self.data_path.mkdir(parents=True, exist_ok=True)
        (self.data_path.parent / ".zunLogs").mkdir(exist_ok=True)
        (self.data_path.parent / ".zunReports").mkdir(exist_ok=True)
    
    def execute(self, jcoql_query):
        """Esegue query JCoQL tramite JCO Framework"""
        try:
            # 1. Crea file query.jcoql
            query_file = self.data_path / "query.jcoql"
            query_file.write_text(jcoql_query, encoding='utf-8')
            
            # 2. Crea file prolog (può essere vuoto)
            prolog_file = self.data_path / "setup_mongodb.prolog"
            if not prolog_file.exists():
                prolog_file.write_text("% Setup\n", encoding='utf-8')
            
            # 3. Crea file mongodb_connection.properties
            connection_props = self.data_path / "mongodb_connection.properties"
            connection_props.write_text(
                f"mongodb.host={self.mongo_host}\n"
                f"mongodb.port={self.mongo_port}\n"
                f"mongodb.database={self.database}\n"
                f"mongodb.auth=false\n",
                encoding='utf-8'
            )
            
            # 4. Crea file mongodb_test.properties (principale)
            main_props = self.data_path / "mongodb_test.properties"
            main_props.write_text(
                "fileInProlog=setup_mongodb.prolog\n"
                "fileInTest=query.jcoql\n"
                "testName=MongoDB_Query_Test\n"
                "keyPropertyFile=mongodb_connection.properties\n"
                "toScreen=true\n",
                encoding='utf-8'
            )
            
            # 5. Costruisci classpath includendo cache Gradle
            gradle_cache = Path.home() / ".gradle/caches/modules-2/files-2.1"

            # Trova JAR critici per SLF4J (ESCLUDI -sources.jar)
            slf4j_api = [j for j in (gradle_cache / "org.slf4j/slf4j-api").rglob("slf4j-api-*.jar") if "-sources" not in str(j)]
            slf4j_log4j = [j for j in (gradle_cache / "org.slf4j/slf4j-log4j12").rglob("slf4j-log4j12-*.jar") if "-sources" not in str(j)]
            log4j_jar = [j for j in (gradle_cache / "log4j/log4j").rglob("log4j-*.jar") if "-sources" not in str(j)]

            # AGGIUNGI Spring Framework (necessario per JCO!)
            spring_context = [j for j in (gradle_cache / "org.springframework/spring-context").rglob("spring-context-*.jar") if "-sources" not in str(j)]
            spring_core = [j for j in (gradle_cache / "org.springframework/spring-core").rglob("spring-core-*.jar") if "-sources" not in str(j)]
            spring_beans = [j for j in (gradle_cache / "org.springframework/spring-beans").rglob("spring-beans-*.jar") if "-sources" not in str(j)]
            spring_aop = [j for j in (gradle_cache / "org.springframework/spring-aop").rglob("spring-aop-*.jar") if "-sources" not in str(j)]

            print(f"Found SLF4J-API: {len(slf4j_api)} JARs")
            print(f"Found SLF4J-Log4j: {len(slf4j_log4j)} JARs")
            print(f"Found Log4j: {len(log4j_jar)} JARs")
            print(f"Found Spring Context: {len(spring_context)} JARs")
            print(f"Found Spring Core: {len(spring_core)} JARs")

            # Costruisci classpath
            classpath_parts = [
                str(self.jco_base / "jcoql-engine/build/classes/java/main"),
                str(self.jco_base / "jcoql-model/build/classes/java/main"),
                str(self.jco_base / "jcoql-model/lib/*"),
                str(self.jco_base / "jcoql-ds-core/lib/*"),
                str(self.jco_base / "jcoql-engine-mongodb/build/classes/java/main"),
            ]

            # Aggiungi SLF4J (prendi ultima versione, NO sources)
            if slf4j_api:
                classpath_parts.append(str(slf4j_api[-1]))
            if slf4j_log4j:
                classpath_parts.append(str(slf4j_log4j[-1]))
            if log4j_jar:
                classpath_parts.append(str(log4j_jar[-1]))

            # Aggiungi Spring Framework
            if spring_context:
                classpath_parts.append(str(spring_context[-1]))
            if spring_core:
                classpath_parts.append(str(spring_core[-1]))
            if spring_beans:
                classpath_parts.append(str(spring_beans[-1]))
            if spring_aop:
                classpath_parts.append(str(spring_aop[-1]))

            classpath = ";".join(classpath_parts)
            
            # 6. Esegui JcoScriptLauncher
            cmd = [
                'java',
                '-cp', classpath,
                'jco.ql.engine.JcoScriptLauncher',
                str(main_props)
            ]
            
            print(f"Executing: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                cwd=str(self.jco_base),
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )
            
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
            
            # 7. Parse risultati
            if result.returncode == 0:
                return {
                    'success': True,
                    'raw_output': result.stdout,
                    'results': self._parse_output(result.stdout),
                    'executor': 'jco_framework'
                }
            else:
                return {
                    'success': False,
                    'error': result.stderr,
                    'raw_output': result.stdout,
                    'executor': 'jco_framework'
                }
                
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'JCO Framework timeout (>30 seconds)',
                'executor': 'jco_framework'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'executor': 'jco_framework'
            }
    
    def _parse_output(self, output):
        """Parse output JCO per estrarre risultati JSON"""
        # TODO: implementa parsing specifico output JCO
        # Per ora ritorna raw output
        return output
    
    def close(self):
        """Cleanup"""
        pass


# TEST
if __name__ == "__main__":
    executor = JCoFrameworkExecutor()
    
    query = "GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Milano' KEEP OTHERS;"
    
    print("Testing JCO Framework Executor...")
    result = executor.execute(query)
    
    print("\nRESULT:")
    print(f"Success: {result['success']}")
    if result['success']:
        print(f"Output:\n{result['raw_output']}")
    else:
        print(f"Error: {result.get('error', 'Unknown')}")
    
    executor.close()