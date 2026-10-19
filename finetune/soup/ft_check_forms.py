"""Che forme di GROUP ci sono davvero nel training, con e senza FILTER prima? Da finetune\\soup."""
import json, re, collections
c = collections.Counter()
for l in open("../out/train_final.jsonl", encoding="utf-8"):
    o = json.loads(l)["output"]
    for m in re.finditer(r"GROUP\s+(\S+(?:\s+\S+)?(?:\s+\S+)?)", o):
        pre = o[:m.start()]
        c[("dopo FILTER" if "FILTER" in pre else "senza FILTER", "GROUP " + " ".join(m.group(1).split()[:3]).split(".")[0].strip())] += 1
for (ctx, forma), n in sorted(c.items(), key=lambda t: -t[1])[:15]:
    print(f"{n:5}  {ctx:13} {forma}")
