import json, re, collections
c = collections.Counter(); n = 0; tot = 0
for l in open('../out/train_final.jsonl', encoding='utf-8'):
    x = json.loads(l)
    if re.search(r'FILTER.*GROUP PARTITION', x['output'], re.S):
        q = re.search(r'RICHIESTA: "(.*)"', x['instruction']).group(1)
        c[' '.join(q.split()[:2])] += 1
        n += ('ordin' in q.lower()); tot += 1
print('esempi FILTER+GROUP:', tot)
for k, v in c.most_common(12):
    print(f'{v:4}  {k}')
print('richieste con "ordin":', n)
