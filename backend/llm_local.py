#!/usr/bin/env python3
"""
Wrapper per LLM locali (Llama/Gemma) via Ollama
"""
import ollama

def generate_with_llama(prompt: str, model: str = "llama3.1:8b-instruct-q4_K_M") -> str:
    """
    Genera testo con Llama 3.1 8B locale
    
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
            'temperature': 0.1,  # Bassa per codice deterministico
            'top_p': 0.9,
            'num_predict': 512,  # Max token output
        }
    )
    return response['response'].strip()

def generate_with_gemma(prompt: str, model: str = "gemma:7b-instruct-q4_K_M") -> str:
    """
    Genera testo con Gemma 2 9B locale
    
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
            'temperature': 0.1,
            'top_p': 0.9,
            'num_predict': 512,
        }
    )
    return response['response'].strip()

def test_models():
    """Test veloce dei due modelli"""
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
    print("TEST GEMMA 2 9B:")
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