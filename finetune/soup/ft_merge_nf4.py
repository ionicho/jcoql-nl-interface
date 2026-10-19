"""Fusione FEDELE: pesi del base DEQUANTIZZATI da NF4 (come visti in addestramento) + correzione LoRA (q_proj, v_proj).
Da finetune\\soup con l'ambiente di Soup, GPU libera (ollama stop ...).
Uso:  python ft_merge_nf4.py --adapter output_v2 --out merged_v2n"""
import argparse, json, os, torch
import bitsandbytes as bnb
from bitsandbytes.nn import Linear4bit
from safetensors.torch import save_file
from transformers import AutoConfig, AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, GenerationConfig
from peft import PeftModel
ap = argparse.ArgumentParser()
ap.add_argument("--adapter", default="output_v2"); ap.add_argument("--out", default="merged_v2n")
a = ap.parse_args()
BASE = "meta-llama/Llama-3.1-8B-Instruct"
os.makedirs(a.out, exist_ok=True)
bnb_cfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
model = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=bnb_cfg, device_map={"": 0})
model = PeftModel.from_pretrained(model, a.adapter); model.eval()

parents = {n: m for n, m in model.named_modules() if hasattr(m, "lora_A") and "default" in m.lora_A}
shard, shard_bytes, shard_i, wmap, total = {}, 0, 0, {}, 0
def flush():
    global shard, shard_bytes, shard_i
    if not shard: return
    shard_i += 1; fn = f"model-{shard_i:05d}.safetensors"
    save_file(shard, os.path.join(a.out, fn), metadata={"format": "pt"})
    for k in shard: wmap[k] = fn
    print("scritto", fn, f"{shard_bytes/1e9:.2f} GB"); shard, shard_bytes = {}, 0
def emit(key, t):
    global shard_bytes, total
    t = t.contiguous().cpu(); shard[key] = t
    shard_bytes += t.numel() * t.element_size(); total += t.numel() * t.element_size()
    if shard_bytes > 3.5e9: flush()
strip = lambda s: s.replace("base_model.model.", "", 1)
n_lora = 0
with torch.no_grad():
    for name, mod in model.named_modules():
        if isinstance(mod, Linear4bit):
            w = bnb.functional.dequantize_4bit(mod.weight.data, mod.weight.quant_state).float()
            key = name
            if name.endswith(".base_layer"):
                key = name[:-len(".base_layer")]
                p = parents[key]
                A = p.lora_A["default"].weight.float().to(w.device); B = p.lora_B["default"].weight.float().to(w.device)
                w = w + p.scaling["default"] * (B @ A); n_lora += 1
            emit(strip(key) + ".weight", w.to(torch.bfloat16))
        else:
            if "lora_" in name: continue
            for pn, p in mod.named_parameters(recurse=False):
                emit(strip((name + "." if name else "") + pn), p.data.to(torch.bfloat16))
flush()
print("livelli LoRA fusi:", n_lora, "(attesi 64: 32 q_proj + 32 v_proj)")
json.dump({"metadata": {"total_size": total}, "weight_map": wmap}, open(os.path.join(a.out, "model.safetensors.index.json"), "w"), indent=1)
AutoConfig.from_pretrained(BASE).save_pretrained(a.out)
AutoTokenizer.from_pretrained(BASE).save_pretrained(a.out)
try: GenerationConfig.from_pretrained(BASE).save_pretrained(a.out)
except Exception: pass
print("fatto:", a.out)
