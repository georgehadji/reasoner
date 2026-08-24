with open('src/reasoner/api/streaming.py', encoding='utf-8') as f:
    content = f.read()

old = "            if getattr(fn, \"_is_silent_noop\", False):"
new = "            if getattr(fn, \"_is_silent_noop\", False) is True:"

if old in content:
    content = content.replace(old, new)
    with open('src/reasoner/api/streaming.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK')
else:
    print('FAIL: not found')
