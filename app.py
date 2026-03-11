import streamlit as st
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
import chromadb

# 1. Configurazione della pagina
st.set_page_config(page_title="JCoQL+ AI Assistant", page_icon="💎", layout="centered")

# 2. Caricamento variabili d'ambiente
load_dotenv()
API_KEY = os.getenv('GEMINI_API_KEY')

# 3. Stile CSS personalizzato
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stCodeBlock { border: 2px solid #4A90E2; border-radius: 10px; padding: 10px; }
    .stTextArea textarea { font-family: 'Cascadia Code', monospace; }
    </style>
    """, unsafe_allow_html=True)

st.title("💎 JCoQL+ AI Interface")
st.write("Traduci il linguaggio naturale in query JCoQL+ utilizzando l'intelligenza artificiale.")

# 4. Inizializzazione Risorse (Database e Modello)
@st.cache_resource
def load_resources():
    # Connessione al DB vettoriale ChromaDB
    client = chromadb.PersistentClient(path="./chroma_data")
    collection = client.get_collection(name="jcoql_examples")
    
    # Inizializzazione LLM con parametri di stabilità
    llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  # ← NUOVO MODELLO
    google_api_key=API_KEY,
    temperature=0,
    max_retries=2
)
    return collection, llm

try:
    collection, llm = load_resources()

    # 5. Interfaccia Input
    query_input = st.text_area(
        "Cosa vuoi chiedere al database?", 
        placeholder="Esempio: Prendi tutti i documenti dalla collezione 'ordini' dove il prezzo è minore di 50",
        height=120
    )

    if st.button("Genera Query JCoQL+ 🚀"):
        if query_input:
            with st.spinner("Generazione in corso..."):
                # A. Recupero Semantico (RAG) - Ridotto a 1 esempio per risparmiare quota
                results = collection.query(query_texts=[query_input], n_results=1)
                context = "\n\n".join(results['documents'][0])
                
                # B. Creazione del Prompt Unificato
                prompt_definitivo = f"""
Sei un esperto traduttore di linguaggio naturale in query JCoQL+.
Usa strettamente la sintassi mostrata in questo esempio:

{context}

Richiesta dell'utente: {query_input}

Rispondi esclusivamente con il codice della query JCoQL+, senza spiegazioni o testo aggiuntivo.
"""
                
                # C. Chiamata al modello
                response = llm.invoke(prompt_definitivo)
                
                # D. Visualizzazione Risultato
                st.success("Query JCoQL+ generata con successo!")
                st.code(response.content, language="sql")
                
                st.info("💡 Puoi copiare questo codice e usarlo nel tuo engine JCoQL.")
        else:
            st.warning("⚠️ Per favore, inserisci una richiesta prima di generare!")

except Exception as e:
    st.error(f"❌ Errore di sistema: {e}")
    if "429" in str(e):
        st.warning("🚨 Limite di quota raggiunto. Assicurati di aver inserito la NUOVA API KEY nel file .env e riprova tra qualche minuto.")
    elif "404" in str(e):
        st.info("🔍 Modello non trovato. Verifica che il nome 'gemini-2.0-flash' sia corretto per la tua zona.")