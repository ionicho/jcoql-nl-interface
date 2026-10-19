#!/usr/bin/env python3
"""
Wrapper per LLM locali (Llama/Gemma) via Ollama

PREREQUISITI PER CHI VUOLE FAR GIRARE QUESTO MODULO (non ovvio dal solo
codice, e non c'è controllo/messaggio d'errore chiaro se manca):
1. Ollama deve essere installato e in esecuzione in locale
   (https://ollama.com) — questo modulo si limita a parlare con l'API
   locale di Ollama via la libreria `ollama`, non include o avvia Ollama.
2. I modelli devono essere già stati scaricati con:
     ollama pull llama3.1:8b-instruct-q4_K_M
     ollama pull gemma:7b-instruct-q4_K_M
   Se Ollama non è in esecuzione o il modello non è stato scaricato,
   ollama.generate(...) qui sotto solleva un'eccezione che NON viene
   gestita in questo file — risale al chiamante (main.py, che la
   intercetta più a monte in un try/except generico sull'endpoint
   /api/generate). Se stai debuggando un errore "modello non trovato" o
   "connection refused" quando selezioni Llama/Gemma dalla UI, il primo
   posto da controllare è se Ollama è acceso e i modelli sono scaricati.
"""
import os
import json
import urllib.request
import urllib.error
import ollama

# 'num_ctx' va impostato esplicitamente in entrambe le chiamate sotto —
# senza, Ollama usa il default
# del runtime, spesso solo 2048 token per molti modelli quantizzati, a
# prescindere da quanto il modello supporterebbe davvero. Il prompt che
# main.py costruisce oggi (grammatica JCoQL+ completa o BASIC per i
# modelli locali, fino a 6 esempi RAG, schema reale con tipi ed esempi per
# ogni database selezionato, più tutte le regole accumulate nel tempo) può
# superare facilmente un valore troppo basso — se lo supera, Ollama tronca
# silenziosamente quello che arriva al modello, che genera senza aver mai
# visto, ad esempio, lo schema reale o perfino la richiesta stessa (se il
# taglio arriva a toccare la parte finale del prompt). Confermato dal vivo
# il 30/09 su Llama con una richiesta a una sola parola ("utenti"): prompt
# BASIC di ~18.345 token stimati contro un num_ctx di 8192 allora comune
# a entrambi i modelli — più del doppio del contesto disponibile, con
# Llama che ometteva sistematicamente GET COLLECTION o rispondeva con una
# frase discorsiva invece di una query, su tutti e 3 i tentativi.
#
# 8192 resta il limite massimo di contesto di Gemma 1 7B (il modello Gemma
# davvero usato qui, non Gemma 2 9B — vedi nota in generate_with_gemma),
# quindi non regolabile verso l'alto per quel modello. Llama 3.1 8B invece
# supporta nativamente fino a 128K token di contesto — valore differenziato
# per Llama, alzato a 32768 (4x) per dare margine comodo sopra al prompt
# osservato più l'output (num_predict 1024), senza spingersi al limite
# massimo del modello (userebbe molta più RAM/VRAM e rallenterebbe la
# generazione, su una macchina locale non è detto serva davvero quel tanto).
# Se risultasse ancora insufficiente con molti database selezionati insieme
# (prompt più grande), o se 32768 risultasse troppo lento/pesante per la
# macchina in uso, vale la pena ritoccare questo valore.
GEMMA_NUM_CTX = 8192
LLAMA_NUM_CTX = 32768

# Modelli aggiuntivi (02/10) — scaricati E AGGIUNTI accanto ai due sopra,
# non in sostituzione (richiesta esplicita, per confrontarli nella
# campagna di test multi-modello). Scelti dopo aver verificato cosa esiste
# davvero sulla libreria Ollama e cosa entra nella VRAM/RAM disponibile su
# questa macchina (RTX 4060 8GB VRAM, 16GB RAM):
# - Llama: l'ultima versione di Meta più recente della 3.1 che abbiamo già
#   è la 3.2, ma solo nelle taglie piccole (1B/3B) — le versioni successive
#   (3.3, solo 70B; Llama 4 Scout/Maverick, minimo 67GB anche quantizzato)
#   non entrano in questa macchina. Llama 3.2 3B è quindi più recente ma
#   probabilmente più debole della 3.1 8B già in uso (meno parametri) — non
#   un upgrade netto, ma un dato di confronto utile per la tesi (effetto
#   della dimensione del modello sulla qualità delle query generate).
# - Gemma: Gemma 4 esiste con taglie piccole compatibili (e2b/e4b), un vero
#   upgrade di generazione rispetto a Gemma 1 7B attuale. Scelta e4b
#   (4,5B parametri effettivi, contesto nativo 128K) come compromesso tra
#   e2b (più piccolo, meno capace) e 12B (al limite della VRAM disponibile).
LLAMA32_NUM_CTX = 32768
# Gemma 4 supporta nativamente fino a 128K di contesto, ma impostarlo al
# massimo userebbe molta più VRAM del necessario per i prompt in uso qui
# (stessa logica già applicata a LLAMA_NUM_CTX sopra) — 32768 dà ampio
# margine sopra il prompt BASIC osservato, restando leggero sugli 8GB di
# VRAM disponibili.
GEMMA4_NUM_CTX = 32768

