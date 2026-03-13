#!/usr/bin/env python3
"""
JCoQL+ Natural Language Interface
Streamlit App con RAG + ANTLR Validation
"""
import streamlit as st
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / 'backend'))

from backend.rag_with_validation import generate_jcoql_with_validation

# Page config
st.set_page_config(
    page_title="JCoQL+ NL Interface",
    page_icon="🔍",
    layout="wide"
)

# Title
st.title("🔍 JCoQL+ Natural Language Interface")
st.markdown("**Trasforma linguaggio naturale in query JCoQL 4.0 validate**")
st.markdown("---")

# Sidebar - Info
with st.sidebar:
    st.header("📊 Sistema")
    st.markdown("""
    **Stack:**
    - 🤖 Gemini 2.5 Flash
    - 🗄️ ChromaDB (39 esempi)
    - ✅ ANTLR Parser (JCoQL 4.0)
    - 🔄 Auto-validation + Retry
    
    **Features:**
    - Retrieval esempi simili
    - Generazione query
    - Validazione sintassi
    - Retry automatico
    """)
    
    st.markdown("---")
    
    # Stats
    if 'total_queries' not in st.session_state:
        st.session_state.total_queries = 0
        st.session_state.valid_queries = 0
    
    st.metric("Query Totali", st.session_state.total_queries)
    st.metric("Query Valide", st.session_state.valid_queries)
    
    if st.session_state.total_queries > 0:
        accuracy = (st.session_state.valid_queries / st.session_state.total_queries) * 100
        st.metric("Accuracy", f"{accuracy:.1f}%")

# Main area
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📝 Input")
    
    # Example queries
    examples = [
        "Hotel a Milano con rating superiore a 4",
        "Prodotti con prezzo tra 100 e 200 euro",
        "Utenti senza email registrata",
        "Ristoranti a Roma o Firenze",
        "Appartamenti con superficie tra 50 e 100 mq",
        "Ordini con totale maggiore di 500"
    ]
    
    selected_example = st.selectbox(
        "Esempi rapidi:",
        [""] + examples,
        index=0
    )
    
    # Text input
    nl_query = st.text_area(
        "Inserisci la tua richiesta in linguaggio naturale:",
        value=selected_example if selected_example else "",
        height=100,
        placeholder="Es: Trova tutti gli hotel a Milano con rating maggiore di 4"
    )
    
    # Generate button
    generate_btn = st.button("🚀 Genera Query JCoQL", type="primary", use_container_width=True)

with col2:
    st.subheader("⚙️ Output")
    
    if generate_btn and nl_query:
        with st.spinner("🔄 Generazione in corso..."):
            result = generate_jcoql_with_validation(nl_query)
        
        st.session_state.total_queries += 1
        
        if 'error' in result:
            st.error(f"❌ Errore: {result['error']}")
        else:
            # Validation status
            if result['is_valid']:
                st.success(f"✅ Query Valida (tentativo {result['attempts']})")
                st.session_state.valid_queries += 1
            else:
                st.error(f"❌ Query Invalida dopo {result['attempts']} tentativi")
            
            # Generated query
            st.code(result['jcoql_query'], language='sql')
            
            # Validation errors
            if not result['is_valid'] and result.get('validation_errors'):
                with st.expander("⚠️ Errori di Validazione"):
                    for err in result['validation_errors']:
                        st.write(f"- {err['message']}")
            
            # Retrieved examples
            if result.get('retrieved_examples'):
                with st.expander("📚 Esempi Recuperati da ChromaDB"):
                    for i, ex in enumerate(result['retrieved_examples'], 1):
                        st.text_area(
                            f"Esempio {i}",
                            value=ex,
                            height=150,
                            key=f"example_{i}"
                        )
    
    elif generate_btn:
        st.warning("⚠️ Inserisci una query!")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <small>JCoQL+ NL Interface | Tesi Magistrale Università Bergamo | 
    RAG + LLM + ANTLR Parser | Gemini 2.5 Flash</small>
</div>
""", unsafe_allow_html=True)