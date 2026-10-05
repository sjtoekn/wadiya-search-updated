"""Seeds the same corpus as dev_server.py, then REPLACES this process with the real application:
   python -m wadiya serve   (FastAPI + uvicorn).   Used by:  UI_SERVER=real node tests/browser/ui_browser_test.js
Cookie 'Secure' is switched off ONLY so Chromium keeps the admin cookie over plain http://127.0.0.1;
the Secure flag itself is verified by scripts/verify_live_http.py --spawn."""
import os
import socket
import sys
import tempfile

from tests.browser.dev_server import build_world

tmp = tempfile.mkdtemp(prefix="wadiya-browser-real-")
st, *_ = build_world(tmp)
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
env = {**os.environ, "WADIYA_DB_PATH": st.db_path, "WADIYA_INDEX_PATH": st.index_path,
       "WADIYA_ADMIN_PASSWORD_HASH": st.admin_password_hash, "WADIYA_SECRET_KEY": st.secret_key,
       "WADIYA_COOKIE_SECURE": "false"}
print(f"PORT={port}", flush=True)
os.execvpe(sys.executable, [sys.executable, "-m", "wadiya", "serve", "--port", str(port)], env)   # same PID, so the test can kill it
