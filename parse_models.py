import json

with open('.reasonix/truncated-results/1781171537097-4ed0f276-web_fetch.txt') as f:
    data = json.load(f)

print(f"Total models: {len(data['data'])}")

# Find cheap models with text output
cheap = []
for m in data['data']:
    pricing = m.get('pricing', {})
    p = pricing.get('prompt')
    if p is None or p == '-1':
        continue
    try:
        pp = float(p)
    except (ValueError, TypeError):
        continue
    if pp < 0 or pp >= 0.0000005:
        continue
    cutoff = m.get('knowledge_cutoff')
    out_mod = m.get('architecture', {}).get('output_modalities', [])
    has_text = 'text' in out_mod
    has_tools = 'tools' in m.get('supported_parameters', [])
    ctx = m.get('context_length', 0)
    cheap.append((pp, m['id'], cutoff, has_text, has_tools, ctx))

cheap.sort(key=lambda x: x[0])

print(f"\nModels under $0.50/M input: {len(cheap)}")
print()

# Header
print(f"{'Price/M':>11} {'Model ID':<55} {'Cutoff':<14} {'Text':<5} {'Tools':<6} {'Ctx':<8}")
print('-' * 100)

for price, mid, cutoff, has_text, has_tools, ctx in cheap:
    price_m = price * 1_000_000
    cutoff_str = cutoff if cutoff else 'null'
    print(f"${price_m:>7.2f}/M  {mid:<55} {cutoff_str:<14} {str(has_text):<5} {str(has_tools):<6} {ctx:<8}")

# Also show ALL models with knowledge_cutoff set
print("\n\n===== ALL models with knowledge_cutoff !== null =====")
cutoff_models = [m for m in data['data'] if m.get('knowledge_cutoff') is not None]
print(f"Total: {len(cutoff_models)}")
for m in cutoff_models:
    pricing = m.get('pricing', {})
    pp = pricing.get('prompt', '?')
    print(f"  {m['id']}: cutoff={m['knowledge_cutoff']}, prompt_price={pp}, text={'text' in m.get('architecture',{}).get('output_modalities',[])}")
