# Reads a hook's stdin JSON on $1 and echoes tool_input.file_path with all
# backslashes turned into forward slashes, so Windows paths match glob patterns.
extract_file_path() {
  printf '%s' "$1" \
    | tr -d '\r\n' \
    | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    | sed 's|\\\\|/|g; s|\\|/|g'
}
