// ==========================================
// History.jsx — Cronologia query eseguite (automatica)
//
// Stesso pattern di Favorites.jsx: persistenza via localStorage, nessun
// endpoint backend dedicato. Differenza principale: qui le voci vengono
// aggiunte automaticamente da QueryExecutor a ogni esecuzione (riuscita
// o no), non con un pulsante "Salva" premuto a mano — per questo ogni
// voce porta anche un timestamp e l'esito (✅/❌), che nei Preferiti non
// servivano.
//
// Capacità massima: 50 voci (le più vecchie vengono scartate quando si
// supera il limite — vedi handleAddHistory in App.jsx, che fa lo slice).
// ==========================================
import { useState } from 'react';

const STORAGE_KEY = 'jcoql_history';
export const MAX_HISTORY_ENTRIES = 50;

export function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (err) {
    console.warn('Errore caricamento cronologia:', err);
    return [];
  }
}

export function persistHistory(history) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  } catch (err) {
    console.warn('Errore salvataggio cronologia:', err);
  }
}

function formatTimestamp(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch (err) {
    return '';
  }
}

export default function History({ history, onLoad, onDelete, onClear }) {
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(false);

  const filtered = history.filter((item) => {
    const q = search.toLowerCase();
    return (
      (item.nlQuery || '').toLowerCase().includes(q) ||
      (item.jcoqlQuery || '').toLowerCase().includes(q)
    );
  });

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex justify-between items-center text-left"
      >
        <span className="text-lg font-bold text-gray-800">
          🕘 Cronologia Query ({history.length}/{MAX_HISTORY_ENTRIES})
        </span>
        <span className="text-gray-400">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="mt-4">
          <div className="flex gap-2">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Cerca nella cronologia..."
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
            />
            {history.length > 0 && (
              <button
                onClick={onClear}
                title="Cancella tutta la cronologia"
                className="px-3 py-2 bg-red-50 hover:bg-red-100 text-red-700 rounded-lg text-xs font-medium transition-colors flex-shrink-0"
              >
                🗑️ Cancella tutto
              </button>
            )}
          </div>

          {history.length === 0 ? (
            <p className="text-sm text-gray-500 mt-3 text-center py-4">
              Nessuna query eseguita ancora — ogni esecuzione (riuscita o
              no) finisce qui automaticamente.
            </p>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-gray-500 mt-3 text-center py-4">
              Nessun risultato per questa ricerca.
            </p>
          ) : (
            <div className="mt-3 space-y-2 max-h-80 overflow-y-auto overflow-x-hidden">
              {filtered.map((item) => (
                <div
                  key={item.id}
                  className="border border-gray-200 rounded-lg p-3 hover:border-blue-300 transition"
                >
                  <div className="flex justify-between items-start gap-1">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span
                          className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                            item.success
                              ? 'bg-green-100 text-green-800'
                              : 'bg-red-100 text-red-800'
                          }`}
                        >
                          {item.success ? '✅' : '❌'}
                        </span>
                        <span className="text-xs text-gray-400">
                          {formatTimestamp(item.timestamp)}
                        </span>
                        {item.success && item.count !== null && item.count !== undefined && (
                          <span className="text-xs text-gray-400">
                            · {item.count} doc.
                          </span>
                        )}
                        {item.countOnly && (
                          <span className="text-xs text-gray-400">· 📊 solo conteggio</span>
                        )}
                      </div>
                      {item.nlQuery && (
                        <p className="text-sm font-medium text-gray-800 break-words">
                          {item.nlQuery}
                        </p>
                      )}
                      <pre className="text-xs text-gray-500 mt-1 whitespace-pre-wrap break-all">
                        {item.jcoqlQuery}
                      </pre>
                    </div>
                    <div className="flex flex-col gap-1 flex-shrink-0">
                      <button
                        onClick={() => onLoad(item)}
                        title="Carica nell'executor"
                        className="px-2 py-1 bg-blue-100 hover:bg-blue-200 text-blue-800 rounded text-xs font-medium transition-colors"
                      >
                        📥
                      </button>
                      <button
                        onClick={() => onDelete(item.id)}
                        title="Elimina dalla cronologia"
                        className="px-2 py-1 bg-red-50 hover:bg-red-100 text-red-700 rounded text-xs transition-colors"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