# --- llama.cpp (llama-server) per il modello fine-tuned con LoRA applicata a runtime (11/10/2026) ---
# Perche': il modello fine-tuned FUSO (soup merge -> GGUF -> Ollama) perde gran parte di cio' che la LoRA
# ha imparato (126/144 con la LoRA a runtime contro 90/144 col modello fuso, vedi cap9-fine-tuning-v2-lora-runtime
# nel Project) e Ollama 0.40 non supporta piu' ADAPTER. Se LLAMACPP_URL e' impostata
# (es. LLAMACPP_URL=http://127.0.0.1:8081) generate_with_llama parla con llama-server invece che con Ollama.
# Il server va avviato con finetune/soup/start_llama_server_v4.ps1 (modello base Q4_K_M + lora_v4.f16.gguf, tutti i livelli su GPU).
# In modalita' tuned l'URL di default e' http://127.0.0.1:8081 (LLAMACPP_URL serve solo per cambiarlo).
# Gli altri modelli (Gemma, Llama 3.2, Gemma 4) NON sono toccati: restano su Ollama.
LLAMA31_CHAT_HEADER = (
    "<|start_header_id|>system<|end_header_id|>\n\n"
    "Cutting Knowledge Date: December 2023\nToday Date: 26 Jul 2024\n\n<|eot_id|>"
    "<|start_header_id|>user<|end_header_id|>\n\n"
)
LLAMA31_CHAT_FOOTER = "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"

def _generate_with_llamacpp(prompt: str, url: str) -> str:
    """
    Stesso formato dell'addestramento: template chat di Llama 3.1 (blocco di sistema con la data fissa di
    default del tokenizer, messaggio utente = istruzione, niente BOS: lo aggiunge il server). Il contenuto
    utente viene 'trimmato' come fa il template del tokenizer. Se il server non e' raggiungibile
    l'eccezione risale al chiamante, come per Ollama.
    """
    body = {
        "prompt": LLAMA31_CHAT_HEADER + prompt.strip() + LLAMA31_CHAT_FOOTER,
        "n_predict": 1024,
        "temperature": 0,
        "stop": ["<|eot_id|>"],
        "cache_prompt": False,
    }
    req = urllib.request.Request(
        url.rstrip("/") + "/completion",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read().decode("utf-8"))["content"].strip()
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"llama-server not reachable at {url} ({e.reason}). Tuned mode needs the server: "
            "run finetune\\soup\\start_llama_server_v4.ps1 and wait for the 'listening' line."
        )

def generate_with_llama(prompt: str, model: str = None, use_llamacpp: bool = None) -> str:
    """
    Genera testo con Llama 3.1 8B locale
    
    Args:
        prompt: Prompt completo
        model: Nome modello Ollama
        use_llamacpp: True = llama-server (modello tuned + LoRA), False = Ollama
            (modello base); None = llama-server se LLAMACPP_URL e' impostata
        
    Returns:
        Testo generato
    """
    # Il modello si può cambiare senza toccare il codice: variabile d'ambiente LLAMA_MODEL
    # (es. LLAMA_MODEL=llama3.1-jcoql per il modello fine-tuned, con LOCAL_PROMPT_MODE=tuned).
    llamacpp_url = os.getenv("LLAMACPP_URL")
    if use_llamacpp is None:
        use_llamacpp = bool(llamacpp_url)
    if use_llamacpp:
        # Con use_llamacpp=True (modalita' tuned) non si ripiega MAI sul modello base di Ollama:
        # sarebbe un modello diverso da quello scelto dall'utente, senza alcun avviso.
        return _generate_with_llamacpp(prompt, llamacpp_url or "http://127.0.0.1:8081")
    model = model or os.getenv("LLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M")
    response = ollama.generate(
        model=model,
        prompt=prompt,
        options={
            'temperature': 0,  # Zero netto (non 0.1): a 0.1 restava un margine di
                                # scelta tra token quasi ugualmente probabili, che su
                                # una generazione di media lunghezza si accumulava in
                                # formulazioni diverse a parità di richiesta - vedi
                                # nota simmetrica in generate_with_gemma sotto
            'top_p': 0.9,
            'num_predict': 1024,  # Max token output — alcune
                                   # delle query più lunghe generate oggi (join
                                   # concatenati, filtraggio a stadi su array) possono
                                   # superare quella soglia, con il rischio di un
                                   # troncamento a metà query invece di un errore chiaro.
            'num_ctx': LLAMA_NUM_CTX,
        }
    )
    return response['response'].strip()

