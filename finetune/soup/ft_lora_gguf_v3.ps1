# ft_lora_gguf_v3.ps1 - converte l'adattatore LoRA v3 (output_v3) in GGUF f16, senza fusione e senza Ollama.
# Da finetune\soup, con soup-env attivo. Produce lora_v3.f16.gguf (serve a start_llama_server_v3.ps1).
$ErrorActionPreference = "Stop"
$LoraConv = "C:\Users\nicho\.soup\llama.cpp\convert_lora_to_gguf.py"
if (-not (Test-Path $LoraConv)) { throw "Non trovo $LoraConv" }
if (-not (Test-Path ".\output_v3\adapter_model.safetensors")) { throw "Manca output_v3\adapter_model.safetensors (l'addestramento e' finito?)" }
if (-not (Test-Path ".\merged_v2n\config.json")) { throw "Manca .\merged_v2n\config.json (serve solo per config e tokenizer del base)" }
$env:PYTHONUTF8 = "1"
python $LoraConv .\output_v3 --base .\merged_v2n --outfile .\lora_v3.f16.gguf --outtype f16
if ($LASTEXITCODE -ne 0) { throw "convert_lora_to_gguf fallito (codice $LASTEXITCODE)" }
Get-Item .\lora_v3.f16.gguf | Select-Object Name, @{n='MB';e={[int]($_.Length/1MB)}}
