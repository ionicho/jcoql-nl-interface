"""
[STORICO / NON FUNZIONANTE] Primo tentativo di JCO Framework Executor
— conservato come documentazione di un approccio fallito, non usare.

PROBLEMI IDENTIFICATI ALL'EPOCA (dopo 6 approcci testati):
1. Subprocess CLI: Path hardcoded relativi (../../.data/)
2. Invocazione diretta: JcoEngine senza main() pubblico
3. Gradle wrapper: Latenza 60+ secondi (timeout)
4. WebSocket server: Non reattivo, chiude connessione
5. Protocolli terminazione: Server timeout silenzioso

DECISIONE PRESA ALLORA: Usare Python Translator (latenza <100ms) come
fallback, con Factory Pattern pronto per un'integrazione JCO futura.

AGGIORNAMENTO: l'integrazione diretta con JCO Framework è stata poi
raggiunta con un approccio diverso (subprocess mirato, non i 5 tentati
qui) — vedere jco_framework_executor_v2.py, che oggi è l'executor
realmente usato in produzione (ACTIVE_EXECUTOR di default). Questo file
NON è più rappresentativo dello stato del progetto: resta solo come
prova/documentazione dei tentativi falliti iniziali.

Vedere anche: backend/executors/INTEGRATION_ANALYSIS.md (stesso discorso,
anche quel documento andrebbe letto con questa stessa avvertenza).
"""

import json
from pymongo import MongoClient

# NOTA: rinominata da "JCoFrameworkExecutor" a "JCoFrameworkExecutorFailedAttempt"
# perché il nome originale collideva esattamente con la classe attiva e
# funzionante in jco_framework_executor_v2.py, rischiando confusione/import
# sbagliati per chi legge o modifica il codice in futuro.
class JCoFrameworkExecutorFailedAttempt:
    def __init__(self, host="localhost", port=27017, database="jcoql_test"):
        self.host = host
        self.port = port
        self.db_name = database

    def execute(self, jcoql_query: str):
        """
        Simula l'esecuzione J-CO interrogando direttamente MongoDB.
        Supporta query base come: GET COLLECTION nome_collezione;
        """
        try:
            client = MongoClient(self.host, self.port, serverSelectionTimeoutMS=2000)
            db = client[self.db_name]
            
            # Analizziamo la query per capire cosa cercare (molto semplificato)
            # Esempio: "GET COLLECTION hotels;" -> cerchiamo 'hotels'
            query_upper = jcoql_query.upper()
            
            if "GET COLLECTION" in query_upper:
                # Estraiamo il nome della collezione (tutto ciò che segue 'COLLECTION' fino al ';')
                parts = jcoql_query.split("COLLECTION")
                coll_name = parts[1].split(";")[0].strip()
                
                print(f"--- Simulazione J-CO: Recupero documenti da collezione '{coll_name}'...")
                
                # Prendiamo i documenti (limitiamo a 50 per velocità)
                cursor = db[coll_name].find({}, {'_id': 0}).limit(50)
                results = list(cursor)
                
                return {
                    "success": True,
                    "results": results,
                    "count": len(results),
                    "executor": "python_mongo_direct"
                }
            
            return {"success": False, "error": "Query J-CO non supportata dal simulatore Python."}
            
        except Exception as e:
            return {"success": False, "error": f"Errore MongoDB: {str(e)}"}

if __name__ == "__main__":
    executor = JCoFrameworkExecutorFailedAttempt()
    # Test diretto su MongoDB
    print(json.dumps(executor.execute("GET COLLECTION hotels;"), indent=2))