// ==========================================
// Favorites.jsx — Query preferite (linguaggio naturale + JCoQL generata)
//
// Persistenza via localStorage (stesso pattern già usato in App.jsx per
// selectedDatabases/joinConfig) — nessun endpoint backend dedicato, non
// serve: è una lista personale del singolo browser/utente.
// ==========================================
import { useState } from 'react';

const STORAGE_KEY = 'jcoql_favorites';

export function loadFavorites() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (err) {
    console.warn('Errore caricamento preferiti:', err);
    return [];
  }
}

export function persistFavorites(favorites) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(favorites));
  } catch (err) {
    console.warn('Errore salvataggio preferiti:', err);
  }
}

export default function Favorites({ favorites, onLoad, onDelete }) {
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(false);

  const filtered = favorites.filter((fav) => {
    const q = search.toLowerCase();
    return (
      fav.nlQuery.toLowerCase().includes(q) ||
      fav.jcoqlQuery.toLowerCase().includes(q)
    );
  });

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex justify-between items-center text-left"
      >
        <span className="text-lg font-bold text-gray-800">
          ⭐ Query Preferite ({favorites.length})
        </span>
        <span className="text-gray-400">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="mt-4">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cerca nei preferiti..."
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
          />

          {favorites.length === 0 ? (
            <p className="text-sm text-gray-500 mt-3 text-center py-4">
              Nessuna query salvata ancora — usa "⭐ Salva nei preferiti" dopo
              aver generato o scritto una query.
            </p>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-gray-500 mt-3 text-center py-4">
              Nessun risultato per questa ricerca.
            </p>
          ) : (
            <div className="mt-3 space-y-2 max-h-80 overflow-y-auto">
              {filtered.map((fav) => (
                <div
                  key={fav.id}
                  className="border border-gray-200 rounded-lg p-3 hover:border-blue-300 transition"
                >
                  <div className="flex justify-between items-start gap-2">
                    <div className="flex-1 min-w-0">
                      {fav.nlQuery && (
                        <p className="text-sm font-medium text-gray-800 truncate">
                          {fav.nlQuery}
                        </p>
                      )}
                      <pre className="text-xs text-gray-500 mt-1 whitespace-pre-wrap break-all">
                        {fav.jcoqlQuery}
                      </pre>
                    </div>
                    <div className="flex gap-1 flex-shrink-0">
                      <button
                        onClick={() => onLoad(fav)}
                        title="Carica nell'executor"
                        className="px-3 py-1.5 bg-blue-100 hover:bg-blue-200 text-blue-800 rounded text-xs font-medium transition-colors"
                      >
                        📥 Usa
                      </button>
                      <button
                        onClick={() => onDelete(fav.id)}
                        title="Elimina dai preferiti"
                        className="px-2 py-1.5 bg-red-50 hover:bg-red-100 text-red-700 rounded text-xs transition-colors"
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
