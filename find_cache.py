import glob

for path in glob.glob("tests/**/*.py", recursive=True):
    with open(path, encoding="utf-8") as f:
        try:
            content = f.read()
            if "_cache.clear" in content:
                print(f"--- {path} ---")
                lines = content.splitlines()
                for i, line in enumerate(lines):
                    if "_cache.clear" in line:
                        print(f"L{i+1}: {line}")
        except Exception:
            pass
