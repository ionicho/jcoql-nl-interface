/**
 * DatabaseSelector Component — selezione dei database da usare
 * nell'interfaccia, in un unico pannello sidebar-friendly.
 *
 * Esiste una sola modalità di selezione (multipla): selezionare un solo
 * database ha lo stesso effetto di una modalità "singola" dedicata,
 * quindi non ce n'è una separata.
 *
 * Non contiene un form di JOIN nativo tra database: un JOIN resta
 * comunque possibile scrivendo a mano (o generando via NL) un comando
 * JOIN OF COLLECTIONS nel pannello query di QueryExecutor,
 * indipendentemente da questo componente. onDatabasesChange passa solo
 * l'elenco dei database selezionati.
 */

import React, { useState, useEffect } from 'react';
import { showToast } from './Toast';
import './DatabaseSelector.css';

/**
 * AGGIUNTO 03/10/2026 — integrazione JCO DS: etichetta e chiave di
 * raggruppamento per il server a cui appartiene un database. "server"
 * arriva già popolato per OGNI database (anche quelli MongoDB, con un
 * descrittore sintetizzato lato backend — vedi
 * DatabaseRegistry._server_descriptor in database_registry.py), quindi
 * qui non c'è un ramo "server assente" da gestire a parte.
 */
function serverLabel(server) {
  const type = server?.type || 'mongodb';
  const host = server?.host || 'localhost';
  const port = server?.port ?? (type === 'mongodb' ? 27017 : '');
  if (type === 'mongodb') return `MongoDB — ${host}:${port}`;
  if (type === 'jcods') return `JCO DS — ${host}:${port}`;
  return `${type} — ${host}:${port}`;
}

function serverKey(server) {
  const type = server?.type || 'mongodb';
  const host = server?.host || 'localhost';
  const port = server?.port ?? (type === 'mongodb' ? 27017 : '');
  return `${type}:${host}:${port}`;
}

/**
 * Raggruppa l'elenco piatto di database per server di appartenenza,
 * preservando l'ordine di prima apparizione (non un ordine alfabetico a
 * sé) — così il gruppo "MongoDB locale" (il più popolato, di solito)
 * resta in genere in cima perché arriva primo dal backend.
 */
function groupDatabasesByServer(databases) {
  const groups = [];
  const byKey = new Map();

  for (const db of databases) {
    const key = serverKey(db.server);
    if (!byKey.has(key)) {
      const group = { key, label: serverLabel(db.server), databases: [] };
      byKey.set(key, group);
      groups.push(group);
    }
    byKey.get(key).databases.push(db);
  }

  return groups;
}

