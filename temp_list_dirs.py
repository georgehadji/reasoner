import os

for root, dirs, files in os.walk(r'E:\Documents\Vibe-Coding\Reasoner\src\reasoner\infrastructure', topdown=True):
    for f in files:
        if 'websocket' in f.lower():
            print(os.path.join(root, f))
    # limit depth
    if root.count(os.sep) > 10:
        dirs.clear()
