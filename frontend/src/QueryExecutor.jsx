// ==========================================
// 1. IMPORTAZIONI
// ==========================================
import { useState, useEffect } from 'react';
import axios from 'axios';
import './QueryExecutor.css';

// ==========================================
// 2. DEFINIZIONE COMPONENTE
// ==========================================
export default function QueryExecutor({ selectedDatabases = [], joinConfig = null, initialQuery = '' }) {
  
  // --- STATI DEL COMPONENTE ---
  const [mode, setMode] = useState('nl'); 
  const [nlQuery, setNlQuery] = useState('');
  const [jcoqlQuery, setJcoqlQuery] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState('');

  // FIX: quando arriva una nuova query generata dal pannello "Input Linguaggio Naturale"
  // in App.jsx (prop initialQuery), popola jcoqlQuery e passa alla tab "Query JCoQL Diretta"
  // cosi' l'utente puo' eseguirla subito, senza doverla ricopiare a mano.
  useEffect(() => {
    if (initialQuery) {
      setJcoqlQuery(initialQuery);
      setMode('direct');
    }
  }, [initialQuery]);

  // ==========================================
  // 3. HANDLERS (FUNZIONI LOGICHE)
  // ==========================================

  const handleGenerate = async () => {
    if (!nlQuery.trim()) {
      setError('Inserisci una query in linguaggio naturale');
      return;
    }

    setIsGenerating(true);
    setError('');
    setResults(null); 

    try {
      const response = await axios.post('http://localhost:8000/api/generate', {
        nl_query: nlQuery,
        database: selectedDatabases?.[0], 
        max_retries: 3
      });

      if (response.data.is_valid) {
        setJcoqlQuery(response.data.jcoql_query); 
      } else {
        setError('Query generata non valida: ' + response.data.validation_errors.join(', '));
      }
    } catch (err) {
      setError('Errore generazione: ' + err.message);
    } finally {
      setIsGenerating(false); 
    }
  };

  const handleExecute = async () => {
    if (!jcoqlQuery.trim()) {
      setError('Nessuna query JCoQL da eseguire');
      return;
    }

    setIsExecuting(true);
    setError('');

    try {
      const response = await axios.post('http://localhost:8000/api/execute', {
        jcoql_query: jcoqlQuery,
        databases: selectedDatabases,
        database_name: selectedDatabases[0],
        join_config: joinConfig  
      });

      const data = response.data;
      if (data.success) {
        // ✅ Parse results se è una stringa JSON
        let parsedResults = data.results;
        if (typeof data.results === 'string') {
          try {
            parsedResults = JSON.parse(data.results);
          } catch (e) {
            console.error('Errore parsing results:', e);
            parsedResults = data.results;
          }
        }

        // Memorizziamo l'oggetto completo aggiornando il campo results con l'array parsato
        setResults({
          ...data,
          results: parsedResults
        });
      } else {
        setError('Errore esecuzione: ' + data.error);
      }
    } catch (err) {
      setError('Errore esecuzione: ' + err.message);
    } finally {
      setIsExecuting(false);
    }
  };

  const handleExecuteDirect = async () => {
    if (!jcoqlQuery.trim()) {
      setError('Nessuna query JCoQL da eseguire');
      return;
    }

    setIsExecuting(true);
    setError('');

    try {
      const payload = {
        jcoql_query: jcoqlQuery,
        databases: selectedDatabases,
        database_name: selectedDatabases[0],
        join_config: joinConfig  
      };
      
      const response = await axios.post(
        'http://localhost:8000/api/execute',
        payload
      );

      const data = response.data;
      if (data.success) {
        // ✅ Parse results se è una stringa JSON
        let parsedResults = data.results;
        if (typeof data.results === 'string') {
          try {
            parsedResults = JSON.parse(data.results);
          } catch (e) {
            console.error('Errore parsing results:', e);
            parsedResults = data.results;
          }
        }

        // Memorizziamo l'oggetto completo aggiornando il campo results con l'array parsato
        setResults({
          ...data,
          results: parsedResults
        });
        setError('');
      } else {
        setError('Errore: ' + data.error);
      }
    } catch (err) {
      setError('Errore: ' + err.message);
    } finally {
      setIsExecuting(false);
    }
  };

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
        </div>
      </div>

      {/* --- SELETTORE MODALITÀ (TABS) --- */}
      <div className="bg-white rounded-lg shadow-md p-4">
        <div className="flex gap-2">
          <button
            onClick={() => setMode('nl')}
            style={{
              backgroundColor: mode === 'nl' ? '#2563eb' : '#f3f4f6',
              color: mode === 'nl' ? '#ffffff' : '#374151',
            }}
            className="flex-1 px-4 py-3 rounded-lg font-medium transition-colors shadow-sm"
          >
            🗣️ Linguaggio Naturale
          </button>
          <button
            onClick={() => setMode('direct')}
            style={{
              backgroundColor: mode === 'direct' ? '#2563eb' : '#f3f4f6',
              color: mode === 'direct' ? '#ffffff' : '#374151',
            }}
            className="flex-1 px-4 py-3 rounded-lg font-medium transition-colors shadow-sm"
          >
            ⚡ Query JCoQL Diretta
          </button>
        </div>
      </div>

      {/* --- VISTA: LINGUAGGIO NATURALE --- */}
      {mode === 'nl' && (
        <>
          <div className="bg-white rounded-lg shadow-md p-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Query in Linguaggio Naturale
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={nlQuery}
                onChange={(e) => setNlQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleGenerate()} 
                placeholder="Es: Prodotti di elettronica con sconto maggiore del 20%"
                className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                onClick={handleGenerate}
                disabled={isGenerating} 
                style={{
                  backgroundColor: isGenerating ? '#9ca3af' : '#2563eb',
                  color: '#ffffff',
                  cursor: isGenerating ? 'not-allowed' : 'pointer',
                  opacity: isGenerating ? 0.8 : 1
                }}
                className="px-6 py-3 rounded-lg font-medium transition-colors shadow-sm"
              >
                {isGenerating ? '⏳ Generazione...' : '🤖 Genera'}
              </button>
            </div>
          </div>

          {jcoqlQuery && (
            <div className="bg-white rounded-lg shadow-md p-6">
              <div className="flex justify-between items-center mb-3">
                <label className="block text-sm font-medium text-gray-700">
                  Query JCoQL Generata
                </label>
                <button
                  onClick={handleExecute}
                  disabled={isExecuting}
                  style={{
                    backgroundColor: isExecuting ? '#9ca3af' : '#4b5563',
                    color: '#ffffff',
                    cursor: isExecuting ? 'not-allowed' : 'pointer',
                    opacity: isExecuting ? 0.8 : 1
                  }}
                  className="px-4 py-2 rounded-lg font-medium transition-colors shadow-sm"
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
              style={{
                backgroundColor: isExecuting ? '#9ca3af' : '#16a34a',
                color: '#ffffff',
                cursor: isExecuting ? 'not-allowed' : 'pointer',
                opacity: isExecuting ? 0.8 : 1
              }}
              className="px-6 py-3 rounded-lg font-medium transition-colors shadow-sm"
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

          {/* Query JCoQL+ effettivamente eseguita, con il contesto USE DB ricostruito -
              utile per mostrare la sintassi completa così com'è stata inviata al motore.
              Caso speciale: il JOIN applicativo (form "Usa JOIN tra database" in sidebar,
              via join_config) esegue la STESSA query separatamente su due database distinti
              e unisce i risultati in Python - non è un unico script JCoQL+, quindi va
              mostrato come due esecuzioni separate invece di un USE DB fittizio con
              "db1 ⊕ db2" (che non è un nome di database valido). */}
          {results.jcoql_query && results.join_config ? (
            <div className="mb-4">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                📜 Query JCoQL+ Eseguita (JOIN applicativo: stessa query su due database, unita in Python)
              </h3>
              <pre className="bg-gray-900 text-green-400 text-xs font-mono p-3 rounded-lg overflow-x-auto whitespace-pre-wrap">
{`USE DB ${results.join_config.db1 || 'N/A'} ON DEFAULT SERVER;
${results.jcoql_query}

--- eseguita separatamente anche su ---

USE DB ${results.join_config.db2 || 'N/A'} ON DEFAULT SERVER;
${results.jcoql_query}`}
              </pre>
            </div>
          ) : results.jcoql_query && (
            <div className="mb-4">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                📜 Query JCoQL+ Eseguita
              </h3>
              <pre className="bg-gray-900 text-green-400 text-xs font-mono p-3 rounded-lg overflow-x-auto whitespace-pre-wrap">
{`USE DB ${results.database || selectedDatabases[0] || 'N/A'} ON DEFAULT SERVER;
${results.jcoql_query}`}
              </pre>
            </div>
          )}

          {results.text && (
            <div className="mb-4 bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg text-sm">
              ✅ {results.text}
            </div>
          )}

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
                    {doc._id !== undefined && (
                      <span className="text-xs font-mono text-gray-500">
                        ID: {doc._id}
                      </span>
                    )}
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
            'Prodotti di elettronica con sconto maggiore del 20%',
            'Ristoranti aperti con cucina giapponese',
            'Prodotti biologici con rating superiore a 4',
            'Ordini con priorità urgente',
            'Raggruppa i prodotti per categoria',
            'Hotel a Milano'
          ].map((example, i) => (
            <button
              key={i}
              onClick={() => {
                setMode('nl'); 
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