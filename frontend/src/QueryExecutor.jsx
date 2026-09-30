// ==========================================
// 1. IMPORTAZIONI
// ==========================================
import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import './QueryExecutor.css';

// ==========================================
// 2. DEFINIZIONE COMPONENTE
//
// Unico componente di generazione ed esecuzione in tutta l'app (non
// duplicarlo altrove — vedi il commento corrispondente in App.jsx): un
// solo pannello di output con la query corrente (editabile, sia che
// arrivi da NL sia scritta a mano), l'esito della generazione se
// presente, e i risultati dell'esecuzione, tutti nello stesso posto.
// ==========================================
export default function QueryExecutor({
  selectedDatabases = [],
  favoriteToLoad = null,
  onSaveFavorite = () => {},
  historyToLoad = null,
  onAddHistory = () => {}
}) {

  // --- STATI DEL COMPONENTE ---
  const [nlQuery, setNlQuery] = useState('');
  const [jcoqlQuery, setJcoqlQuery] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [results, setResults] = useState(null);

  // Modalità "database di grandi dimensioni / risultato non necessario":
  // quando attiva, il backend non accoda il SAVE AS automatico
  // usato per rileggere i documenti dal browser (vedi execute_count_only()
  // in jco_framework_executor_v2.py) - evita il costo di scrittura isolato
  // come collo di bottiglia su collezioni grandi, ma restituisce solo il
  // conteggio, non i documenti. Persiste per query successive nella stessa
  // sessione finché non la si disattiva a mano.
  const [countOnly, setCountOnly] = useState(false);

  // Campo "Query in Linguaggio Naturale": si adatta all'altezza del testo
  // scritto, invece di restare a una riga fissa. Il ref serve per leggere
  // scrollHeight (l'altezza reale del contenuto) e applicarla come nuova
  // altezza — va rifatto ogni volta che nlQuery cambia, non solo quando
  // l'utente digita, perché cambia anche caricando un preferito o con
  // il pulsante "Pulisci" sotto.
  const nlQueryRef = useRef(null);
  useEffect(() => {
    const el = nlQueryRef.current;
    if (!el) return;
    el.style.height = 'auto';
    // +2px di margine: senza, l'altezza calcolata a filo su scrollHeight
    // tagliava visivamente le lettere con parti sopra/sotto la riga di
    // base (p, f, la Q maiuscola che sembrava una O).
    el.style.height = `${el.scrollHeight + 2}px`;
  }, [nlQuery]);
  const [error, setError] = useState('');

  // Esito dell'ultima generazione (null se la query attuale è stata
  // scritta a mano o modificata dopo la generazione) — mostrato nel
  // pannello di output unificato insieme alla query.
  const [generationInfo, setGenerationInfo] = useState(null);

  // Preferiti: stato e persistenza vivono in App.jsx (pannello nella
  // sidebar, sotto "Database"). "Carica" arriva da fuori tramite
  // favoriteToLoad (un segnale, cambia ad ogni click anche sulla stessa
  // preferita — vedi App.jsx);
  // "Salva" resta un'azione locale (il pulsante è qui vicino alla query
  // corrente) ma il risultato va su tramite onSaveFavorite.
  useEffect(() => {
    if (favoriteToLoad) {
      handleLoadFavorite(favoriteToLoad);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [favoriteToLoad]);

  // Cronologia: stesso meccanismo a segnale di favoriteToLoad
  // sopra — cambia ad ogni click su "📥" nella cronologia, anche sulla
  // stessa voce due volte di fila (_loadTs, vedi App.jsx). Le voci di
  // cronologia hanno gli stessi campi jcoqlQuery/nlQuery dei preferiti,
  // quindi riusa lo stesso handler invece di duplicarlo.
  useEffect(() => {
    if (historyToLoad) {
      handleLoadFavorite(historyToLoad);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyToLoad]);

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
    // Senza questo, la vecchia query resta a schermo finché la nuova non
    // arriva dalla risposta, sovrascrivendola senza un intervallo vuoto
    // visibile nel mezzo.
    setJcoqlQuery('');

    // Nota: manda anche l'intera lista selectedDatabases (non solo il primo)
    // — necessaria perché l'LLM possa generare correttamente un MERGE
    // multi-database con i nomi VERI dei database selezionati, invece di
    // indovinarli (senza questo, l'LLM confondeva nomi di collection con
    // nomi di database).
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
        validation_errors: response.data.validation_errors || [],
        // Stesso schema di execution_time_seconds su /api/execute
        generationTimeSeconds: response.data.generation_time_seconds ?? null
      });

      if (!response.data.is_valid) {
        setError('Query generata non valida — vedi i dettagli sopra.');
      }
    } catch (err) {
      // Preferisce il dettaglio vero che il backend manda in
      // err.response.data.detail (es. il caso specifico del limite di
      // quota Gemini, gestito lì con un messaggio chiaro) al messaggio
      // generico di Axios (err.message, es. "Request failed with status
      // code 500"), tornando a quest'ultimo solo se il dettaglio manca.
      setError('Errore generazione: ' + (err.response?.data?.detail || err.message));
    } finally {
      setIsGenerating(false);
    }
  };

  // Cronologia: registra OGNI esecuzione tentata da qui, riuscita
  // o no — a differenza dei Preferiti (salvataggio manuale), l'idea è un
  // log completo di cosa è stato lanciato, per poter ricaricare anche una
  // query fallita e correggerla, non solo rivedere i successi. Se in
  // futuro si preferisce loggare solo i successi, basta non chiamarla nel
  // ramo di errore/catch sotto.
  const recordHistory = (success, extra = {}) => {
    onAddHistory({
      id: Date.now() + Math.random(),
      nlQuery: nlQuery.trim(),
      jcoqlQuery: (extra.executedQuery ?? jcoqlQuery).trim(),
      timestamp: new Date().toISOString(),
      success,
      count: extra.count ?? null,
      countOnly,
      elapsedSeconds: extra.elapsedSeconds ?? null
    });
  };

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
        count_only: countOnly
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

        // Riallinea il pannello alla query REALMENTE eseguita: ricostruiamo
        // lo stesso USE DB che execute() ha usato davvero (data.database),
        // così quello che vedi/modifichi qui è sempre esattamente quello
        // che è appena girato sul motore, non più il solo comando nudo
        // restituito dalla generazione. Stesso controllo anti-duplicazione
        // di handleGenerate: data.jcoql_query può già contenere il proprio
        // USE DB (è lo stesso testo che era nel pannello quando hai
        // premuto "Esegui").
        const alreadyHasUseDb = /^\s*USE\s+DB\b/i.test(data.jcoql_query || '');
        const executedFull = alreadyHasUseDb
          ? data.jcoql_query
          : `USE DB ${data.database || selectedDatabases[0] || 'N/A'} ON DEFAULT SERVER;\n${data.jcoql_query}`;
        if (data.jcoql_query) setJcoqlQuery(executedFull);
        recordHistory(true, { executedQuery: executedFull, count: data.count, elapsedSeconds: data.execution_time_seconds });
      } else {
        setError('Errore esecuzione: ' + data.error);
        recordHistory(false, { elapsedSeconds: data.execution_time_seconds });
      }
    } catch (err) {
      setError('Errore esecuzione: ' + (err.response?.data?.detail || err.message));
      recordHistory(false);
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
      // Salviamo qualunque testo NL sia presente al momento del
      // salvataggio, indipendentemente da come si è arrivati alla query
      // JCoQL corrente (generata o scritta a mano) — vedi HelpGuide per
      // il caso in cui i due box non sono più allineati tra loro.
      nlQuery: nlQuery.trim(),
      jcoqlQuery: jcoqlQuery.trim(),
      timestamp: new Date().toISOString()
    };
    onSaveFavorite(newFavorite);
  };

  const handleLoadFavorite = (fav) => {
    setJcoqlQuery(fav.jcoqlQuery);
    setNlQuery(fav.nlQuery || '');
    setGenerationInfo(null);
    setResults(null);
    setError('');
  };

  // ==========================================
  // 4. RENDER DELL'INTERFACCIA (JSX)
  // ==========================================
  return (
    // Niente p-6 qui: App.jsx racchiude già questo componente in
    // <section className="bg-white rounded-lg shadow p-6"> — con un p-6
    // anche qui il padding raddoppierebbe (48px) sopra "Query Executor",
    // contro il singolo padding di "Database" nella sidebar.
    <div className="max-w-6xl mx-auto space-y-6">

      {/* --- HEADER ---
          Stesso stile/dimensione del titolo "🗄️ Database" nella sidebar
          (18px, blu, riga sotto), per non competere visivamente con il
          vero titolo dell'app ("JCoQL+ Natural Language Interface" in
          alto). */}
      <div>
        <h2 className="qe-header-title">🔍 Query Executor</h2>
        <p className="qe-header-subtitle">
          Genera ed esegui query JCoQL su MongoDB
        </p>
      </div>

      {/* --- INPUT: LINGUAGGIO NATURALE (unico in tutta l'app, sempre visibile) --- */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Query in Linguaggio Naturale
        </label>
        <div className="flex gap-2 items-start">
          <textarea
            ref={nlQueryRef}
            value={nlQuery}
            onChange={(e) => setNlQuery(e.target.value)}
            onKeyDown={(e) => {
              // Invio da solo genera; Shift+Invio va a capo normalmente
              // (comportamento comune per i campi di testo che crescono).
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleGenerate();
              }
            }}
            placeholder="Es: Prodotti di elettronica con sconto maggiore del 20%"
            rows={2}
            className="flex-1 px-4 py-3 leading-relaxed border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#007bff] focus:border-transparent resize-none overflow-y-auto"
            style={{ maxHeight: '200px', minHeight: '60px' }}
          />
          {nlQuery && (
            <button
              type="button"
              onClick={() => setNlQuery('')}
              title="Cancella il testo"
              className="px-4 py-3 rounded-lg font-medium border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
            >
              🗑️ Pulisci
            </button>
          )}
          <button
            onClick={handleGenerate}
            disabled={isGenerating}
            style={{
              backgroundColor: isGenerating ? '#9ca3af' : '#e7f3ff',
              color: isGenerating ? '#ffffff' : '#0056b3',
              cursor: isGenerating ? 'not-allowed' : 'pointer',
              opacity: isGenerating ? 0.8 : 1,
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.25), 0 2px 4px -2px rgba(0, 0, 0, 0.2)',
              border: 'none',
              WebkitAppearance: 'none',
              MozAppearance: 'none',
              appearance: 'none'
            }}
            // Stesse classi Tailwind di ⭐ Salva (py-2 text-sm), non valori
            // px scritti a mano in stile inline (padding/fontSize/
            // lineHeight) — unico modo per essere certi di ottenere
            // ESATTAMENTE la sua stessa altezza invece di ricalcolarla a
            // mano. Solo l'orizzontale (px-6) resta più largo di Salva
            // (px-3).
            className="px-6 py-2 rounded-lg text-sm font-semibold transition-colors"
          >
            {isGenerating ? '⏳ Generazione...' : '✦ Genera'}
          </button>
        </div>
      </div>

      {/* --- PANNELLO QUERY UNIFICATO ---
          Unico posto in tutta l'app dove si vede/modifica la
          query corrente, sia che sia stata generata da NL sia scritta o
          incollata a mano. Sempre editabile: la query generata finisce già
          qui pronta per essere eseguita (o corretta a mano prima di farlo),
          senza bisogno di copiarla da nessuna parte — e allo stesso tempo
          è anche l'input diretto, se preferisci scrivere JCoQL+ a mano. */}
      <div className="bg-white rounded-lg shadow-md p-6">
        {/* Tre righe indipendenti, ognuna sul proprio blocco a piena
            larghezza (niente flex condiviso tra label e pulsanti) — così
            nessun elemento di una riga può
            spingere o far andare a capo quelli di un'altra:
            riga 1 = solo la label "Query JCoQL+";
            riga 2 = Salva / checkbox "Solo conteggio" / Esegui;
            riga 3 = Valida/Tentativi/tempo di generazione, sempre presente
            nel DOM (anche senza generationInfo, vedi minHeight sotto) così
            non collassa/appare a scatto quando si scrive la query a mano
            invece di generarla — resta lì come spazio bianco fisso. */}
        <div className="mb-3">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Query JCoQL+
          </label>
          {/* I tre elementi (checkbox, Salva, Esegui) distribuiti lungo
              tutta la riga, con "Esegui su MongoDB" fino al bordo destro
              del box. */}
          <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
            <label
              className="flex items-center gap-2.5 text-xs text-gray-600 cursor-pointer select-none"
              title="Non salva il risultato in una collezione temporanea per mostrarlo qui - mostra solo il numero di documenti prodotti. Da usare su collezioni grandi (es. JOIN/GROUP su dataset con decine di migliaia di documenti), dove salvare l'intero risultato solo per leggerlo è il vero collo di bottiglia."
            >
              {/* Il gap del flex container non produce spazio visibile
                  qui perché il testo dopo <input/> è un nodo di testo
                  "nudo", non un elemento — avvolto in uno <span> con
                  margin-left esplicito (più affidabile del solo gap su
                  un nodo di testo) per garantire lo spazio. */}
              <input
                type="checkbox"
                checked={countOnly}
                onChange={(e) => setCountOnly(e.target.checked)}
              />
              <span style={{ marginLeft: '6px' }}>Solo conteggio (database grandi)</span>
            </label>
            {jcoqlQuery.trim() && (
              <button
                onClick={handleSaveFavorite}
                title="Salva questa query nei preferiti"
                style={{
                  border: 'none',
                  WebkitAppearance: 'none',
                  MozAppearance: 'none',
                  appearance: 'none',
                  cursor: 'pointer',
                  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.25), 0 2px 4px -2px rgba(0, 0, 0, 0.2)'
                }}
                className="px-3 py-2 bg-yellow-100 hover:bg-yellow-200 text-yellow-800 rounded-lg text-sm font-medium transition-colors"
              >
                ⭐ Salva
              </button>
            )}
            <button
              onClick={handleExecute}
              disabled={isExecuting || !jcoqlQuery.trim()}
              style={{
                backgroundColor: isExecuting ? '#9ca3af' : '#e7f3ff',
                color: isExecuting ? '#ffffff' : '#0056b3',
                cursor: isExecuting ? 'not-allowed' : 'pointer',
                opacity: isExecuting || !jcoqlQuery.trim() ? 0.7 : 1,
                boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.25), 0 2px 4px -2px rgba(0, 0, 0, 0.2)',
                border: 'none',
                WebkitAppearance: 'none',
                MozAppearance: 'none',
                appearance: 'none'
              }}
              // Stesso motivo di ✦ Genera sopra — stesse classi
              // Tailwind di ⭐ Salva (py-2 text-sm) per l'altezza, solo px-5
              // più largo in orizzontale.
              className="px-5 py-2 rounded-lg text-sm font-semibold transition-colors"
            >
              {isExecuting ? '⏳ Esecuzione...' : '► Esegui su MongoDB'}
            </button>
          </div>
          <div
            className="flex items-center gap-4 flex-wrap"
            style={{ minHeight: '26px' }}
          >
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
                {typeof generationInfo.generationTimeSeconds === 'number' && (
                  <span className="text-xs text-gray-500">
                    ⏱️ {generationInfo.generationTimeSeconds}s
                  </span>
                )}
              </>
            )}
          </div>
        </div>

        {/* Bordo grigio e anello blu del focus in un unico bordo che
            cambia solo colore, invece di due livelli distinti (border +
            box-shadow separato) che non combaciano esattamente ai
            bordi. */}
        <textarea
          value={jcoqlQuery}
          onChange={(e) => handleQueryEdit(e.target.value)}
          placeholder="Es: GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Milano' KEEP OTHERS;"
          rows={6}
          className="w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:outline-none focus:border-[#007bff] font-mono text-sm"
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
          💡 Tip: Puoi incollare, modificare o scrivere qui il codice JCoQL per lavorare direttamente, senza passare dall&apos;AI.
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
              {typeof results.execution_time_seconds === 'number' && (
                <span className="ml-2 text-sm font-normal text-gray-500">
                  ⏱️ {results.execution_time_seconds}s
                </span>
              )}
            </h2>
            <div className="text-sm text-gray-500 flex gap-3 flex-wrap justify-end">
              {/* Elenca TUTTI i database dichiarati con USE DB nella query
                  realmente eseguita (results.jcoql_query), non solo
                  results.database (un singolo nome, in pratica sempre
                  selectedDatabases[0]) — quello sarebbe fuorviante per
                  query che toccano più database (MERGE, join concatenati),
                  dando l'impressione che tutto arrivi da un solo database.
                  Non dice da quale DI QUESTI proviene ogni singolo
                  documento (il motore non lo traccia) — solo quali
                  database sono stati coinvolti in totale. */}
              {(() => {
                const dbs = [...new Set(
                  Array.from(
                    (results.jcoql_query || '').matchAll(/USE\s+DB\s+(\w+)/gi)
                  ).map((m) => m[1])
                )];
                const shown = dbs.length > 0 ? dbs : [results.database || selectedDatabases[0] || 'N/A'];
                return shown.map((db) => (
                  <span key={db} className="inline-block bg-[#e7f3ff] text-[#0056b3] px-3 py-1 rounded">
                    📦 {db}
                  </span>
                ));
              })()}
            </div>
          </div>

          {/* La query realmente eseguita (USE DB incluso) non compare qui:
              dopo un'esecuzione riuscita, handleExecute riallinea già il
              pannello "Query JCoQL+" sopra a questo stesso testo — un
              unico posto dove vederla/modificarla, non due copie
              identiche in due punti diversi della pagina. */}

          {results.text && (
            <div className="mb-4 bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg text-sm">
              ✅ {results.text}
            </div>
          )}

          {/* Trasparenza sul risultato: il backend segnala qui
              (results.warning) quando trova riferimenti .item.item.XXX_id
              mai risolti da un JOIN successivo — non un errore, non blocca
              nulla, solo un'informazione in più perché non c'è modo per
              l'utente di sapere a priori se il risultato è completo. */}
          {results.warning && (
            <div className="mb-4 bg-amber-50 border border-amber-300 text-amber-800 px-4 py-3 rounded-lg text-sm">
              ⚠️ {results.warning}
            </div>
          )}

          {results.count === 0 ? (
            <div className="text-center py-8 text-gray-500">
              Nessun risultato trovato
            </div>
          ) : results.results.length === 0 ? (
            // Modalità "solo conteggio": il motore ha prodotto
            // results.count documenti ma non ne è stato letto/mostrato
            // nessuno qui - per come funziona execute_count_only(), è
            // l'esito atteso, non un errore o un caso da confondere con
            // "nessun risultato trovato" sopra (quello è per count === 0).
            <div className="text-center py-8 text-gray-500 text-sm">
              📊 Modalità solo conteggio attiva: {results.count} documenti prodotti dal motore,
              contenuto non recuperato. Se la query conteneva un SAVE AS esplicito verso una
              collezione con un nome a tua scelta, puoi ispezionarla con MongoDB Compass.
            </div>
          ) : (
            <div className="space-y-4 max-h-96 overflow-y-auto border border-gray-100 rounded p-2 bg-gray-50">
              {results.results.map((doc, index) => (
                <div
                  key={doc._id || index}
                  className="bg-white rounded-lg p-4 border border-gray-200 hover:border-[#8fc4ff] transition shadow-sm"
                >
                  <div className="flex justify-between items-start mb-2">
                    {doc._id !== undefined && (
                      <span className="text-xs font-mono text-gray-500">
                        ID: {doc._id}
                      </span>
                    )}
                    <span className="text-xs bg-[#e7f3ff] text-[#0056b3] px-2 py-1 rounded">
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
    </div>
  );
}
