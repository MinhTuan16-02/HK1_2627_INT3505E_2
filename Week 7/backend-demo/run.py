"""Chay dong thoi hai cach tiep can bang mot lenh."""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["both", "code", "design"], default="both", nargs="?")
    args = parser.parse_args()
    if args.mode == "code":
        from code_first.app import create_app
        create_app().run(host="127.0.0.1", port=5001, use_reloader=False)
    elif args.mode == "design":
        import uvicorn
        from design_first.app import create_app
        uvicorn.run(create_app(), host="127.0.0.1", port=5002)
    else:
        children = []
        try:
            for mode in ("code", "design"):
                children.append(subprocess.Popen([sys.executable, str(ROOT / "run.py"), mode], cwd=ROOT))
            print("Code-First:   http://127.0.0.1:5001/docs", flush=True)
            print("Design-First: http://127.0.0.1:5002/ui/", flush=True)
            print("Nhan Ctrl+C de dung ca hai API.", flush=True)
            while all(child.poll() is None for child in children):
                time.sleep(0.5)
            raise SystemExit("Mot API da dung. Kiem tra log o tren (co the cong dang bi chiem).")
        except KeyboardInterrupt:
            pass
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
            for child in children:
                child.wait()


if __name__ == "__main__":
    main()
