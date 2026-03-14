import { useState } from 'react'
import { QueryClient, QueryClientProvider, useMutation } from '@tanstack/react-query'
import axios from 'axios'

const queryClient = new QueryClient()

const API_BASE_URL = 'http://localhost:8000'

function JCoQLInterface() {
  const [nlQuery, setNlQuery] = useState('')
  const [result, setResult] = useState(null)

  // Mutation for generating JCoQL
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

  // Mutation for validating JCoQL
  const validateMutation = useMutation({
    mutationFn: async (query) => {
      const response = await axios.post(`${API_BASE_URL}/api/validate`, {
        jcoql_query: query
      })
      return response.data
    }
  })

  const handleGenerate = () => {
    if (nlQuery.trim()) {
      generateMutation.mutate(nlQuery)
    }
  }

  const exampleQueries = [
    "Hotel a Milano con rating superiore a 4",
    "Prodotti con prezzo tra 100 e 200 euro",
    "Utenti senza email registrata",
    "Ristoranti a Roma o Firenze",
    "Appartamenti con superficie tra 50 e 100 mq"
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-indigo-600 rounded-lg flex items-center justify-center">
                <span className="text-white text-xl font-bold">J+</span>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">JCoQL+ Interface</h1>
                <p className="text-sm text-gray-500">Natural Language → JCoQL Query</p>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                <span className="text-sm text-gray-600">API Online</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          
          {/* Left Column - Input */}
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow-md p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                📝 Input Linguaggio Naturale
              </h2>
              
              {/* Example Queries */}
              <div className="mb-4">
                <p className="text-sm text-gray-600 mb-2">Esempi rapidi:</p>
                <div className="flex flex-wrap gap-2">
                  {exampleQueries.map((example, idx) => (
                    <button
                      key={idx}
                      onClick={() => setNlQuery(example)}
                      className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-full text-gray-700 transition-colors"
                    >
                      {example.substring(0, 30)}...
                    </button>
                  ))}
                </div>
              </div>

              {/* Input Textarea */}
              <textarea
                value={nlQuery}
                onChange={(e) => setNlQuery(e.target.value)}
                placeholder="Scrivi la tua richiesta in italiano..."
                className="w-full h-32 p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
              />

              {/* Generate Button */}
              <button
                onClick={handleGenerate}
                disabled={generateMutation.isPending || !nlQuery.trim()}
                className="w-full mt-4 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-400 text-white font-medium rounded-lg transition-colors flex items-center justify-center space-x-2"
              >
                {generateMutation.isPending ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    <span>Generazione...</span>
                  </>
                ) : (
                  <>
                    <span>🚀</span>
                    <span>Genera Query JCoQL</span>
                  </>
                )}
              </button>

              {/* Error Display */}
              {generateMutation.isError && (
                <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-800">
                    <strong>Errore:</strong> {generateMutation.error.response?.data?.detail || generateMutation.error.message}
                  </p>
                </div>
              )}
            </div>

            {/* Stats */}
            {result && (
              <div className="bg-white rounded-lg shadow-md p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">📊 Statistiche</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-green-50 rounded-lg">
                    <p className="text-sm text-gray-600">Stato</p>
                    <p className="text-2xl font-bold text-green-600">
                      {result.is_valid ? '✅ Valid' : '❌ Invalid'}
                    </p>
                  </div>
                  <div className="p-4 bg-blue-50 rounded-lg">
                    <p className="text-sm text-gray-600">Tentativi</p>
                    <p className="text-2xl font-bold text-blue-600">{result.attempts}</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right Column - Output */}
          <div className="space-y-6">
            {result ? (
              <>
                {/* Generated Query */}
                <div className="bg-white rounded-lg shadow-md p-6">
                  <h2 className="text-lg font-semibold text-gray-900 mb-4">
                    ⚡ Query JCoQL Generata
                  </h2>
                  <div className="bg-gray-900 rounded-lg p-4 overflow-x-auto">
                    <pre className="text-sm text-green-400 font-mono">
                      {result.jcoql_query}
                    </pre>
                  </div>
                  <button
                    onClick={() => navigator.clipboard.writeText(result.jcoql_query)}
                    className="mt-4 px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm transition-colors"
                  >
                    📋 Copia Query
                  </button>
                </div>

                {/* Validation Errors */}
                {!result.is_valid && result.validation_errors?.length > 0 && (
                  <div className="bg-white rounded-lg shadow-md p-6">
                    <h3 className="text-lg font-semibold text-red-600 mb-4">
                      ⚠️ Errori di Validazione
                    </h3>
                    <ul className="space-y-2">
                      {result.validation_errors.map((error, idx) => (
                        <li key={idx} className="p-3 bg-red-50 rounded-lg text-sm text-red-800">
                          {error.message}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Retrieved Examples */}
                {result.retrieved_examples?.length > 0 && (
                  <div className="bg-white rounded-lg shadow-md p-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">
                      📚 Esempi RAG Utilizzati
                    </h3>
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
              </>
            ) : (
              <div className="bg-white rounded-lg shadow-md p-12 text-center">
                <div className="text-6xl mb-4">🔍</div>
                <h3 className="text-xl font-semibold text-gray-900 mb-2">
                  In attesa di input
                </h3>
                <p className="text-gray-600">
                  Scrivi una richiesta in linguaggio naturale e premi "Genera Query JCoQL"
                </p>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="mt-12 pb-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center text-sm text-gray-500">
            <p>JCoQL+ NL Interface | Tesi Magistrale Università Bergamo</p>
            <p className="mt-1">RAG + LLM (Gemini 2.5 Flash) + ANTLR Parser</p>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <JCoQLInterface />
    </QueryClientProvider>
  )
}