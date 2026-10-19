# start_llama_server_v3.ps1 - avvia llama-server (build CUDA) con Llama 3.1 8B Q4_K_M (il file di Ollama) + LoRA v3 a runtime.
# Da lanciare da finetune\soup, prima di avviare il backend con LLAMACPP_URL=http://127.0.0.1:8081
# Ollama deve avere la GPU libera dagli altri modelli (ollama ps / ollama stop <nome>).
$ErrorActionPreference = "Stop"
$Server = "C:\llama-cuda\llama-server.exe"
$Lora = Join-Path $PSScriptRoot "lora_v3.f16.gguf"
if (-not (Test-Path $Server)) { throw "Non trovo $Server" }
if (-not (Test-Path $Lora)) { throw "Non trovo $Lora" }
$from = ollama show llama3.1:8b-instruct-q4_K_M --modelfile | Select-String "^FROM " | Select-Object -First 1
if (-not $from) { throw "Non riesco a leggere il percorso del modello base da Ollama" }
$Base = ($from.Line -replace "^FROM\s+", "").Trim()
if (-not (Test-Path $Base)) { throw "Il file del modello base non esiste: $Base" }
if (Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue) { Write-Host "Porta 8081 gia' in uso: server gia' avviato?" -ForegroundColor Yellow; return }
Start-Process $Server -ArgumentList '-m', $Base, '--lora', $Lora, '-c', '8192', '--parallel', '1', '--port', '8081', '-ngl', '99'
Write-Host "llama-server avviato in una nuova finestra (porta 8081). Attendi la riga 'listening'." -ForegroundColor Green
