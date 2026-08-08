"""
Script di test manuale per interrogare direttamente il corpus RAG in
ChromaDB, senza passare da un LLM — utile per verificare rapidamente se
il retrieval recupera esempi pertinenti per una data domanda, quando si
sta debuggando (se gli esempi recuperati sono già sbagliati/non pertinenti, 
il problema è nel retrieval, non nel prompt o nel modello).

PREREQUISITI:
- Va lanciato dalla ROOT del progetto (usa il path relativo
  "./chroma_data", coerente con dove main.py se lo aspetta).
- Il corpus deve essere già stato caricato con
  backend/database/load_examples.py almeno una volta, altrimenti
  client.get_collection(...) fallisce perché la collection non esiste.

Lancio: `python backend/database/test_retrieval.py` — esegue due ricerche
di esempio hardcoded in fondo al file (righe "Test 1"/"Test 2").
"""
import chromadb
from dotenv import load_dotenv

def test_search(query_text):
    """
    Cerca i 2 esempi più simili a query_text nel corpus RAG e li stampa.

    NOTA sul campo "Distanza" stampato sotto: è una distanza (più basso =
    più simile), non un punteggio di affinità (più alto = meglio) come
    potrebbe suggerire il nome "score" nella variabile locale.
    """
    print(f"\n🔍 Domanda Utente: '{query_text}'")
    
    # Connessione al DB
    client = chromadb.PersistentClient(path="./chroma_data")
    collection = client.get_collection(name="jcoql_examples")
    
    # Ricerca dei 2 esempi più simili
    results = collection.query(
        query_texts=[query_text],
        n_results=2
    )
    
    print("-" * 40)
    for i in range(len(results['documents'][0])):
        title = results['metadatas'][0][i]['title']
        score = results['distances'][0][i]
        query = results['metadatas'][0][i]['query']
        
        print(f"📌 RISULTATO {i+1}: {title} (Distanza: {score:.4f})")
        print(f"💻 Query JCoQL+:\n{query}")
        print("-" * 40)

if __name__ == "__main__":
    # Test 1: Ricerca per filtraggio prezzi
    test_search("Mostrami i prodotti che costano più di 100 euro")
    
    # Test 2: Ricerca per trasformazione dati
    test_search("Aggiungi un campo con l'iva calcolata al totale")