def generate_with_gemma(prompt: str, model: str = "gemma:7b-instruct-q4_K_M") -> str:
    """
    Genera testo con Gemma 7B locale

    NOTA: il default qui sotto (model="gemma:7b-instruct-q4_K_M") è un
    modello da 7B, non 9B — il nome del modello Ollama lo conferma
    ("7b"). Corretto qui il docstring, che riportava erroneamente "9B".
    È inoltre Gemma 1, non Gemma 2 (quest'ultima esisterebbe come tag
    Ollama separato, es. "gemma2:9b") — vedi anche la correzione
    dell'etichetta in test_models() più sotto, che riportava lo stesso
    doppio errore (versione e dimensione).
    
    Args:
        prompt: Prompt completo
        model: Nome modello Ollama
        
    Returns:
        Testo generato
    """
    response = ollama.generate(
        model=model,
        prompt=prompt,
        options={
            'temperature': 0,  # Zero netto - vedi nota in generate_with_llama sopra
            'top_p': 0.9,
            'num_predict': 1024,  # Vedi nota in generate_with_llama sopra
            'num_ctx': GEMMA_NUM_CTX,
        }
    )
    return response['response'].strip()

def generate_with_llama32(prompt: str, model: str = "llama3.2:3b-instruct-q4_K_M") -> str:
    """
    Genera testo con Llama 3.2 3B locale — AGGIUNTO accanto a
    generate_with_llama (Llama 3.1 8B), non in sostituzione. Vedi nota
    sopra LLAMA32_NUM_CTX per perché 3.2 3B e non una versione più
    recente/grande.

    Args:
        prompt: Prompt completo
        model: Nome modello Ollama

    Returns:
        Testo generato
    """
    response = ollama.generate(
        model=model,
        prompt=prompt,
        options={
            'temperature': 0,  # Zero netto - vedi nota in generate_with_llama sopra
            'top_p': 0.9,
            'num_predict': 1024,  # Vedi nota in generate_with_llama sopra
            'num_ctx': LLAMA32_NUM_CTX,
        }
    )
    return response['response'].strip()

def generate_with_gemma4(prompt: str, model: str = "gemma4:e4b-it-q4_K_M") -> str:
    """
    Genera testo con Gemma 4 E4B locale — AGGIUNTO accanto a
    generate_with_gemma (Gemma 1 7B), non in sostituzione. Vedi nota
    sopra GEMMA4_NUM_CTX per la scelta della taglia E4B.

    Args:
        prompt: Prompt completo
        model: Nome modello Ollama

    Returns:
        Testo generato
    """
    response = ollama.generate(
        model=model,
        prompt=prompt,
        options={
            'temperature': 0,  # Zero netto - vedi nota in generate_with_llama sopra
            'top_p': 0.9,
            'num_predict': 1024,  # Vedi nota in generate_with_llama sopra
            'num_ctx': GEMMA4_NUM_CTX,
        }
    )
    return response['response'].strip()

def test_models():
    """
    Test manuale da riga di comando dei due modelli (non è un test
    automatizzato/pytest — va lanciato a mano con
    `python backend/llm_local.py` e richiede Ollama attivo con entrambi
    i modelli già scaricati, vedi note prerequisiti in cima al file).
    """
    test_prompt = """
You are a JCoQL query generator expert. JCoQL is a JSON query language.

SYNTAX RULES:
- Use GET COLLECTION to select a collection
- Use FILTER CASE WHERE for conditions
- Fields start with dot (e.g., .rating)
- End with semicolon ;
- Example: GET COLLECTION documents; FILTER CASE WHERE .rating > 4 KEEP OTHERS;

TASK: Generate a JCoQL query to select documents with rating greater than 4.
Output ONLY the query code, nothing else.
"""
    print("="*70)
    print("TEST GEMMA 7B:")  # Il modello davvero richiamato da
                              # generate_with_gemma è Gemma 1 7B (non Gemma 2
                              # 9B) — vedi nota nella funzione sopra.
    print("-"*70)
    gemma_response = generate_with_gemma(test_prompt)
    print(gemma_response)
    print()
    
    print("="*70)
    print("TEST LLAMA 3.1 8B:")
    print("-"*70)
    llama_response = generate_with_llama(test_prompt)
    print(llama_response)
    print()
    
    

if __name__ == "__main__":
    test_models()