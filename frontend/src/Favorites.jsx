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
    console.warn('Error loading favorites:', err);
    return [];
  }
}

export function persistFavorites(favorites) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(favorites));
  } catch (err) {
    console.warn('Error saving favorites:', err);
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
    <div className="bg-yellow-100 rounded-lg shadow-md p-6">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex justify-between items-center text-left bg-yellow-100 appearance-none border-none"
      >
        <span className="text-lg font-bold text-yellow-800">
          ⭐ Favorite Queries ({favorites.length})
        </span>
        <span className="text-gray-400">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="mt-4">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search favorites..."
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#007bff] focus:border-transparent text-sm"
          />

          {favorites.length === 0 ? (
            <p className="text-sm text-gray-500 mt-3 text-center py-4">
              No saved queries yet — use "⭐ Save" after
              generating or writing a query.
            </p>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-gray-500 mt-3 text-center py-4">
              No results for this search.
            </p>
          ) : (
            <div className="mt-3 space-y-2 max-h-80 overflow-y-auto overflow-x-hidden">
              {filtered.map((fav) => (
                <div
                  key={fav.id}
                  className="border border-[#dbeeff] rounded-lg p-3 hover:border-[#8fc4ff] transition"
                >
                  <div className="flex justify-between items-start gap-1">
                    <div className="flex-1 min-w-0">
                      {fav.nlQuery && (
                        <p className="text-sm font-medium text-gray-800 break-words">
                          {fav.nlQuery}
                        </p>
                      )}
                      <pre className="text-xs text-gray-500 mt-1 whitespace-pre-wrap break-all">
                        {fav.jcoqlQuery}
                      </pre>
                    </div>
                    <div className="flex flex-col gap-1 flex-shrink-0">
                      <button
                        onClick={() => onLoad(fav)}
                        title="Load into the executor"
                        className="px-2 py-1 bg-[#e7f3ff] hover:bg-[#cfe8ff] text-[#0056b3] rounded text-xs font-medium transition-colors"
                      >
                        📥
                      </button>
                      <button
                        onClick={() => onDelete(fav.id)}
                        title="Remove from favorites"
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