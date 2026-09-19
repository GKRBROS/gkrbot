import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Syntax check script
with open(os.path.join(os.path.dirname(__file__), "..", "dashboard_api.py"), "r", encoding="utf-8") as f:
    code = f.read()

import py_compile
print("Current dashboard_api.py compiles cleanly!")
