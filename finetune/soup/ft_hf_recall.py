"""Interroga DIRETTAMENTE l'adattatore (base 4bit + LoRA output_v2), senza fusione/GGUF/Ollama.
Stessi 30 esempi FILTER+GROUP di ft_train_recall (seed 7). Da finetune\\soup, ambiente Soup.
PRIMA libera la GPU:  ollama stop llama3.1-jcoql-v2  (e gli altri modelli caricati; controlla con 'ollama ps').
Uso:  python ft_hf_recall.py --adapter output_v2 --n 30"""
import argparse, json, random, re, torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel
ap = argparse.ArgumentParser()
ap.add_argument("--adapter", default="output_v2")
ap.add_argument("--n", type=int, default=30)
a = ap.parse_args()
BASE = "meta-llama/Llama-3.1-8B-Instruct"
tok = AutoTokenizer.from_pretrained(BASE)
bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
model = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=bnb, device_map={"": 0})
model = PeftModel.from_pretrained(model, a.adapter); model.eval()
rows = [json.loads(l) for l in open('../out/train_final.jsonl', encoding='utf-8')]
fg = [x for x in rows if re.search(r'FILTER.*GROUP PARTITION', x['output'], re.S)]
random.seed(7); sample = random.sample(fg, min(a.n, len(fg)))
norm = lambda q: re.sub(r"\s+", " ", q).strip().rstrip(";").strip()
ident = true_ok = 0
for k, x in enumerate(sample, 1):
    ids = tok.apply_chat_template([{"role": "user", "content": x["instruction"]}], add_generation_prompt=True, return_tensors="pt", return_dict=True).to(0)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=300, do_sample=False, eos_token_id=[tok.eos_token_id, tok.convert_tokens_to_ids("<|eot_id|>")])
    g = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    same = norm(g) == norm(x["output"]); t = "GROUP PARTITION TRUE BY" in g
    ident += same; true_ok += t
    if not t: print("SBAGLIATA:", g)
    print(f"[{k}/{len(sample)}] identica={same} PARTITION TRUE BY={t}")
print(f"\nidentiche {ident}/{len(sample)}  |  con 'GROUP PARTITION TRUE BY' {true_ok}/{len(sample)}")
