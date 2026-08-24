import json
import os

import pathspec


def load_gitignore():
    # Load .gitignore patterns to respect them properly
    ignore_patterns = [
        '.git/', 'node_modules/', '__pycache__/', '.pytest_cache/',
        '.mypy_cache/', '.ruff_cache/', '.hypothesis/', '.import_linter_cache/',
        '.agents/', '.claude/', '.deepseek/', '.gemini/', '.openclaude/', '.qwen/',
        '.reasonix/', '.rtk/', '.worktrees/', 'cache/', 'uploads/', '.venv/'
    ]
    if os.path.exists('.gitignore'):
        with open('.gitignore', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    ignore_patterns.append(line)
    return pathspec.PathSpec.from_lines('gitwildmatch', ignore_patterns)

def map_workspace(root_dir):
    spec = load_gitignore()
    workspace_map = {}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Calculate relative path from root
        rel_path = os.path.relpath(dirpath, root_dir)
        if rel_path == '.':
            rel_path = ''

        # Filter out ignored directories in-place to prevent walking into them
        # Note: os.walk allows modifying dirnames in-place to control recursion
        filtered_dirs = []
        for d in dirnames:
            sub_rel_path = os.path.join(rel_path, d).replace('\\', '/')
            # Always ignore dot directories, build artifacts, etc.
            if d.startswith('.') or d in ['node_modules', '__pycache__', 'cache', 'uploads', 'node_modules', 'dist', 'build', '.venv']:
                continue
            if spec.match_file(sub_rel_path + '/'):
                continue
            filtered_dirs.append(d)

        dirnames[:] = filtered_dirs  # Update in-place to prune recursion

        # Check if current directory itself is ignored
        if rel_path:
            rel_path_slashes = rel_path.replace('\\', '/')
            if spec.match_file(rel_path_slashes + '/') or any(part.startswith('.') for part in rel_path.split(os.sep)):
                continue

        # Filter files
        valid_files = []
        for f in filenames:
            file_rel_path = os.path.join(rel_path, f).replace('\\', '/')
            if f.startswith('.'):
                continue
            if spec.match_file(file_rel_path):
                continue
            valid_files.append(f)

        workspace_map[rel_path.replace('\\', '/')] = {
            'files': sorted(valid_files),
            'subdirs': sorted([d.replace('\\', '/') for d in dirnames])
        }

    return workspace_map

if __name__ == '__main__':
    root_dir = os.path.abspath(os.path.dirname(__file__))
    result = map_workspace(root_dir)
    with open('workspace_map.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(f"Successfully mapped {len(result)} directories to workspace_map.json")
