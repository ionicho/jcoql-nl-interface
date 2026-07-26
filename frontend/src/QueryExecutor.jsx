// ==========================================
// 1. IMPORTAZIONI
// ==========================================
import { useState } from 'react';
import axios from 'axios';
// RIMOSSO: import { Link } from 'react-router-dom'; -> Non serve più nell'architettura a pagina singola

import './QueryExecutor.css';


// ==========================================
// 2. DEFINIZIONE COMPONENTE
// Riceve (opzionalmente) come Props i database selezionati dal componente padre (MainInterface)
// ==========================================
export default function QueryExecutor({ selectedDatabases = [], joinConfig = null }) {
  
  // --- STATI DEL COMPONENTE ---
  // mode: Gestisce la vista attuale ('nl' per Linguaggio Naturale, 'direct' per query JCoQL manuale)
  const [mode, setMode] = useState('nl'); 
  
  // nlQuery: Memorizza l'input testuale dell'utente in linguaggio naturale
  const [nlQuery, setNlQuery] = useState('');
  
  // jcoqlQuery: Memorizza la query JCoQL (sia quella generata dal backend, sia quella digitata a mano)
  const [jcoqlQuery, setJcoqlQuery] = useState('');
  
  // Stati di caricamento per gestire i bottoni disabilitati e gli spinner visivi
  const [isGenerating, setIsGenerating] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  
  // results: Salva la risposta del database dopo l'esecuzione della query
  const [results, setResults] = useState(null);
  
  // error: Gestisce la visualizzazione di eventuali messaggi di errore a schermo
  const [error, setError] = useState('');

  // ==========================================
  // 3. HANDLERS (FUNZIONI LOGICHE)
  // ==========================================

  /**
   * handleGenerate: 
   * Invia la stringa in linguaggio naturale (nlQuery) al backend FastAPI.
   * Il backend interroga l'LLM e restituisce una query JCoQL formattata.
   */
  const handleGenerate = async () => {
    // Controllo validità: impedisce richieste vuote
    if (!nlQuery.trim()) {
      setError('Inserisci una query in linguaggio naturale');
      return;
    }

    setIsGenerating(true);
    setError('');
    setResults(null); // Pulisce eventuali risultati precedenti

    try {
      const response = await axios.post('http://localhost:8000/api/generate', {
        nl_query: nlQuery,
        max_retries: 3
      });

      // Se la query generata supera i controlli di validazione (es. sintassi ANTLR3)
      if (response.data.is_valid) {
        setJcoqlQuery(response.data.jcoql_query); // Imposta la query nel box di esecuzione
      } else {
        // Mostra gli errori di validazione restituiti dal server
        setError('Query generata non valida: ' + response.data.validation_errors.join(', '));
      }
    } catch (err) {
      setError('Errore generazione: ' + err.message);
    } finally {
      setIsGenerating(false); // Riabilita il bottone indipendentemente dall'esito
    }
  };

  /**
   * handleExecute: 
   * Invia la query JCoQL (jcoqlQuery) appena generata al backend per l'esecuzione su MongoDB.
   * AGGIORNATO: Ora invia anche i database selezionati per evitare il fallback su jcoql_test
   */
  const handleExecute = async () => {
    if (!jcoqlQuery.trim()) {
      setError('Nessuna query JCoQL da eseguire');
      return;
    }

    setIsExecuting(true);
    setError('');

    try {
      console.log('🔍 ESECUZIONE (modalità NL)')
      console.log('selectedDatabases:', selectedDatabases)
      console.log('joinConfig:', joinConfig)
      
      const response = await axios.post('http://localhost:8000/api/execute', {
        jcoql_query: jcoqlQuery,
        databases: selectedDatabases,
        database_name: selectedDatabases[0],
        join_config: joinConfig  // ← AGGIUNGI QUESTA RIGA!
      });

      if (response.data.success) {
        console.log('✅ Risultati ricevuti:', response.data)
        setResults(response.data);
      } else {
        setError('Errore esecuzione: ' + response.data.error);
      }
    } catch (err) {
      setError('Errore esecuzione: ' + err.message);
    } finally {
      setIsExecuting(false);
    }
  };

  /**
   * handleExecuteDirect: 
   * Identica ad handleExecute, ma pensata concettualmente per la modalità "diretta", 
   * dove l'utente scrive o incolla il codice JCoQL a mano.
   */
  const handleExecuteDirect = async () => {
    if (!jcoqlQuery.trim()) {
      setError('Nessuna query JCoQL da eseguire')
      return
    }

    setIsExecuting(true)
    setError('')

    try {
      console.log('🔍 INIZIO ESECUZIONE')
      console.log('selectedDatabases prop ricevuto:', selectedDatabases)
      console.log('joinConfig prop ricevuto:', joinConfig)  // ← AGGIUNGI QUESTO
      console.log('Query:', jcoqlQuery)
      
      const payload = {
        jcoql_query: jcoqlQuery,
        databases: selectedDatabases,
        database_name: selectedDatabases[0],
        join_config: joinConfig  // ← AGGIUNGI QUESTA RIGA!
      }
      
      console.log('📤 Payload inviato al backend:', payload)

      const response = await axios.post(
        'http://localhost:8000/api/execute',
        payload
      )

      console.log('✅ Risposta ricevuta:', response.data)

      if (response.data.success) {
        console.log('📊 Mostrando risultati...')
        setResults(response.data)
        setError('')
      } else {
        console.log('❌ Errore dalla risposta:', response.data.error)
        setError('Errore: ' + response.data.error)
      }
    } catch (err) {
      console.error('❌ ERRORE COMPLETO:', err)
      setError('Errore: ' + err.message)
    } finally {
      setIsExecuting(false)
    }
  }

  // ==========================================
  // 4. RENDER DELL'INTERFACCIA (JSX)
  // ==========================================
  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      
      {/* --- HEADER --- */}
      <div className="bg-gradient-to-r from-blue-600 to-purple-600 text-white p-6 rounded-lg shadow-lg">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold">🔍 Query Executor</h1>
            <p className="mt-2 opacity-90">
              Genera ed esegui query JCoQL su MongoDB
            </p>
          </div>
          {/* RIMOSSO: I vecchi tag <Link> per la navigazione sono stati eliminati per prevenire il crash e snellire la singola pagina */}
        </div>
      </div>

      {/* --- SELETTORE MODALITÀ (TABS) --- */}
      <div className="bg-white rounded-lg shadow-md p-4">
        <div className="flex gap-2">
          <button
            onClick={() => setMode('nl')}
            className={`flex-1 px-4 py-3 rounded-lg font-medium transition ${
              mode === 'nl'
                ? 'bg-blue-600 text-white' // Stile Attivo
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200' // Stile Inattivo
            }`}
          >
            🗣️ Linguaggio Naturale
          </button>
          <button
            onClick={() => setMode('direct')}
            className={`flex-1 px-4 py-3 rounded-lg font-medium transition ${
              mode === 'direct'
                ? 'bg-blue-600 text-white' // Stile Attivo
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200' // Stile Inattivo
            }`}
          >
            ⚡ Query JCoQL Diretta
          </button>
        </div>
      </div>

      {/* --- VISTA: LINGUAGGIO NATURALE --- */}
      {mode === 'nl' && (
        <>
          {/* Box di inserimento testo */}
          <div className="bg-white rounded-lg shadow-md p-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Query in Linguaggio Naturale
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={nlQuery}
                onChange={(e) => setNlQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleGenerate()} // Permette di generare premendo Invio
                placeholder="Es: Hotel a Milano con rating superiore a 4"
                className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                onClick={handleGenerate}
                disabled={isGenerating} // Disabilita durante il caricamento
                className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition"
              >
                {isGenerating ? '⏳ Generazione...' : '🤖 Genera'}
              </button>
            </div>
          </div>

          {/* Box della query JCoQL (visibile solo DOPO la generazione) */}
          {jcoqlQuery && (
            <div className="bg-white rounded-lg shadow-md p-6">
              <div className="flex justify-between items-center mb-3">
                <label className="block text-sm font-medium text-gray-700">
                  Query JCoQL Generata
                </label>
                <button
                  onClick={handleExecute}
                  disabled={isExecuting}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 font-medium transition"
                >
                  {isExecuting ? '⏳ Esecuzione...' : '▶️ Esegui su MongoDB'}
                </button>
              </div>
              <pre className="bg-gray-50 p-4 rounded-lg overflow-x-auto text-sm border border-gray-200">
                {jcoqlQuery}
              </pre>
            </div>
          )}
        </>
      )}

      {/* --- VISTA: QUERY DIRETTA (MANUALE) --- */}
      {mode === 'direct' && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Query JCoQL Diretta
          </label>
          {/* Textarea permette l'inserimento multi-linea */}
          <textarea
            value={jcoqlQuery}
            onChange={(e) => setJcoqlQuery(e.target.value)}
            placeholder="Es: GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Milano' KEEP OTHERS;"
            rows={6}
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
          />
          <div className="mt-3 flex justify-end">
            <button
              onClick={handleExecuteDirect}
              disabled={isExecuting}
              className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 font-medium transition"
            >
              {isExecuting ? '⏳ Esecuzione...' : '▶️ Esegui su MongoDB'}
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-500">
            💡 Tip: Puoi incollare qui il codice JCoQL per testare modifiche manuali senza usare l&apos;AI.
          </p>
        </div>
      )}

      {/* --- GESTIONE AVVISI ED ERRORI GLOBALI --- */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg">
          ⚠️ {error}
        </div>
      )}

      {/* --- SCHEDA DEI RISULTATI DEL DATABASE --- */}
      {results && results.results && Array.isArray(results.results) && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold text-gray-800">
              📊 Risultati ({results.count} documenti)
            </h2>
            <div className="text-sm text-gray-500 flex gap-3">
              <span className="inline-block bg-blue-100 text-blue-800 px-3 py-1 rounded">
                📦 Database: {results.database || selectedDatabases[0] || 'N/A'}
              </span>
            </div>
          </div>

          {results.count === 0 ? (
            <div className="text-center py-8 text-gray-500">
              Nessun risultato trovato
            </div>
          ) : (
            <div className="space-y-4 max-h-96 overflow-y-auto border border-gray-100 rounded p-2 bg-gray-50">
              {results.results.map((doc, index) => (
                <div
                  key={doc._id || index}
                  className="bg-white rounded-lg p-4 border border-gray-200 hover:border-blue-300 transition shadow-sm"
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-xs font-mono text-gray-500">
                      ID: {doc._id}
                    </span>
                    <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                      Documento #{index + 1}
                    </span>
                  </div>
                  <pre className="text-sm overflow-x-auto">
                    {JSON.stringify(doc, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          )}

          {results.mongo_query && (
            <details className="mt-4 text-sm">
              <summary className="cursor-pointer text-gray-600 hover:text-gray-800 font-medium">
                🔍 Visualizza query MongoDB tradotta
              </summary>
              <pre className="mt-2 bg-gray-900 text-green-400 p-3 rounded overflow-x-auto">
                {JSON.stringify(results.mongo_query, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}

      {/* FALLBACK se results è malformato */}
      {results && !Array.isArray(results.results) && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800">
            ⚠️ Errore nella risposta del server:<br/>
            <code>{JSON.stringify(results, null, 2)}</code>
          </p>
        </div>
      )}

      {/* --- SUGGERIMENTI (QUICK EXAMPLES) --- */}
      <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
        <h3 className="font-medium text-blue-900 mb-2">💡 Esempi Rapidi:</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
          {[
            'Hotel a Milano con rating superiore a 4',
            'Prodotti con prezzo tra 100 e 500 euro',
            'Utenti premium attivi',
            'Ristoranti aperti a Roma',
            'Ordini con totale maggiore di 200',
            'Prodotti in sconto maggiore del 20%'
          ].map((example, i) => (
            <button
              key={i}
              onClick={() => {
                setMode('nl'); // Assicura che l'utente sia nella scheda giusta
                setNlQuery(example);
              }}
              className="text-left px-3 py-2 bg-white rounded border border-blue-200 hover:border-blue-400 hover:bg-blue-50 transition shadow-sm"
            >
              • {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}