import React, { useState, useEffect } from 'react';
import './DatabaseManager.css';

export default function DatabaseManager() {
  const [databases, setDatabases] = useState([]);
  const [currentDatabase, setCurrentDatabase] = useState('jcoql_test');
  const [showForm, setShowForm] = useState(false);
  
  // Form per nuovo database
  const [formData, setFormData] = useState({
    db_name: '',
    mongo_uri: 'mongodb://localhost:27017',
    database_name: ''
  });
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Carica lista database al mount
  useEffect(() => {
    loadDatabases();
  }, []);

  const loadDatabases = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/databases');
      const data = await response.json();
      setDatabases(data.databases);
      setCurrentDatabase(data.current);
    } catch (err) {
      setError('Errore caricamento database: ' + err.message);
    }
  };

  const switchDatabase = async (dbName) => {
    try {
      setLoading(true);
      const response = await fetch(
        `http://127.0.0.1:8000/api/databases/select?database_name=${dbName}`,
        { method: 'POST' }
      );
      const data = await response.json();
      
      if (data.success) {
        setCurrentDatabase(dbName);
        setSuccess(`✅ Database cambiato: ${dbName} (${data.collections} collezioni)`);
        setTimeout(() => setSuccess(''), 3000);
      } else {
        setError('❌ ' + data.error);
      }
    } catch (err) {
      setError('Errore switch database: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAddDatabase = async (e) => {
    e.preventDefault();
    
    if (!formData.db_name || !formData.database_name) {
      setError('Riempire tutti i campi!');
      return;
    }

    try {
      setLoading(true);
      const params = new URLSearchParams({
        db_name: formData.db_name,
        mongo_uri: formData.mongo_uri,
        database_name: formData.database_name
      });

      const response = await fetch(
        `http://127.0.0.1:8000/api/databases/connect?${params}`,
        { method: 'POST' }
      );
      const data = await response.json();

      if (data.success) {
        setSuccess(`✅ Database '${formData.db_name}' connesso! (${data.database.collections} collezioni)`);
        setFormData({ db_name: '', mongo_uri: 'mongodb://localhost:27017', database_name: '' });
        setShowForm(false);
        loadDatabases();
        setTimeout(() => setSuccess(''), 3000);
      } else {
        setError('❌ ' + data.error);
      }
    } catch (err) {
      setError('Errore connessione: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const getCurrentDatabaseInfo = () => {
    return databases.find(db => db.name === currentDatabase);
  };

  const currentInfo = getCurrentDatabaseInfo();

  return (
    <div className="database-manager">
      <div className="db-header">
        <h3>🗄️ Database Manager</h3>
      </div>

      {/* Status messages */}
      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      {/* Database Selector */}
      <div className="db-selector">
        <label>Database Attuale:</label>
        <select 
          value={currentDatabase} 
          onChange={(e) => switchDatabase(e.target.value)}
          disabled={loading}
        >
          {databases.map(db => (
            <option key={db.name} value={db.name}>
              {db.name} {db.current ? '✓' : ''} ({db.collections} collezioni)
            </option>
          ))}
        </select>
      </div>

      {/* Current Database Info */}
      {currentInfo && (
        <div className="db-info">
          <h4>Info Database</h4>
          <div className="info-grid">
            <div><strong>Nome:</strong> {currentInfo.name}</div>
            <div><strong>URI:</strong> {currentInfo.uri}</div>
            <div><strong>Database:</strong> {currentInfo.database}</div>
            <div><strong>Collezioni:</strong> {currentInfo.collections}</div>
          </div>
        </div>
      )}

      {/* Add Database Button */}
      <button 
        className="btn-add-db"
        onClick={() => setShowForm(!showForm)}
        disabled={loading}
      >
        {showForm ? '✕ Annulla' : '+ Aggiungi Database'}
      </button>

      {/* Add Database Form */}
      {showForm && (
        <form className="db-form" onSubmit={handleAddDatabase}>
          <h4>Connetti Nuovo Database</h4>
          
          <div className="form-group">
            <label>Nome Database (interno):</label>
            <input
              type="text"
              placeholder="es: production_db"
              value={formData.db_name}
              onChange={(e) => setFormData({...formData, db_name: e.target.value})}
              disabled={loading}
            />
          </div>

          <div className="form-group">
            <label>MongoDB URI:</label>
            <input
              type="text"
              placeholder="mongodb://localhost:27017"
              value={formData.mongo_uri}
              onChange={(e) => setFormData({...formData, mongo_uri: e.target.value})}
              disabled={loading}
            />
          </div>

          <div className="form-group">
            <label>Nome Database MongoDB:</label>
            <input
              type="text"
              placeholder="es: my_database"
              value={formData.database_name}
              onChange={(e) => setFormData({...formData, database_name: e.target.value})}
              disabled={loading}
            />
          </div>

          <button 
            type="submit" 
            className="btn-submit"
            disabled={loading}
          >
            {loading ? '⏳ Connessione...' : '✅ Connetti'}
          </button>
        </form>
      )}

      {/* Database List */}
      <div className="db-list">
        <h4>Database Connessi ({databases.length})</h4>
        <div className="list">
          {databases.map(db => (
            <div key={db.name} className={`db-item ${db.current ? 'current' : ''}`}>
              <span className="db-name">{db.name}</span>
              <span className="db-collections">{db.collections} collezioni</span>
              {db.current && <span className="badge-current">ATTUALE</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}