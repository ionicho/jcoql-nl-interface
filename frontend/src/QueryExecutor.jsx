// ==========================================
// 1. IMPORTAZIONI
// ==========================================
import { useState, useEffect } from 'react';
import axios from 'axios';
import Favorites, { loadFavorites, persistFavorites } from './Favorites';
import './QueryExecutor.css';

// ==========================================
// 2. DEFINIZIONE COMPONENTE
//
// NOTA (14/08) — Ristrutturazione sostanziale su richiesta esplicita:
// - Prima esisteva un secondo input in linguaggio naturale in App.jsx
//   (sopra questo componente), che duplicava esattamente quello qui
//   sotto (stessa chiamata a /api/generate, stesso risultato) — rimosso,
//   questo è ora l'UNICO punto di generazione.
// - Prima l'esito della generazione (valida/invalida, tentativi, errori)
//   si vedeva in App.jsx, mentre i risultati dell'esecuzione si vedevano
//   qui sotto, in due blocchi separati della pagina — ora è un unico
//   pannello di output: la query corrente (editabile, sia che arrivi da
//   NL sia scritta a mano), l'esito della generazione se presente, e i
//   risultati dell'esecuzione, tutti nello stesso posto.
// - handleExecute e handleExecuteDirect erano due funzioni identiche
//   (lo diceva già un commento in questo file) — unificate in una sola,
//   dato che ora c'è un solo pannello query condiviso.
// - Il pulsante "Copia Query" in App.jsx è sparito insieme al blocco che
//   lo conteneva — non aveva più senso da quando la query generata finiva
//   già da sola nel pannello sottostante.
// - (14/08, secondo giro) tolta anche la scelta tra "modalità" NL/Diretta:
//   prima bisognava cambiare tab per vedere l'una o l'altra, ora l'input
//   NL e il pannello query sono sempre entrambi visibili insieme.
// ==========================================
export default function QueryExecutor({ selectedDatabases = [], joinConfig = null, onDisableJoin = () => {} }) {

  // --- STATI DEL COMPONENTE ---
  const [nlQuery, setNlQuery] = useState('');
  const [jcoqlQuery, setJcoqlQuery] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState('');

  // Esito dell'ultima generazione (null se la query attuale è stata
  // scritta a mano o modificata dopo la generazione) — mostrato nel
  // pannello di output unificato insieme alla query.
  const [generationInfo, setGenerationInfo] = useState(null);

  // Preferiti: caricati una volta all'avvio, persistiti ad ogni modifica.
  const [favorites, setFavorites] = useState(() => loadFavorites());

  useEffect(() => {
    persistFavorites(favorites);
  }, [favorites]);

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
    setGenerationInfo(null);

    // Nota: a differenza di handleExecute sotto, questa chiamata a
    // /api/generate non invia joinConfig — il join tra due database
    // avviene solo in fase di esecuzione. Manda però ora anche l'intera
    // lista selectedDatabases (non solo il primo) — necessaria perché
    // l'LLM possa generare correttamente un MERGE multi-database con i
    // nomi VERI dei database selezionati, invece di indovinarli (bug
    // osservato il 14/08: senza questo, l'LLM confondeva nomi di
    // collection con nomi di database).
    try {
      const response = await axios.post('http://localhost:8000/api/generate', {
        nl_query: nlQuery,
        database: selectedDatabases?.[0],
        databases: selectedDatabases || [],
        max_retries: 3
      });

      // Il pannello mostra/modifica la query COMPLETA, USE DB incluso —
      // non solo il comando nudo che restituisce /api/generate. Il
      // database usato qui è lo stesso che il backend usa davvero per
      // generare (selectedDatabases[0], passato sopra). Il backend
      // accetta senza problemi un USE DB già incluso nel testo (verificato:
      // una USE DB ridondante/aggiuntiva non è un errore, "reference has
      // been replaced" al più) — quindi qualunque modifica fatta qui,
      // USE DB compreso, è esattamente ciò che arriva all'executor.
      //
      // FIX: l'LLM a volte genera già di suo un USE DB in testa (imitando
      // pattern come JOIN/GET DICTIONARY, che lo richiedono) — senza
      // questo controllo veniva anteposto un secondo USE DB identico,
      // producendo due righe duplicate.
      const generatedCommand = response.data.jcoql_query || '';
      const targetDb = selectedDatabases?.[0] || 'jcoql_test';
      const alreadyHasUseDb = /^\s*USE\s+DB\b/i.test(generatedCommand);
      setJcoqlQuery(
        generatedCommand
          ? (alreadyHasUseDb ? generatedCommand : `USE DB ${targetDb} ON DEFAULT SERVER;\n${generatedCommand}`)
          : ''
      );
      setGenerationInfo({
        is_valid: response.data.is_valid,
        attempts: response.data.attempts,
        validation_errors: response.data.validation_errors || []
      });

      if (!response.data.is_valid) {
        setError('Query generata non valida — vedi i dettagli sotto.');
      }
    } catch (err) {
      setError('Errore generazione: ' + err.message);
    } finally {
      setIsGenerating(false);
    }
  };

  // Unico handler di esecuzione (prima ce n'erano due identici, uno per
  // modalità — non serviva, il pannello query è condiviso ora).
  const handleExecute = async () => {
    if (!jcoqlQuery.trim()) {
      setError('Nessuna query JCoQL da eseguire');
      return;
    }

    setIsExecuting(true);
    setError('');
    setResults(null);

    try {
      // jcoqlQuery arriva già così com'è nel pannello — se contiene un
      // USE DB (generato automaticamente o scritto/modificato a mano),
      // quello stesso testo, USE DB compreso, è ciò che viene eseguito
      // per davvero: il backend non lo riscrive.
      const response = await axios.post('http://localhost:8000/api/execute', {
        jcoql_query: jcoqlQuery,
        databases: selectedDatabases,
        database_name: selectedDatabases[0],
        join_config: joinConfig
      });

      const data = response.data;
      if (data.success) {
        let parsedResults = data.results;
        if (typeof data.results === 'string') {
          try {
            parsedResults = JSON.parse(data.results);
          } catch (e) {
            console.error('Errore parsing results:', e);
            parsedResults = data.results;
          }
        }
        setResults({ ...data, results: parsedResults });

        // Riallinea il pannello alla query REALMENTE eseguita: per un JOIN
        // nativo data.jcoql_query è già completa (USE DB per entrambi i
        // database inclusi, costruita dal backend); per le altre query
        // ricostruiamo lo stesso USE DB che execute() ha usato davvero
        // (data.database). Così quello che vedi/modifichi qui è sempre
        // esattamente quello che è appena girato sul motore, non più il
        // solo comando nudo restituito dalla generazione.
        // Stesso controllo anti-duplicazione di handleGenerate: data.jcoql_query
        // può già contenere il proprio USE DB (è lo stesso testo che era nel
        // pannello quando hai premuto "Esegui").
        const alreadyHasUseDb = /^\s*USE\s+DB\b/i.test(data.jcoql_query || '');
        const executedFull = (data.join_config || alreadyHasUseDb)
          ? data.jcoql_query
          : `USE DB ${data.database || selectedDatabases[0] || 'N/A'} ON DEFAULT SERVER;\n${data.jcoql_query}`;
        if (data.jcoql_query) setJcoqlQuery(executedFull);
      } else {
        setError('Errore esecuzione: ' + data.error);
      }
    } catch (err) {
      setError('Errore esecuzione: ' + err.message);
    } finally {
      setIsExecuting(false);
    }
  };

  // La query nel pannello è editabile: se l'utente la modifica a mano
  // dopo una generazione, l'esito di validità mostrato non si riferisce
  // più al testo attuale — lo nascondiamo per non mostrare informazioni
  // ormai scorrette.
  const handleQueryEdit = (newText) => {
    setJcoqlQuery(newText);
    if (generationInfo) setGenerationInfo(null);
  };

  const handleSaveFavorite = () => {
    if (!jcoqlQuery.trim()) return;
    const newFavorite = {
      id: Date.now(),
      // Senza più il concetto di "modalità", salviamo qualunque testo NL
      // sia presente al momento del salvataggio, indipendentemente da come
      // si è arrivati alla query JCoQL corrente (generata o scritta a mano).
      nlQuery: nlQuery.trim(),
      jcoqlQuery: jcoqlQuery.trim(),
      timestamp: new Date().toISOString()
    };
    setFavorites([newFavorite, ...favorites]);
  };

  const handleDeleteFavorite = (id) => {
    setFavorites(favorites.filter((f) => f.id !== id));
  };

  const handleLoadFavorite = (fav) => {
    setJcoqlQuery(fav.jcoqlQuery);
    setNlQuery(fav.nlQuery || '');
    setGenerationInfo(null);
    setResults(null);
    setError('');
  };

  // FIX (16/08): "Disattiva JOIN" spegneva solo il meccanismo di
  // costruzione automatica (joinConfig), ma non toccava il testo già nel
  // pannello — se quel testo era già una query JOIN completa (finita lì
  // per il riallineamento post-esecuzione), continuava a essere eseguita
  // come tale anche a JOIN "disattivato", perché il percorso diretto
  // esegue qualunque testo valido gli venga dato, indipendentemente da
  // joinConfig. Il pannello va svuotato insieme alla disattivazione,
  // altrimenti resta un residuo che sembra ignorare la disattivazione.
  const handleDisableJoinClick = () => {
    setJcoqlQuery('');
    setGenerationInfo(null);
    setResults(null);
    setError('');
    onDisableJoin();
  };

  // ==========================================
  // 4. RENDER DELL'INTERFACCIA (JSX)
  // ==========================================
  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">

      {/* --- HEADER ---
          Prima era un riquadro grande con sfondo sfumato (text-3xl) che
          competeva visivamente con il vero titolo dell'app ("JCoQL+
          Natural Language Interface" in alto) — rimpicciolito per
          rispecchiare lo stesso stile/dimensione del titolo "🗄️ Database"
          nella sidebar (18px, blu, riga sotto). */}
      <div>
        <h2 className="qe-header-title">🔍 Query Executor</h2>
        <p className="qe-header-subtitle">
          Genera ed esegui query JCoQL su MongoDB
        </p>
      </div>

      {/* --- AVVISO MODALITÀ JOIN ATTIVA ---
          joinConfig è uno stato "persistente" nella sidebar (resta attivo
          finché non lo si disattiva esplicitamente, anche passando a una
          richiesta che non c'entra nulla col JOIN) — osservato più volte
          durante i test che una query semplice finiva dirottata verso il
          JOIN senza che fosse ovvio perché. Prima l'unico indizio era il
          checkbox nella sidebar, facile da perdere di vista con
          l'attenzione sul pannello principale — questo banner sta proprio
          lì, in cima, e permette di disattivarlo senza tornare in sidebar. */}
      {joinConfig && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg px-4 py-3 flex justify-between items-center gap-3 flex-wrap">
          <p className="text-sm text-amber-800">
            Modalità JOIN attiva: <strong>{joinConfig.db1}</strong> ↔{' '}
            <strong>{joinConfig.db2 || '(database 2 non ancora scelto)'}</strong>.
            Ogni esecuzione da qui userà questo JOIN, anche per una richiesta non correlata.
          </p>
          <button
            onClick={handleDisableJoinClick}
            className="px-3 py-1.5 bg-amber-200 hover:bg-amber-300 text-amber-900 rounded text-xs font-medium transition-colors flex-shrink-0"
          >
            Disattiva JOIN
          </button>
        </div>
      )}

      {/* --- INPUT: LINGUAGGIO NATURALE (unico in tutta l'app, sempre visibile) ---
          Tolta la scelta tra "modalità" — prima costringeva a passare da una
          tab all'altra per vedere l'input NL o il pannello query diretta,
          ora sono entrambi sempre a schermo insieme. */}
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

      {/* --- PANNELLO QUERY UNIFICATO ---
          Sempre visibile (prima appariva/spariva a seconda della modalità
          scelta). Unico posto in tutta l'app dove si vede/modifica la
          query corrente, sia che sia stata generata da NL sia scritta o
          incollata a mano. Sempre editabile: la query generata finisce già
          qui pronta per essere eseguita (o corretta a mano prima di farlo),
          senza bisogno di copiarla da nessuna parte — e allo stesso tempo
          è anche l'input diretto, se preferisci scrivere JCoQL+ a mano. */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex justify-between items-center mb-3 flex-wrap gap-2">
          <label className="block text-sm font-medium text-gray-700">
            Query JCoQL+
          </label>
          <div className="flex items-center gap-2">
            {generationInfo && (
              <>
                <span
                  className={`px-3 py-1 rounded-full text-xs font-medium ${
                    generationInfo.is_valid
                      ? 'bg-green-100 text-green-800'
                      : 'bg-red-100 text-red-800'
                  }`}
                >
                  {generationInfo.is_valid ? '✅ Valida' : '❌ Invalida'}
                </span>
                <span className="text-xs text-gray-500">
                  Tentativi: {generationInfo.attempts}
                </span>
              </>
            )}
            <button
              onClick={handleSaveFavorite}
              disabled={!jcoqlQuery.trim()}
              title="Salva questa query nei preferiti"
              style={{ opacity: jcoqlQuery.trim() ? 1 : 0.5 }}
              className="px-3 py-2 bg-yellow-100 hover:bg-yellow-200 text-yellow-800 rounded-lg text-sm font-medium transition-colors"
            >
              ⭐ Salva
            </button>
            <button
              onClick={handleExecute}
              disabled={isExecuting || !jcoqlQuery.trim()}
              style={{
                backgroundColor: isExecuting ? '#9ca3af' : '#16a34a',
                color: '#ffffff',
                cursor: isExecuting ? 'not-allowed' : 'pointer',
                opacity: isExecuting || !jcoqlQuery.trim() ? 0.7 : 1
              }}
              className="px-4 py-2 rounded-lg font-medium transition-colors shadow-sm"
            >
              {isExecuting ? '⏳ Esecuzione...' : '▶️ Esegui su MongoDB'}
            </button>
          </div>
        </div>

        <textarea
          value={jcoqlQuery}
          onChange={(e) => handleQueryEdit(e.target.value)}
          placeholder="Es: GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Milano' KEEP OTHERS;"
          rows={6}
          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
        />

        {generationInfo && !generationInfo.is_valid && generationInfo.validation_errors.length > 0 && (
          <div className="mt-3 bg-red-50 border border-red-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-red-800 mb-2">⚠️ Errori di Validazione:</h3>
            <ul className="space-y-1">
              {generationInfo.validation_errors.map((err, idx) => (
                <li key={idx} className="text-sm text-red-700">• {err.message}</li>
              ))}
            </ul>
          </div>
        )}

        <p className="mt-2 text-xs text-gray-500">
          💡 Tip: Puoi incollare qui il codice JCoQL per testare modifiche manuali senza usare l&apos;AI.
        </p>
      </div>

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
            <div className="text-sm text-gray-500 flex gap-3 flex-wrap justify-end">
              {/* FIX: prima mostrava solo results.database (un singolo nome,
                  in pratica sempre selectedDatabases[0]) — fuorviante per
                  query che toccano più database (MERGE, join concatenati),
                  dava l'impressione che tutto arrivasse da un solo database.
                  Ora elenca TUTTI i database dichiarati con USE DB nella
                  query realmente eseguita (results.jcoql_query). Non dice
                  da quale DI QUESTI proviene ogni singolo documento (il
                  motore non lo traccia, vedi discussione) — solo quali
                  database sono stati coinvolti in totale. */}
              {(() => {
                const dbs = [...new Set(
                  Array.from(
                    (results.jcoql_query || '').matchAll(/USE\s+DB\s+(\w+)/gi)
                  ).map((m) => m[1])
                )];
                const shown = dbs.length > 0 ? dbs : [results.database || selectedDatabases[0] || 'N/A'];
                return shown.map((db) => (
                  <span key={db} className="inline-block bg-blue-100 text-blue-800 px-3 py-1 rounded">
                    📦 {db}
                  </span>
                ));
              })()}
            </div>
          </div>

          {/* La query realmente eseguita (USE DB incluso) non si ripete più
              qui: dopo un'esecuzione riuscita, handleExecute riallinea già
              il pannello "Query JCoQL+" sopra a questo stesso testo — un
              'unico posto dove vederla/modificarla, non due copie identiche
              in due punti diversi della pagina. */}

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

      {/* --- PREFERITI --- */}
      <Favorites
        favorites={favorites}
        onLoad={handleLoadFavorite}
        onDelete={handleDeleteFavorite}
      />
    </div>
  );
}