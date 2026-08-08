"""
Test suite - Verifica comandi JCoQL via API
Questo test invia query reali al server e verifica se vengono accettate o rifiutate.

IMPORTANTE: Il server deve essere in running (uvicorn main:app --reload)
"""
import logging
import requests
import json
import time
from datetime import datetime

#SETUP LOGGING
# Configura il logger per questo modulo
test_logger = logging.getLogger('command_test')
test_logger.setLevel(logging.DEBUG)

# Handler console - mostra i messaggi a schermo
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
# Formato: timestamp - logger_name - level - messaggio
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(formatter)
test_logger.addHandler(console_handler)


class JCoQLCommandTester:
    """
    Testa comandi JCoQL inviando query reali al server.
    
    Ogni test:
    1. Invia una query al server via HTTP POST
    2. Riceve la risposta JSON
    3. Verifica se la query è stata accettata (is_valid: true/false)
    4. Registra il risultato
    
    Questo approccio è REALE e testa il sistema come lo usa l'utente.
    """
    
    def __init__(self, server_url="http://127.0.0.1:8000"):
        """
        Inizializza il tester.
        
        Args:
            server_url: URL del server JCoQL (default: localhost:8000)
        """
        # URL base del server
        self.server_url = server_url
        # Endpoint per generare query
        self.api_endpoint = f"{server_url}/api/generate"
        # Lista per memorizzare tutti i risultati
        self.results = []
        
        test_logger.info(f"Inizializzazione tester con server: {self.server_url}")
        
        # Verifica se il server è disponibile
        try:
            # Fa un ping al server
            response = requests.get(f"{self.server_url}/docs", timeout=5)
            if response.status_code == 200:
                test_logger.info("✅ Server raggiungibile")
            else:
                test_logger.warning("⚠️  Server risponde ma con status code diverso da 200")
        except requests.ConnectionError:
            test_logger.error("❌ ERRORE: Server non raggiungibile!")
            test_logger.error("   Assicurati di aver avviato: uvicorn main:app --reload")
            raise
    
    def test_command(self, command_name: str, nl_query: str) -> dict:
        # Pausa di 4.5 secondi per rispettare il limite di 15 req/min del Free Tier
        time.sleep(4.5)
        """
        Testa un comando inviando una query in linguaggio naturale al server.
        
        Il server convertirà la query naturale in JCoQL e la validerà.
        Se il comando è supportato, is_valid sarà True.
        Se il comando non è supportato, il parser lo bloccherà e is_valid sarà False.
        
        Args:
            command_name: Nome descrittivo del test (es: "FILTER_SIMPLE")
            nl_query: Query in linguaggio naturale (es: "Hotel a Milano con rating > 4")
        
        Returns:
            Dictionary con i risultati:
            {
                "command": nome del test,
                "nl_query": query naturale inviata,
                "jcoql_query": query JCoQL generata dal LLM,
                "valid": True se parser ha accettato, False altrimenti,
                "status": "✅ PASS" o "❌ FAIL",
                "reason": motivo del fallimento (se presente)
            }
        """
        test_logger.info(f"\n{'='*70}")
        test_logger.info(f"🧪 TEST: {command_name}")
        test_logger.info(f"Query naturale: '{nl_query}'")
        test_logger.info(f"{'='*70}")
        
        try:
            # Prepara il body della richiesta
            # Invia la query naturale al server
            payload = {
                "nl_query": nl_query,
                "max_retries": 3  # Permetti al LLM 3 tentativi se fallisce
            }
            
            # Invia POST request al server
            response = requests.post(
                self.api_endpoint,
                json=payload,
                timeout=10
            )
            
            # Verifica che la richiesta sia andata a buon fine
            if response.status_code != 200:
                # Se il server ritorna errore HTTP
                test_logger.error(f"❌ HTTP Error: {response.status_code}")
                result = {
                    "command": command_name,
                    "nl_query": nl_query,
                    "jcoql_query": None,
                    "valid": False,
                    "status": "❌ ERROR",
                    "reason": f"HTTP {response.status_code}: {response.text}"
                }
                self.results.append(result)
                return result
            
            # Parsa la risposta JSON
            data = response.json()
            
            # Estrae i dati importanti dalla risposta
            jcoql_query = data.get('jcoql_query', '')
            is_valid = data.get('is_valid', False)
            errors = data.get('validation_errors', [])
            
            # Determina lo stato del test
            # Se is_valid è True, il comando è supportato
            # Se is_valid è False, il comando è stato rifiutato dal parser
            status = "✅ PASS" if is_valid else "❌ FAIL"
            reason = None
            if not is_valid and errors:
                # Se c'è un errore, lo registra
                reason = errors[0].get('message', 'Unknown error') if isinstance(errors[0], dict) else str(errors[0])
            
            # Crea il risultato
            result = {
                "command": command_name,
                "nl_query": nl_query,
                "jcoql_query": jcoql_query,
                "valid": is_valid,
                "status": status,
                "reason": reason
            }
            
            # Log dei risultati
            test_logger.info(f"Query JCoQL generata: {jcoql_query}")
            test_logger.info(f"Parser validation: {is_valid}")
            test_logger.info(f"Status: {status}")
            if reason:
                test_logger.info(f"Motivo fallimento: {reason}")
            
            # Aggiunge il risultato alla lista
            self.results.append(result)
            return result
            
        except requests.Timeout:
            # Se il server non risponde entro 10 secondi
            test_logger.error("❌ Timeout: Server non ha risposto in tempo")
            result = {
                "command": command_name,
                "nl_query": nl_query,
                "jcoql_query": None,
                "valid": False,
                "status": "❌ TIMEOUT",
                "reason": "Server timeout (>10s)"
            }
            self.results.append(result)
            return result
            
        except Exception as e:
            # Errore generico
            test_logger.error(f"❌ Exception: {e}", exc_info=True)
            result = {
                "command": command_name,
                "nl_query": nl_query,
                "jcoql_query": None,
                "valid": False,
                "status": "❌ ERROR",
                "reason": str(e)
            }
            self.results.append(result)
            return result
    
    def run_all_tests(self):
        """
        Esegui tutti i test di comandi JCoQL.
        
        Testa:
        1. FILTER (dovrebbe funzionare) - filtraggio documenti
        2. GROUP (dovrebbe funzionare) - raggruppamento
        3. SET OPERATIONS (dovrebbe funzionare) - merge/intersect/subtract
        4. GENERATE BUILD (teoricamente valido, praticamente?) - ristrutturazione
        5. ADD FIELDS (teoricamente valido, praticamente?) - aggiunta campi
        6. COMANDI INESISTENTI (dovrebbe fallire) - comandi che non hanno senso
        7. EXPAND (dovrebbe funzionare) - espansione array
        """
        
        test_logger.info("\n" + "="*70)
        test_logger.info("🚀 INIZIO TEST SUITE - VERIFICA COMANDI JCOQL")
        test_logger.info("="*70 + "\n")
        
        # ==================== CATEGORIA 1: FILTER TESTS ====================
        # Questi dovrebbero TUTTI passare in quanto FILTER è un comando base JCoQL
        test_logger.info("\n" + "─"*70)
        test_logger.info("📋 CATEGORIA 1: FILTER (Base - Dovrebbe FUNZIONARE)")
        test_logger.info("─"*70)
        
        # Test 1.1: FILTER semplice con una condizione
        self.test_command(
            "FILTER_SIMPLE",
            "Hotel con rating superiore a 4"
        )
        
        # Test 1.2: FILTER con AND (due condizioni)
        self.test_command(
            "FILTER_AND",
            "Hotel a Milano con rating superiore a 4"
        )
        
        # Test 1.3: FILTER con OR (alternativa tra due condizioni)
        self.test_command(
            "FILTER_OR",
            "Prodotti con prezzo alto o scontati"
        )
        
        # Test 1.4: FILTER con NOT (negazione)
        self.test_command(
            "FILTER_NOT",
            "Hotel che non sono a Milano"
        )
        
        # Test 1.5: FILTER verificando se campo esiste
        self.test_command(
            "FILTER_WITH",
            "Ordini con campo totale"
        )
        
        # Test 1.6: FILTER con DROP (ritorna solo i matching)
        self.test_command(
            "FILTER_DROP",
            "Filtra hotel con rating > 4, mostra solo questi"
        )
        
        # ==================== CATEGORIA 2: GROUP TESTS ====================
        # GROUP PARTITION dovrebbe funzionare per raggruppare documenti
        test_logger.info("\n" + "─"*70)
        test_logger.info("📋 CATEGORIA 2: GROUP PARTITION (Dovrebbe FUNZIONARE)")
        test_logger.info("─"*70)
        
        # Test 2.1: GROUP PARTITION semplice
        self.test_command(
            "GROUP_PARTITION",
            "Raggruppa ordini per stato"
        )
        
        # Test 2.2: GROUP PARTITION con nome alternativo
        self.test_command(
            "GROUP_PARTITION_ALT",
            "Raggruppa prodotti per categoria"
        )
        
        # ==================== CATEGORIA 3: GENERATE BUILD ====================
        # GENERATE BUILD è nella grammatica ufficiale ma il parser custom potrebbe bloccarlo
        test_logger.info("\n" + "─"*70)
        test_logger.info("📋 CATEGORIA 3: GENERATE BUILD (Valido in grammatica, ma?)")
        test_logger.info("─"*70)
        
        # Test 3.1: GENERATE BUILD con selezione campi
        self.test_command(
            "GENERATE_BUILD",
            "Prodotti mostrando solo nome e prezzo"
        )
        
        # Test 3.2: GENERATE BUILD semplice con un solo campo
        self.test_command(
            "GENERATE_BUILD_SIMPLE",
            "Hotel mostrando solo il nome"
        )
        
        # ==================== CATEGORIA 4: ADD FIELDS ====================
        # ADD FIELDS è nella grammatica ufficiale ma il parser custom potrebbe bloccarlo
        test_logger.info("\n" + "─"*70)
        test_logger.info("📋 CATEGORIA 4: ADD FIELDS (Valido in grammatica, ma?)")
        test_logger.info("─"*70)
        
        # Test 4.1: ADD FIELDS per aggiungere nuovo campo
        self.test_command(
            "ADD_FIELDS",
            "Prodotti con un nuovo campo category aggiunto"
        )
        
        # ==================== CATEGORIA 5: COMANDI INESISTENTI ====================
        # Questi comandi NON ESISTONO in JCoQL e dovrebbero TUTTI fallire
        test_logger.info("\n" + "─"*70)
        test_logger.info("📋 CATEGORIA 5: COMANDI INESISTENTI (Dovrebbe FALLIRE)")
        test_logger.info("─"*70)
        
        # Test 5.1: COMPUTE non esiste in JCoQL
        self.test_command(
            "COMPUTE_INVALID",
            "Usa COMPUTE per calcolare il totale degli ordini"
        )
        
        # Test 5.2: REPORT non esiste in JCoQL
        self.test_command(
            "REPORT_INVALID",
            "Genera un report dei prodotti per categoria"
        )
        
        # Test 5.3: TRANSFORM non esiste in JCoQL
        self.test_command(
            "TRANSFORM_INVALID",
            "Trasforma gli utenti aumentando l'eta di 1"
        )
        
        # Test 5.4: PROJECT non esiste in JCoQL
        self.test_command(
            "PROJECT_INVALID",
            "Proietta solo nome e rating degli hotel"
        )
        
        # Test 5.5: SELECT (sintassi SQL) non esiste in JCoQL
        self.test_command(
            "SELECT_INVALID",
            "SELECT nome e prezzo dai prodotti"
        )

        # ==================== CATEGORIA 6: EXPAND ====================
        # EXPAND espande campi array
        test_logger.info("\n" + "─"*70)
        test_logger.info("📋 CATEGORIA 6: EXPAND (Dovrebbe FUNZIONARE)")
        test_logger.info("─"*70)
        
        # Test 6.1: EXPAND per espandere array
        self.test_command(
            "EXPAND",
            "Espandi i servizi degli hotel"
        )
        
        # Genera e RITORNA il report finale
        # FIX: il return era prima del blocco EXPAND, quindi la categoria 6
        # non veniva mai eseguita (codice irraggiungibile). Spostato qui, in
        # fondo, dopo l'ultimo test.
        return self.generate_report()
    
    def generate_report(self):
        """
        Genera report finale dei test.
        
        Conta quanti test hanno passato/fallito/errore
        e mostra un riepilogo dettagliato delle categorie.
        """
        
        test_logger.info("\n" + "="*70)
        test_logger.info("📊 REPORT FINALE - VERIFICA COMANDI JCOQL")
        test_logger.info("="*70)
        
        # Conta i risultati per categoria
        passed = [r for r in self.results if r['status'] == '✅ PASS']
        failed = [r for r in self.results if r['status'] == '❌ FAIL']
        errors = [r for r in self.results if r['status'] not in ['✅ PASS', '❌ FAIL']]
        
        # Mostra statistiche globali
        test_logger.info(f"\n📈 STATISTICHE GLOBALI:")
        test_logger.info(f"   ✅ PASSED: {len(passed)}/{len(self.results)} ({len(passed)*100//len(self.results)}%)")
        test_logger.info(f"   ❌ FAILED: {len(failed)}/{len(self.results)} ({len(failed)*100//len(self.results)}%)")
        test_logger.info(f"   ⚠️  ERROR:  {len(errors)}/{len(self.results)} ({len(errors)*100//len(self.results)}%)")
        
        # Mostra comandi che hanno passato (supportati)
        test_logger.info(f"\n✅ COMANDI SUPPORTATI ({len(passed)}):")
        for r in passed:
            test_logger.info(f"   ✅ {r['command']:20} -> {r['jcoql_query']}")
        
        # Mostra comandi che hanno fallito (bloccati)
        test_logger.info(f"\n❌ COMANDI BLOCCATI ({len(failed)}):")
        for r in failed:
            test_logger.info(f"   ❌ {r['command']:20} -> {r['reason'] if r['reason'] else 'Parser rejected'}")
        
        # Mostra errori di comunicazione
        if errors:
            test_logger.info(f"\n⚠️  ERRORI COMUNICAZIONE ({len(errors)}):")
            for r in errors:
                test_logger.info(f"   ⚠️  {r['command']:20} -> {r['reason']}")
        
        test_logger.info("\n" + "="*70)
        test_logger.info("✅ TEST SUITE COMPLETATO")
        test_logger.info("="*70 + "\n")
        
        # Ritorna il report come dictionary
        return {
            "total": len(self.results),
            "passed": len(passed),
            "failed": len(failed),
            "errors": len(errors),
            "results": self.results,
            "timestamp": datetime.now().isoformat()
        }


# ==================== ENTRY POINT ====================
# Punto di ingresso quando si esegue questo file direttamente
if __name__ == "__main__":
    try:
        # Crea il tester
        tester = JCoQLCommandTester()
        
        # Esegui tutti i test
        report = tester.run_all_tests()
        
        # Mostra risultati finali nel terminale
        print("\n" + "="*70)
        print("📊 RISULTATI FINALI")
        print("="*70)
        print(f"Total tests: {report['total']}")
        print(f"✅ Passed: {report['passed']}")
        print(f"❌ Failed: {report['failed']}")
        print(f"⚠️  Errors: {report['errors']}")
        print("="*70)
        
    except Exception as e:
        print(f"❌ ERRORE FATALE: {e}")
        print("\nAssicurati che:")
        print("1. Il server sia in esecuzione: uvicorn main:app --reload")
        print("2. URL server: http://127.0.0.1:8000")