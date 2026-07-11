import os, re
root = r'E:\Documents\Vibe-Coding\Reasoner\src\reasoner'
pattern = r'def _event'
for dirpath, dirnames, fnames in os.walk(root):
    for fn in fnames:
        if fn.endswith('.py'):
            fp = os.path.join(dirpath, fn)
            try:
                with open(fp, encoding='utf-8', errors='replace') as f:
                    for i, line in enumerate(f, 1):
                        if re.search(pattern, line):
                            print(f'{fp}:{i}: {line.rstrip()[:120]}')
            except Exception as e:
                import logging
                logging.error(f"Error reading file: {e}")
