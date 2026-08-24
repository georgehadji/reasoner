from pathlib import Path

base = Path(r'E:\Documents\Vibe-Coding\Reasoner\src\reasoner\infrastructure')
for f in sorted(base.rglob('*websocket*')):
    print(f.relative_to(base.parent.parent.parent))
