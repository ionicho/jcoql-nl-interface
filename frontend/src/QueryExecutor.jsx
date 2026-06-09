import { useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';

export default function QueryExecutor() {
  const [mode, setMode] = useState('nl'); // 'nl' o 'direct'
  const [nlQuery, setNlQuery] = useState('');
  const [jcoqlQuery, setJcoqlQuery] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState('');

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
        jcoql_query: jcoqlQuery
      });

      if (response.data.success) {
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

  const handleExecuteDirect = async () => {
    if (!jcoqlQuery.trim()) {
      setError('Inserisci una query JCoQL');
      return;
    }

    setIsExecuting(true);
    setError('');

    try {
      const response = await axios.post('http://localhost:8000/api/execute', {
        jcoql_query: jcoqlQuery
      });

      if (response.data.success) {
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

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-purple-600 text-white p-6 rounded-lg shadow-lg">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold">🔍 Query Executor</h1>
            <p className="mt-2 opacity-90">
              Genera ed esegui query JCoQL su MongoDB
            </p>
          </div>
          <div className="flex gap-2">
            <Link
              to="/"
              className="px-4 py-2 bg-white/20 hover:bg-white/30 text-white rounded-lg transition"
            >
              ← Interfaccia
            </Link>
            <Link
              to="/upload"
              className="px-4 py-2 bg-white text-blue-600 hover:bg-gray-100 rounded-lg font-medium transition"
            >
              📤 Upload Dati
            </Link>
          </div>
        </div>
      </div>

      {/* Mode Selector */}
      <div className="bg-white rounded-lg shadow-md p-4">
        <div className="flex gap-2">
          <button
            onClick={() => setMode('nl')}
            className={`flex-1 px-4 py-3 rounded-lg font-medium transition ${
              mode === 'nl'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            🗣️ Linguaggio Naturale
          </button>
          <button
            onClick={() => setMode('direct')}
            className={`flex-1 px-4 py-3 rounded-lg font-medium transition ${
              mode === 'direct'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            ⚡ Query JCoQL Diretta
          </button>
        </div>
      </div>

      {/* Mode: Natural Language */}
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
                placeholder="Es: Hotel a Milano con rating superiore a 4"
                className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                onClick={handleGenerate}
                disabled={isGenerating}
                className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition"
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

      {/* Mode: Direct JCoQL */}
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
              className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 font-medium transition"
            >
              {isExecuting ? '⏳ Esecuzione...' : '▶️ Esegui su MongoDB'}
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-500">
            💡 Tip: Puoi copiare query generate dall&apos;interfaccia principale
          </p>
        </div>
      )}

      {/* Errori */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg">
          ⚠️ {error}
        </div>
      )}

      {/* Risultati */}
      {results && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold text-gray-800">
              📊 Risultati ({results.count} documenti)
            </h2>
            <span className="text-sm text-gray-500">
              Database: jcoql_test
            </span>
          </div>

          {results.count === 0 ? (
            <div className="text-center py-8 text-gray-500">
              Nessun risultato trovato
            </div>
          ) : (
            <div className="space-y-4 max-h-96 overflow-y-auto">
              {results.results.map((doc, index) => (
                <div
                  key={doc._id || index}
                  className="bg-gray-50 rounded-lg p-4 border border-gray-200 hover:border-blue-300 transition"
                >
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-xs font-mono text-gray-500">
                      ID: {doc._id}
                    </span>
                    <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                      #{index + 1}
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
              <pre className="mt-2 bg-gray-50 p-3 rounded border border-gray-200 overflow-x-auto">
                {JSON.stringify(results.mongo_query, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}

      {/* Quick Examples */}
      <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
        <h3 className="font-medium text-blue-900 mb-2">💡 Esempi Query:</h3>
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
              onClick={() => setNlQuery(example)}
              className="text-left px-3 py-2 bg-white rounded border border-blue-200 hover:border-blue-400 hover:bg-blue-50 transition"
            >
              • {example}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}