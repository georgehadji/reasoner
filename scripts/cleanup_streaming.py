import sys
import re
from pathlib import Path

def main():
    repo_root = Path(__file__).parent.parent.resolve()
    streaming_path = repo_root / "src" / "reasoner" / "api" / "streaming.py"
    
    with open(streaming_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove _stream_direct_answer
    match_direct = re.search(r'async def _stream_direct_answer\(.*?return\n', content, re.DOTALL)
    if match_direct:
        content = content.replace(match_direct.group(0), "")
        
    # Remove _stream_web_search_results
    match_web = re.search(r'async def _stream_web_search_results\(.*?yield chunk\n', content, re.DOTALL)
    if match_web:
        content = content.replace(match_web.group(0), "")

    # Remove CREATIVE constants block
    match_creative = re.search(r'# Creative-writing model tiers.*?SELF-CORRECTION:\\n"\n\)\n', content, re.DOTALL)
    if match_creative:
        content = content.replace(match_creative.group(0), "")
        
    with open(streaming_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print("Cleaned up streaming.py")

if __name__ == "__main__":
    main()
