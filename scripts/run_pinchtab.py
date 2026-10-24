"""Run PinchTab 0.15.2 with disposable local-only attach configuration."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    binary = shutil.which("pinchtab")
    if not binary:
        raise SystemExit("Install PinchTab 0.15.2 first; see backend/README.md.")
    if not os.environ.get("PINCHTAB_TOKEN", "").strip():
        raise SystemExit("Export PINCHTAB_TOKEN for both PinchTab and the backend.")
    version = subprocess.run([binary, "--version"], capture_output=True, text=True, check=True)
    if version.stdout.strip() != "pinchtab 0.15.2":
        raise SystemExit("Install PinchTab 0.15.2; refusing an untested version.")
    with tempfile.TemporaryDirectory(prefix="clevis-pinchtab-") as temporary:
        config = {
            "configVersion": "0.8.0",
            "server": {
                "bind": "127.0.0.1", "port": "9867", "stateDir": temporary,
                "logLevel": "error", "networkBufferSize": 0, "retainNetworkBodies": False,
            },
            "multiInstance": {"strategy": "explicit"},
            "browser": {"extensionPaths": []},
            "observability": {"activity": {"enabled": False}},
            "security": {"attach": {
                "enabled": True, "allowHosts": ["127.0.0.1"],
                "allowSchemes": ["http", "ws"], "forwardProxyAuth": False,
            }},
        }
        path = Path(temporary) / "config.json"
        path.write_text(json.dumps(config))
        child = subprocess.Popen(
            [binary, "server", "--bind", "127.0.0.1", "--port", "9867", "--log-level", "error"],
            env={**os.environ, "PINCHTAB_CONFIG": str(path)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print("PinchTab starting on 127.0.0.1:9867; Ctrl+C stops it.", flush=True)
        try:
            return child.wait()
        except KeyboardInterrupt:
            return 0
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
