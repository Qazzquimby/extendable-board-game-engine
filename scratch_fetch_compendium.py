import ssl, urllib.request, json, re, textwrap

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

resp = urllib.request.urlopen("https://tactics.toren.dev/_nuxt/compendium.ddeea079.js", context=ctx, timeout=10)
js = resp.read().decode("utf-8", errors="replace")

# Print size
print(f"Size: {len(js)} bytes")

# Look for interesting patterns - property names that could indicate hero data
keywords = ["hp", "damage", "range", "ability", "hero", "unit", "speed", "name", "team", "pos", "charge"]
for kw in keywords:
    indices = [i for i in range(len(js)) if js[i:i+len(kw)].lower() == kw.lower()]
    if indices:
        for idx in indices[:3]:
            start = max(0, idx - 30)
            end = min(len(js), idx + len(kw) + 100)
            snippet = js[start:end]
            # Try to show readable content
            readable = "".join(c if 32 <= ord(c) < 127 else " " for c in snippet)
            print(f"  {kw} @ {idx}: ...{readable}...")
        print(f"  (total {len(indices)} occurrences of '{kw}')")
    else:
        print(f"  {kw}: not found")

# Look for the Vue component definition and its data
# Find the compendium component specifically
component_match = re.search(r"(name|data|setup|asyncData)\s*[=:]\s*(function)?\s*\([^)]*\)\s*{", js)
if component_match:
    start = component_match.start()
    print(f"\nComponent start @ {start}:")
    print(js[max(0,start-50):start+500])

# Print key sections of the file
print("\n\n=== FIRST 1500 CHARS ===")
print(textwrap.fill("".join(c if 32 <= ord(c) < 127 else " " for c in js[:1500]), 100))
