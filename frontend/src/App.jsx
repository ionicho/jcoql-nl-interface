import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query'
import axios from 'axios'
import { useState, useEffect } from 'react'
import { BrowserRouter, Route, Routes, Link } from 'react-router-dom'
import Dashboard from './Dashboard'
import QueryExecutor from './QueryExecutor';
import UploadData from './UploadData';

const queryClient = new QueryClient()
const API_BASE_URL = 'http://localhost:8000'

function JCoQLInterface() {
  const [nlQuery, setNlQuery] = useState('')
  const [result, setResult] = useState(null)
  const [selectedLlm, setSelectedLlm] = useState('gemini')
  const [selectedParser, setSelectedParser] = useState('antlr4_custom')
  const [availableParsers, setAvailableParsers] = useState([])

  // Fetch parsers on mount
  useEffect(() => {
    axios.get(`${API_BASE_URL}/api/parsers`)
      .then(res => {
        setAvailableParsers(res.data.available || [])
        setSelectedParser(res.data.current || 'antlr4_custom')
      })
      .catch(err => {
        console.error('Error fetching parsers:', err)
        setAvailableParsers(['antlr4_custom'])
      })
  }, [])

  // Handler cambio LLM
  const handleLlmChange = async (e) => {
    const newLlm = e.target.value
    try {
      const response = await axios.post(`${API_BASE_URL}/api/set_llm`, null, {
        params: { llm_type: newLlm }
      })
      if (response.data.success) {
        setSelectedLlm(newLlm)
        console.log(`LLM changed to: ${newLlm}`)
      }
    } catch (error) {
      console.error('Error changing LLM:', error)
      alert('Errore nel cambio LLM')
    }
  }

  // Handler cambio parser
  const handleParserChange = async (e) => {
    const newParser = e.target.value
    try {
      const response = await axios.post(`${API_BASE_URL}/api/set_parser`, null, {
        params: { parser_type: newParser }
      })
      if (response.data.success) {
        setSelectedParser(newParser)
        console.log(`Parser changed to: ${response.data.parser}`)
      }
    } catch (error) {
      console.error('Error changing parser:', error)
      alert('Errore nel cambio parser')
    }
  }

  const generateMutation = useMutation({
    mutationFn: async (query) => {
      const response = await axios.post(`${API_BASE_URL}/api/generate`, {
        nl_query: query,
        max_retries: 2
      })
      return response.data
    },
    onSuccess: (data) => {
      setResult(data)
    }
  })

  const exampleQueries = [
    "Hotel a Milano con rating superiore a 4",
    "Prodotti con prezzo tra 100 e 200 euro",
    "Utenti senza email registrata"
  ]

  const handleGenerate = () => {
    if (nlQuery.trim()) {
      generateMutation.mutate(nlQuery)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex justify-between items-center">
            <h1 className="text-2xl font-bold">JCoQL+ Interface</h1>
            
            <div className="flex items-center space-x-4">
              {/* LLM Selector con badge VRAM */}
                <div className="flex items-center space-x-2">
                    <label className="text-sm text-gray-600">LLM:</label>
                    <select 
                      value={selectedLlm} 
                      onChange={handleLlmChange}
                      className="px-3 py-1 bg-white border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      title={`Attuale: ${selectedLlm === 'gemini' ? 'Cloud (Google API)' : 'Locale (Ollama)'}`}
                    >
                      <option value="gemini">☁️ Gemini (Cloud)</option>
                      <option value="llama">🏠 Llama (Locale - 4.7GB)</option>
                      <option value="gemma">🏠 Gemma (Locale - 5.4GB) ⚠️</option>
                    </select>
                  </div>

                  {/* Warning se Gemma selezionato */}
                  {selectedLlm === 'gemma' && (
                    <div className="mt-2 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                      <p className="text-xs text-yellow-800">
                        <strong>⚠️ Nota VRAM:</strong> Gemma richiede 5.4GB. 
                        Se hai appena usato Llama, riavvia Ollama per liberare memoria: 
                        <code className="ml-1 px-1 bg-yellow-100 rounded">ollama stop</code>
                      </p>
                    </div>
                  )}

              {/* Dashboard Link */}
              <Link
                to="/dashboard"
                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm transition-colors"
              >
                📊 Dashboard
              </Link>
              <Link to="/executor" className="...">
                🔍 Query Executor
              </Link>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">📝 Input Linguaggio Naturale</h2>
          
          <div className="mb-4">
            <p className="text-sm text-gray-600 mb-2">Esempi rapidi:</p>
            <div className="flex flex-wrap gap-2">
              {exampleQueries.map((ex, i) => (
                <button
                  key={i}
                  onClick={() => setNlQuery(ex)}
                  className="px-3 py-1 bg-gray-100 hover:bg-gray-200 rounded text-sm transition-colors"
                >
                  {ex.substring(0, 30)}...
                </button>
              ))}
            </div>
          </div>

          <textarea
            value={nlQuery}
            onChange={(e) => setNlQuery(e.target.value)}
            placeholder="Scrivi la tua richiesta in italiano..."
            className="w-full h-32 p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
          />

          <button
            onClick={handleGenerate}
            disabled={generateMutation.isPending || !nlQuery.trim()}
            className="w-full mt-4 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors"
          >
            {generateMutation.isPending ? (
              <span>🔄 Generazione in corso...</span>
            ) : (
              <span>🚀 Genera Query JCoQL</span>
            )}
          </button>

          {generateMutation.isError && (
            <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-800">
                <strong>Errore:</strong> {generateMutation.error.response?.data?.detail || generateMutation.error.message}
              </p>
            </div>
          )}
        </div>

        {result && (
          <div className="mt-6 space-y-4">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">⚡ Query JCoQL Generata</h2>
              <div className="bg-gray-900 rounded-lg p-4">
                <pre className="text-green-400 text-sm font-mono whitespace-pre-wrap">{result.jcoql_query}</pre>
              </div>
              
              <div className="mt-4 flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                    result.is_valid ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  }`}>
                    {result.is_valid ? '✅ Valida' : '❌ Invalida'}
                  </span>
                  <span className="text-sm text-gray-600">
                    Tentativi: {result.attempts}
                  </span>
                </div>
                
                <button
                  onClick={() => navigator.clipboard.writeText(result.jcoql_query)}
                  className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm transition-colors"
                >
                  📋 Copia
                </button>
              </div>
            </div>

            {!result.is_valid && result.validation_errors?.length > 0 && (
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-lg font-semibold text-red-600 mb-4">⚠️ Errori di Validazione</h3>
                <ul className="space-y-2">
                  {result.validation_errors.map((error, idx) => (
                    <li key={idx} className="p-3 bg-red-50 rounded-lg text-sm text-red-800">
                      {error.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {result.retrieved_examples?.length > 0 && (
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">📚 Esempi RAG Utilizzati</h3>
                <div className="space-y-3">
                  {result.retrieved_examples.slice(0, 2).map((example, idx) => (
                    <details key={idx} className="p-3 bg-gray-50 rounded-lg">
                      <summary className="cursor-pointer text-sm font-medium text-gray-700">
                        Esempio {idx + 1}
                      </summary>
                      <pre className="mt-2 text-xs text-gray-600 whitespace-pre-wrap">
                        {example.substring(0, 200)}...
                      </pre>
                    </details>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {!result && !generateMutation.isPending && (
          <div className="mt-6 bg-white rounded-lg shadow p-12 text-center">
            <div className="text-6xl mb-4">🔍</div>
            <h3 className="text-xl font-semibold text-gray-900 mb-2">
              In attesa di input
            </h3>
            <p className="text-gray-600">
              Scrivi una richiesta in linguaggio naturale e premi &quot;Genera Query JCoQL&quot;
            </p>
          </div>
        )}
      </main>

      <footer className="mt-12 pb-8">
        <div className="max-w-7xl mx-auto px-4">
          <div className="text-center text-sm text-gray-500">
            <p>JCoQL+ NL Interface | Tesi Magistrale Università Bergamo</p>
            <p className="mt-1">
              {result && result.llm_used && result.parser_used ? (
                <>
                  <span className="font-medium text-indigo-600">
                    LLM: {result.llm_used.toUpperCase()} 
                    {result.llm_used === 'gemini' ? ' ☁️ Cloud' : ' 🏠 Locale'}
                  </span>
                  {' | '}
                  <span className="font-medium text-green-600">
                    Parser: {result.parser_used}
                  </span>
                </>
              ) : (
                "RAG + Multi-LLM (Cloud/Locale) + Multi-Parser"
              )}
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<JCoQLInterface />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/executor" element={<QueryExecutor />} />
          <Route path="/upload" element={<UploadData />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}