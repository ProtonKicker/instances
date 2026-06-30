import os
import sys
import json
import argparse
from pathlib import Path
import detect
import process

APP_DIR = Path(__file__).parent
CONFIG_FILE = APP_DIR / ".instance1_config.json"
DATA_DIR = str(Path.home() / "Documents" / "instance1")


def load_data_dir():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())["data_dir"]
        except (json.JSONDecodeError, KeyError):
            pass
    return str(Path.home() / "Documents" / "instance1")


def setup_data_dir():
    target = Path(DATA_DIR)
    if not target.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        print(f"Created directory at: {target}")


def render_status():
    os.system('clear')
    print("🪽  Instance 1 ALIVE\n")

    print(f"📁  Data: {DATA_DIR}\n")

    devices = detect.scan()
    if len(devices) == 0:
        print("📋  No devices found")
    else:
        print(f"📋  Devices ({len(devices)} found):")
        for i, dev in enumerate(devices):
            name = os.path.basename(dev)
            print(f"      [{i}] {name}")
    print()

    if detect.check_config(DATA_DIR):
        print("🔧  Config: printer.cfg ✓")
    else:
        print("🔧  Config: printer.cfg ⚠️  missing")
        print(f"      Place your printer.cfg in: {DATA_DIR}")
    print()

    if process.get_state():
        print("🟢  Instance 1 is RUNNING")
        print("🌍  Mainsail: http://localhost:8080\n")


def main():
    global DATA_DIR

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=str, help="data directory path")
    args = parser.parse_args()

    if args.data_dir:
        DATA_DIR = str(Path(args.data_dir).expanduser().resolve())
        CONFIG_FILE.write_text(json.dumps({"data_dir": DATA_DIR}))
    else:
        DATA_DIR = load_data_dir()

    setup_data_dir()

    while True:
        render_status()

        if process.get_state():
            cmd = input("Commands: [kill] [exit]\n> ").strip().lower()

            if cmd == "kill":
                process.kill()
            elif cmd == "exit":
                process.kill()
                print("Goodbye!")
                break

        else:
            cmd = input("Commands: [launch] [detect] [setdir] [exit]\n> ").strip().lower()

            if cmd == "exit":
                print("Goodbye!")
                break

            elif cmd == "detect":
                devices = detect.scan()
                print(f"✓ Scanned: {len(devices)} device(s) found")
                input("Press Enter...")
                continue

            elif cmd == "setdir":
                new_dir = input("Enter new data directory path:\n> ").strip()
                if new_dir:
                    new_dir = str(Path(new_dir).expanduser().resolve())
                    try:
                        Path(new_dir).mkdir(parents=True, exist_ok=True)
                        test_file = Path(new_dir) / ".write_test"
                        test_file.write_text("test")
                        test_file.unlink()
                        DATA_DIR = new_dir
                        CONFIG_FILE.write_text(json.dumps({"data_dir": DATA_DIR}))
                        print(f"✅ Data directory set to: {DATA_DIR}")
                    except (OSError, PermissionError) as e:
                        print(f"❌ Cannot write to {new_dir}: {e}")
                input("Press Enter...")
                continue

            elif cmd == "launch":
                devices = detect.scan()

                if not detect.check_config(DATA_DIR):
                    input("No printer.cfg found. Press Enter...")
                    continue

                if len(devices) == 0:
                    input("No USB devices found. Press Enter...")
                    continue

                selected = devices[0]
                if len(devices) > 1:
                    try:
                        idx = int(input(f"Select device [0-{len(devices)-1}]: "))
                        if 0 <= idx < len(devices):
                            selected = devices[idx]
                        else:
                            input("Invalid selection. Press Enter...")
                            continue
                    except ValueError:
                        input("Invalid input. Press Enter...")
                        continue

                if not process.check_serial_access(selected):
                    print("\n⚠️  Cannot access serial port.")
                    print("   Run this command and log out/back in (or maybe this one newgrp uucp):")
                    print("     sudo usermod -aG uucp $USER")
                    input("\nPress Enter...")
                    continue

                detect.update_serial(DATA_DIR, selected)
                print(f"✅ Serial updated: {os.path.basename(selected)}")
                process.start(DATA_DIR)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        process.kill()
        print("\nGoodbye!")
        sys.exit(0)