export default function DatabaseSelector({ onDatabasesChange, selectedDatabases }) {
  // ================== STATE ==================

  const [availableDatabases, setAvailableDatabases] = useState([]);
  // Letto direttamente da localStorage qui, non con un useEffect: in
  // React gli effect dei componenti figli partono prima di quelli del
  // genitore, quindi un effect qui girerebbe prima che App.jsx abbia
  // letto il proprio localStorage, leggendo ancora il default
  // ['jcoql_test'] invece del valore reale. L'inizializzatore di
  // useState gira invece una sola volta, al primissimo render,
  // indipendentemente dal genitore. Stessa chiave usata in App.jsx.
  const [multiSelected, setMultiSelected] = useState(() => {
    try {
      const saved = localStorage.getItem('jcoql_selected_databases');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          return new Set(parsed);
        }
      }
    } catch (err) {
      console.warn('Error reading selected databases from localStorage:', err);
    }
    return new Set(['jcoql_test']);
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [removingDb, setRemovingDb] = useState(null); //per rimozione di un database

  const [showAddForm, setShowAddForm] = useState(false);
  // AGGIUNTO 03/10/2026 — integrazione JCO DS: "serverType" seleziona il
  // ramo del form mostrato sotto. 'mongodb' resta il default, stesso
  // comportamento di sempre.
  const [newDbForm, setNewDbForm] = useState({
    serverType: 'mongodb',
    dbName: '',
    mongoUri: 'mongodb://localhost:27017',
    databaseName: '',
    serverHost: 'localhost',
    serverPort: '17017',
    collections: ''
  });

  /**
   * Al mount, carica i database disponibili
   */
  useEffect(() => {
    loadAvailableDatabases();
  }, []);

  /**
   * Aggiunge un nuovo database, MongoDB (default, comportamento di
   * sempre) o JCO DS (il server alternativo dei professori:
   * https://github.com/JcoProjectTeam — aggiunto 03/10/2026).
   *
   * Nota: a differenza della versione precedente, qui i parametri sono
   * passati attraverso URLSearchParams, che li percentuale-codifica da
   * solo — prima erano concatenati a mano nella query string senza
   * encodeURIComponent, quindi un valore con caratteri speciali (uno
   * spazio, una '@' in mongoUri con credenziali, una '&') alterava la
   * query string invece di essere passato come valore letterale.
   */
  const handleAddDatabase = async () => {
    const isJcoDs = newDbForm.serverType === 'jcods';

    if (!newDbForm.dbName || !newDbForm.databaseName) {
      showToast('Please fill in all fields!', 'error');
      return;
    }
    if (isJcoDs && (!newDbForm.serverHost || !newDbForm.serverPort || !newDbForm.collections.trim())) {
      showToast('JCO DS requires host, port and at least one collection!', 'error');
      return;
    }

    try {
      setLoading(true);

      const params = new URLSearchParams({
        db_name: newDbForm.dbName,
        database_name: newDbForm.databaseName,
      });

      if (isJcoDs) {
        params.set('server_type', 'jcods');
        params.set('server_host', newDbForm.serverHost);
        params.set('server_port', newDbForm.serverPort);
        params.set('collections', newDbForm.collections);
      } else {
        params.set('mongo_uri', newDbForm.mongoUri);
      }

      const response = await fetch(
        `http://127.0.0.1:8000/api/databases/connect?${params.toString()}`,
        { method: 'POST' }
      );

      const data = await response.json().catch(() => null);

      if (response.ok && data && data.success !== false) {
        showToast('Database added!', 'success');
        setNewDbForm({
          serverType: 'mongodb',
          dbName: '',
          mongoUri: 'mongodb://localhost:27017',
          databaseName: '',
          serverHost: 'localhost',
          serverPort: '17017',
          collections: ''
        });
        setShowAddForm(false);
        loadAvailableDatabases(); // Ricarica lista
      } else {
        showToast(`Error adding database: ${data?.error || 'unknown error'}`, 'error');
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Rimuove un database dalla registry
   * Non elimina i dati, solo disconnette
   */
  const handleRemoveDatabase = async (dbName) => {
    if (!window.confirm(`Disconnect '${dbName}'? The data stays intact.`)) {
      return;
    }

    try {
      setRemovingDb(dbName);
      const response = await fetch(
        `http://127.0.0.1:8000/api/databases/disconnect?db_name=${dbName}`,
        { method: 'POST' }
      );

      if (response.ok) {
        // Ricarica la lista database
        loadAvailableDatabases();
        
        // Se era selezionato, resetta selection
        if (multiSelected.has(dbName)) {
          const newSet = new Set(multiSelected);
          newSet.delete(dbName);
          setMultiSelected(newSet);
          onDatabasesChange(Array.from(newSet));
        }
        
        showToast(`Database '${dbName}' disconnected`, 'success');
      } else {
        showToast('Error while disconnecting', 'error');
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    } finally {
      setRemovingDb(null);
    }
  };

  /**
   * Carica la lista di database dal server.
   *
   * Nota: questo componente usa fetch() con host "127.0.0.1", mentre
   * App.jsx/QueryExecutor.jsx/Dashboard.jsx usano axios con host
   * "localhost" — stesso backend, due modi diversi di raggiungerlo,
   * senza una costante URL condivisa tra i componenti.
   *
   * Nota: ad ogni chiamata (mount, add/remove database, "Ricarica
   * Database") la selezione corrente viene preservata se è ancora
   * valida — cioè se i database selezionati esistono ancora in quelli
   * appena scaricati. Si resetta al primo database della lista solo se
   * la selezione risulta vuota o non contiene più nessun database
   * realmente esistente.
   */
  const loadAvailableDatabases = async () => {
    try {
      setLoading(true);
      setError('');

      const response = await fetch('http://127.0.0.1:8000/api/databases');
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      // AGGIUNTO 03/10/2026 — integrazione JCO DS: da qui in giù si tiene
      // l'oggetto completo di ogni database (non solo il nome) perché
      // serve anche "server" per raggruppare la lista nel render
      // sottostante — vedi groupDatabasesByServer più in basso nel file.
      const dbList = data.databases;
      const dbNames = dbList.map(db => db.name);

      setAvailableDatabases(dbList);

      // Preserva la selezione corrente se è ancora valida (vedi il
      // commento sopra la funzione); altrimenti prende il primo database
      // disponibile.
      setMultiSelected((prevSelected) => {
        const stillValid = new Set([...prevSelected].filter((db) => dbNames.includes(db)));
        if (stillValid.size > 0) {
          return stillValid;
        }
        return dbNames.length > 0 ? new Set([dbNames[0]]) : new Set();
      });
    } catch (err) {
      setError(`Error loading databases: ${err.message}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Toggle checkbox database (multi-mode)
   */
  const handleMultiToggle = (dbName) => {
    const newSet = new Set(multiSelected);
    
    if (newSet.has(dbName)) {
      newSet.delete(dbName);
    } else {
      newSet.add(dbName);
    }

    setMultiSelected(newSet);

    // Notifica parent
    onDatabasesChange(Array.from(newSet));
  };

  // ================== RENDER ==================

  if (loading) {
    return (
      <div className="database-selector">
        <div className="loading">⏳ Loading databases...</div>
      </div>
    );
  }

  return (
    <div className="database-selector">
      <h2>Databases</h2>

      {error && <div className="error-box">{error}</div>}

      <div className="mode-content">
          {/* Database checkboxes CON BOTTONE RIMUOVI, raggruppati per
              server di appartenenza (AGGIUNTO 03/10/2026 — integrazione
              JCO DS: una sezione per server, col nome/tipo di server
              come sottotitolo, invece di un unico elenco piatto). */}
          <label className="section-label">Available databases:</label>
          {availableDatabases.length === 0 ? (
            <p className="no-databases">No database available</p>
          ) : (
            groupDatabasesByServer(availableDatabases).map(group => (
              <div key={group.key} className="server-group">
                <div className="server-group-label">{group.label}</div>
                <div className="checkboxes">
                  {group.databases.map(db => (
                    <div key={db.name} className="checkbox-with-remove">
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={multiSelected.has(db.name)}
                          onChange={() => handleMultiToggle(db.name)}
                        />
                        <span>{db.name}</span>
                      </label>
                      <button
                        onClick={() => handleRemoveDatabase(db.name)}
                        disabled={removingDb === db.name}
                        className="remove-db-btn"
                        title="Disconnect this database"
                      >
                        {removingDb === db.name ? '⏳' : '✖️'}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
      </div>

      {/* ──────────── ADD DATABASE FORM ──────────── */}
      <button 
        onClick={() => setShowAddForm(!showAddForm)} 
        className="add-db-toggle"
      >
        {showAddForm ? '✖️ Close' : '➕ Add Database'}
      </button>

      {showAddForm && (
        <div className="add-db-form">
          <h4>Connect New Database</h4>

          {/* AGGIUNTO 03/10/2026 — integrazione JCO DS: scelta del server.
              "MongoDB locale" resta selezionato di default, stesso
              comportamento di sempre per chi non tocca questo campo. */}
          <div className="form-group">
            <label>Server:</label>
            <select
              value={newDbForm.serverType}
              onChange={(e) => setNewDbForm({...newDbForm, serverType: e.target.value})}
            >
              <option value="mongodb">Local MongoDB</option>
              <option value="jcods">JCO DS (professors' server)</option>
            </select>
          </div>

          {newDbForm.serverType === 'mongodb' ? (
            <div className="form-group">
              <label>MongoDB URI:</label>
              <input
                type="text"
                value={newDbForm.mongoUri}
                onChange={(e) => setNewDbForm({...newDbForm, mongoUri: e.target.value})}
              />
            </div>
          ) : (
            <>
              <div className="form-group">
                <label>JCO DS host:</label>
                <input
                  type="text"
                  placeholder="e.g. localhost"
                  value={newDbForm.serverHost}
                  onChange={(e) => setNewDbForm({...newDbForm, serverHost: e.target.value})}
                />
              </div>
              <div className="form-group">
                <label>JCO DS port:</label>
                <input
                  type="text"
                  placeholder="e.g. 17017"
                  value={newDbForm.serverPort}
                  onChange={(e) => setNewDbForm({...newDbForm, serverPort: e.target.value})}
                />
              </div>
            </>
          )}

          <div className="form-group">
            <label>{newDbForm.serverType === 'mongodb' ? 'MongoDB database name:' : 'Database name on JCO DS:'}</label>
            <input
              type="text"
              placeholder="e.g. my_database"
              value={newDbForm.databaseName}
              onChange={(e) => setNewDbForm({...newDbForm, databaseName: e.target.value})}
            />
          </div>

          {newDbForm.serverType === 'jcods' && (
            <div className="form-group">
              <label>Collections (comma-separated):</label>
              <input
                type="text"
                placeholder="e.g. testcoll, othercoll"
                value={newDbForm.collections}
                onChange={(e) => setNewDbForm({...newDbForm, collections: e.target.value})}
              />
              <p className="field-hint">
                J-CO-QL+ has no command to list the collections of a JCO DS database — they must be entered here by hand.
              </p>
            </div>
          )}

          <div className="form-group">
            <label>Database name (internal):</label>
            <input
              type="text"
              placeholder="e.g. production_db"
              value={newDbForm.dbName}
              onChange={(e) => setNewDbForm({...newDbForm, dbName: e.target.value})}
            />
          </div>

          <button onClick={handleAddDatabase} className="connect-btn">
            ✅ Connect
          </button>
        </div>
      )}

      {/* ──────────── SUMMARY ──────────── */}
      <div className="summary">
        <div className="summary-title">Selected Databases ({selectedDatabases ? selectedDatabases.length : 0}):</div>
        <div className="summary-badges">
          {selectedDatabases && selectedDatabases.map(db => (
            <span key={db} className="badge">{db}</span>
          ))}
        </div>
      </div>

      {/* ──────────── REFRESH BUTTON ──────────── */}
      <button onClick={loadAvailableDatabases} className="refresh-btn">
        <span style={{ color: '#7c3aed', fontSize: '18px', lineHeight: 1, verticalAlign: 'middle' }}>↻</span> Reload Databases
      </button>
    </div>
  );
}