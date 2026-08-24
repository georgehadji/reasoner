import os
import subprocess
import sys

print(f"Current Working Directory: {os.getcwd()}")
print(f"Python Version: {sys.version}")
print(f"PATH: {os.environ.get('PATH')}")

try:
    result = subprocess.run(['git', '--version'], capture_output=True, text=True)
    print(f"Git Version: {result.stdout.strip()}")
except Exception as e:
    print(f"Error running git: {e}")

try:
    result = subprocess.run(['powershell.exe', '-Command', 'echo hello'], capture_output=True, text=True)
    print(f"Powershell Echo: {result.stdout.strip()}")
except Exception as e:
    print(f"Error running powershell: {e}")
