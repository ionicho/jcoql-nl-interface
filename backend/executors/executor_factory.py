#!/usr/bin/env python3
import os
import sys
import json
from enum import Enum
from pathlib import Path

# 1. Configurazione Percorsi
current_folder = Path(__file__).parent.absolute()
if str(current_folder) not in sys.path:
    sys.path.insert(0, str(current_folder))

# 2. Import del traduttore Python
try:
    import python_translator
    # ✅ La classe si chiama JCoQLExecutor
    PythonExecutorClass = python_translator.JCoQLExecutor
    IMPORT_SUCCESS = True
except Exception as e:
    IMPORT_SUCCESS = False
    IMPORT_ERROR = str(e)
    print(f"⚠️ IMPORT ERROR: {e}")

class ExecutorType(Enum):
    PYTHON_TRANSLATOR = "python_translator"
    JCO_FRAMEWORK = "jco_framework"

class ExecutorFactory:
    @staticmethod
    def create_executor(executor_type, **kwargs):
        """
        Crea un'istanza dell'executor richiesto
        
        Args:
            executor_type: ExecutorType enum o stringa
            **kwargs: mongo_uri, database, ecc.
        
        Returns:
            Istanza dell'executor
        """
        # Se viene passata una stringa, convertila a ExecutorType
        if isinstance(executor_type, str):
            executor_type = ExecutorType(executor_type)
        
        if executor_type == ExecutorType.PYTHON_TRANSLATOR or executor_type.value == "python_translator":
            if not IMPORT_SUCCESS:
                raise ImportError(f"Errore import python_translator: {IMPORT_ERROR}")
            
            try:
                # ✅ Parametro si chiama 'database', non 'database_name'
                executor = PythonExecutorClass(
                    mongo_uri=kwargs.get('mongo_uri', 'mongodb://localhost:27017'),
                    database=kwargs.get('database', 'jcoql_test')
                )
                return executor
            except Exception as e:
                print(f"❌ Errore creazione executor: {e}")
                raise
        
        elif executor_type == ExecutorType.JCO_FRAMEWORK or executor_type.value == "jco_framework":
            try:
                from backend.executors.jco_framework_executor_v2 import JCoFrameworkExecutor
                
                executor = JCoFrameworkExecutor(
                    mongo_uri=kwargs.get('mongo_uri', 'mongodb://localhost:27017'),
                    database=kwargs.get('database', 'jcoql_test')  # ← database, non database_name!
                )
                return executor
            except Exception as e:
                print(f"❌ Errore JCo Framework: {e}")
                raise
        
        else:
            raise ValueError(f"Executor type sconosciuto: {executor_type}")
    
    @staticmethod
    def get_available_executors() -> list:
        """Restituisce lista executor disponibili"""
        return [
            {
                'type': 'python_translator',
                'name': 'Python JCoQL→MongoDB Translator',
                'status': 'available',
                'latency': '<100ms',
                'coverage': '90% production queries'
            },
            {
                'type': 'jco_framework',
                'name': 'JCO Framework Official',
                'status': 'not_implemented',
                'latency': '60+ seconds (Gradle)',
                'coverage': '100% theoretical',
                'note': 'Integration ready via Factory Pattern. See INTEGRATION_ANALYSIS.md'
            }
        ]

# Test
if __name__ == "__main__":
    print(f"✅ Cerco i file in: {current_folder}")
    
    if IMPORT_SUCCESS:
        print("\n✅ Modulo 'python_translator' caricato correttamente!")
        try:
            ex = ExecutorFactory.create_executor(ExecutorType.PYTHON_TRANSLATOR)
            print("🚀 Factory pronta per l'uso!")
            ex.close()
        except Exception as e:
            print(f"❌ Errore: {e}")
    else:
        print(f"❌ Errore import: {IMPORT_ERROR}")