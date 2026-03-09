import os
import chromadb
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

# Caricamento configurazioni
load_dotenv()
API_KEY = os.getenv('GEMINI_API_KEY')


# Inizializzazione Database
client = chromadb.PersistentClient(path="./chroma_data")
collection = client.get_collection(name="jcoql_examples")

# Inizializzazione con Gemma (Modello Open di Google)
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=API_KEY,
    temperature=0
)

def get_context(user_query):
    # Riduciamo al minimo il contesto per non sprecare token
    try:
        results = collection.query(query_texts=[user_query], n_results=1)
        return results['documents'][0][0]
    except:
        return ""

def translate_to_jcoql(user_input):
    """Traduce il linguaggio naturale in JCoQL+ usando il RAG"""
    
    # 1. Recupera esempi pertinenti
    context = get_context(user_input)
    
    # 2. Prepara il Prompt per Gemini
    system_prompt = """
    Sei un esperto traduttore di linguaggio naturale in JCoQL+ (JSON Collection Query Language).
    Usa gli esempi forniti nel contesto per capire la sintassi corretta.
    
    REGOLE CRITICHE:
    - Rispondi SOLO con la query JCoQL+ pronta all'uso.
    - Non aggiungere spiegazioni o introduzioni.
    - Usa sempre il punto e virgola ';' alla fine delle istruzioni.
    - Se non sei sicuro del nome della collezione, usa 'collection_name'.
    
    ESEMPI DI RIFERIMENTO:
    {context}
    """
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Traduci questa richiesta in JCoQL+: {user_input}")
    ])
    
    # 3. Generazione
    chain = prompt | llm
    response = chain.invoke({
        "context": context,
        "user_input": user_input
    })
    
    return response.content

if __name__ == "__main__":
    print("🚀 JCoQL+ Natural Language Interface (v1.0)")
    print("Digita 'exit' per uscire.\n")
    
    while True:
        user_msg = input("User 👤: ")
        if user_msg.lower() in ['exit', 'quit', 'esci']:
            break
            
        print("Gemini 🤖: Generando query...")
        try:
            query = translate_to_jcoql(user_msg)
            print(f"\n✨ QUERY GENERATA:\n{query}\n")
            print("-" * 50)
        except Exception as e:
            print(f"❌ Errore: {e}")