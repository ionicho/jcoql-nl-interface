#!/usr/bin/env python3
"""
Wrapper per LLM cloud (Gemini/Gemma) via Google API
"""
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def generate_with_gemini(prompt: str, model: str = "gemini-3.1-flash-lite-preview") -> str:
    """Genera con Gemini"""
    model_obj = genai.GenerativeModel(model)
    response = model_obj.generate_content(prompt)
    return response.text.strip()

def generate_with_gemma_cloud(prompt: str, model: str = "gemma-2-2b-it") -> str:
    """Genera con Gemma cloud"""
    model_obj = genai.GenerativeModel(model)
    response = model_obj.generate_content(prompt)
    return response.text.strip()