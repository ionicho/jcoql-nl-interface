# JCoQL+ Natural Language Interface

Natural Language to JCoQL+ Query Translation using RAG (Retrieval-Augmented Generation)

## 📋 Project Overview

Master's Thesis Project - University of Bergamo  
Student: Nicholas Iotti  
Framework: J-CO (Java Coordinate Objects)

## Objective

Develop an interface that translates natural language queries into JCoQL+ syntax using:
- Large Language Models (Gemini 2.5 Flash)
- Retrieval-Augmented Generation (RAG)
- ANTLR Parser Validation
- Iterative Repair Loop

## Architecture

- **Backend:** Python + FastAPI
- **Frontend:** React + Vite
- **LLM:** Gemini 2.5 Flash (Free Tier)
- **Vector DB:** ChromaDB
- **Parser:** ANTLR (from J-CO Framework)
- **Deploy:** Vercel (Frontend) + Render/Railway (Backend)

## Target Metrics

- Syntactic Accuracy: >85%
- Semantic Accuracy: >75%
- Latency: <2 seconds
- User Satisfaction: >4/5

## Dependencies

This project uses the J-CO Framework:
- Repository: https://github.com/JcoProjectTeam/JcoQL
- Usage: ANTLR grammar for JCoQL+ validation
- We do NOT modify J-CO core - we use it as external tool

## Project Structure
