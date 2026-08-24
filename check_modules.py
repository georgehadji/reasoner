import os

shadow_names = {'asyncio', 'selectors', 'concurrent', 'threading', 'time'}
for f in os.listdir('.'):
    name, ext = os.path.splitext(f)
    if ext == '.py' and name in shadow_names:
        print(f'SHADOW: {f}')
