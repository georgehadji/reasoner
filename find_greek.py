import os
import re


def find_greek(directory):
    greek_pattern = re.compile(r'[α-ωΑ-Ω]')
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(('.tsx', '.ts', '.js', '.jsx')):
                path = os.path.join(root, file)
                try:
                    with open(path, encoding='utf-8') as f:
                        for i, line in enumerate(f, 1):
                            if greek_pattern.search(line):
                                print(f"Greek found in {path} at line {i}: {line.strip()}")
                except Exception:
                    pass

if __name__ == "__main__":
    find_greek('ui-next/src')
