import chromadb
from dotenv import load_dotenv

def test_search(query_text):
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