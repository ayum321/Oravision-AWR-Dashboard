"""Start uvicorn with automatic port retry on bind failures."""
import os
import socket
import sys
import time

# Ensure backend/ is on sys.path so uvicorn can import main:app.
# Use the script's own location to find backend/ regardless of CWD.
_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
# Also change CWD to backend/ so relative imports inside main.py resolve
os.chdir(_BACKEND_DIR)


def is_port_free(port: int) -> bool:
    """Check if a port is truly available by attempting to bind WITHOUT
    SO_REUSEADDR — this mirrors how uvicorn binds, so a TIME_WAIT socket
    will correctly show as unavailable."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except OSError:
        return False


def main():
    base_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    max_retries = 10

    # Find the first actually bindable port
    port = base_port
    for attempt in range(max_retries):
        if is_port_free(port):
            break
        print(f"  [SKIP] Port {port} is held by OS, trying {port + 1}...")
        port += 1
    else:
        print(f"  [WARN] No free port in {base_port}-{base_port + max_retries - 1}, forcing {base_port}")
        port = base_port

    if port != base_port:
        print(f"  [OK] Switched to port {port}")
        print()
        print(f"  ============================================================")
        print(f"    Updated URL  :  http://localhost:{port}")
        print(f"  ============================================================")
        print()

    # Write actual port to temp file so _open_browser.py opens the right URL
    port_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".oravision_port")
    try:
        with open(port_file, "w") as f:
            f.write(str(port))
    except Exception:
        pass

    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
