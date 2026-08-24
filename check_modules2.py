import os

shadow_names = {'asyncio', 'selectors', 'concurrent', 'threading', 'time'}
for root, dirs, files in os.walk('src'):
    for f in files:
        name, ext = os.path.splitext(f)
        if ext == '.py' and name in shadow_names:
            print(os.path.join(root, f))
