import os
import sys
import json
import argparse
from pathlib import Path
import detect
import process
from farm import Farm

APP_DIR = Path(__file__).parent
CONFIG_FILE = APP_DIR / ".instance1_config.json"
DATA_DIR = str(Path.home() / "Documents" / "instance1")
_farm = None


def load_data_dir():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())["data_dir"]
        except (json.JSONDecodeError, KeyError):
            pass
    return str(Path.home() / "Documents" / "instance1")


def setup_data_dir():
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def render_status():
    os.system('clear')
    print(" 🪄  Instance 1 FARM\n")
    print(f" \U0001f4c1  Data: {DATA_DIR}\n")

    devices = detect.scan()
    assigned = _farm.assigned_serials() if _farm else set()
    available = len([d for d in devices if d not in assigned])
    print(f" \U0001f4cb  Devices: {len(devices)} total ({len(assigned)} assigned, {available} available)\n")

    if _farm and _farm.instances:
        running = process.running_count()
        print(f" \U0001f4e6  Instances: {len(_farm.instances)} total, {running} running")
    else:
        print(" \U0001f4e6  Instances: none (use `setup` or `add`)")
    print()


def _pick_template():
    config_dir = APP_DIR / "klipper_core" / "config"
    templates = sorted(config_dir.rglob("*.cfg"))
    if not templates:
        print("No templates found in klipper_core/config/")
        return ""

    print("\nKlipper config templates (first 30):")
    for i, t in enumerate(templates[:30]):
        print(f"  [{i}] {t.relative_to(config_dir)}")
    if len(templates) > 30:
        print(f"  ... and {len(templates) - 30} more")

    print("  (or type part of a filename to search)")
    choice = input(f"Select template [0-{min(29, len(templates) - 1)}]: ").strip()
    if not choice:
        return ""

    try:
        idx = int(choice)
        if 0 <= idx < len(templates):
            return str(templates[idx])
    except ValueError:
        pass

    matches = [t for t in templates if choice.lower() in t.name.lower()]
    if len(matches) == 1:
        return str(matches[0])
    elif len(matches) > 1:
        print("Multiple matches:")
        for i, m in enumerate(matches):
            print(f"  [{i}] {m.relative_to(config_dir)}")
        try:
            idx = int(input("Select: "))
            if 0 <= idx < len(matches):
                return str(matches[idx])
        except ValueError:
            pass
    else:
        print("No match found")
    return ""


def _pick_device(available, prompt="Select device"):
    if not available:
        print("No unassigned USB devices found")
        return ""

    print(f"\n{prompt}:")
    for i, dev in enumerate(available):
        print(f"  [{i}] {os.path.basename(dev)}")
    print("  (leave blank to skip)")
    choice = input("> ").strip()
    if not choice:
        return ""
    try:
        idx = int(choice)
        if 0 <= idx < len(available):
            return available[idx]
    except ValueError:
        pass
    return ""


def cmd_setup():
    try:
        count = int(input("How many printers? ").strip())
    except ValueError:
        print("Invalid number")
        return
    if count < 1:
        return

    template = _pick_template()
    all_devices = detect.scan()
    available = _farm.unassigned_usb_devices(all_devices)

    for i in range(count):
        label = Farm.default_label(_farm.next_id)
        print(f"\n--- Instance {_farm.next_id} ({label}) ---")
        device = _pick_device(available) if available else ""
        if device:
            available.remove(device)
        inst = _farm.create(label=label, serial=device, template_path=template)
        print(f"  \u2705  Created Instance {inst.id} [{inst.label}]")

    print(f"\n\u2705  {count} instances created. Use `launch all` to start.")


def cmd_add():
    template = _pick_template()
    all_devices = detect.scan()
    available = _farm.unassigned_usb_devices(all_devices)
    device = _pick_device(available) if available else ""
    label = Farm.default_label(_farm.next_id)
    inst = _farm.create(label=label, serial=device, template_path=template)
    print(f"\u2705  Created Instance {inst.id} [{inst.label}]")


def cmd_remove(instance_id):
    try:
        inst = _farm._get(instance_id)
    except KeyError:
        print(f"Instance {instance_id} not found")
        return
    print(f"Remove Instance {inst.id} ({inst.name}, {inst.label})?")
    if input("Type 'yes' to confirm: ").strip().lower() == "yes":
        if process.is_running(instance_id):
            process.stop(instance_id)
        _farm.remove(instance_id)
        print(f"\u2705  Removed Instance {instance_id}")
    else:
        print("Cancelled")


def cmd_rename(instance_id, name):
    try:
        _farm.rename(instance_id, name)
        print(f"\u2705  Instance {instance_id} renamed to '{name}'")
    except KeyError:
        print(f"Instance {instance_id} not found")


def cmd_label(instance_id, label):
    try:
        _farm.relabel(instance_id, label)
        print(f"\u2705  Instance {instance_id} labeled '{label}'")
    except KeyError:
        print(f"Instance {instance_id} not found")


def cmd_assign(instance_id):
    try:
        inst = _farm._get(instance_id)
    except KeyError:
        print(f"Instance {instance_id} not found")
        return

    all_devices = detect.scan()
    available = _farm.unassigned_usb_devices(all_devices)
    if not available:
        print("No unassigned USB devices available")
        return

    device = _pick_device(available)
    if device:
        _farm.assign_serial(instance_id, device)
        print(f"\u2705  Serial updated for Instance {instance_id}")


def cmd_launch(instance_id):
    try:
        inst = _farm._get(instance_id)
    except KeyError:
        print(f"Instance {instance_id} not found")
        return

    if not inst.serial:
        print(f"Instance {instance_id} has no serial device assigned")
        return
    if not process.check_serial_access(inst.serial):
        print(f"Cannot access serial: {inst.serial}")
        print("Try: newgrp uucp")
        return

    if process.start(_farm, inst):
        p = _farm.ports(inst.id)
        print(f"\u2705  Instance {instance_id} ({inst.label}) launched")
        print(f"   Moonraker: http://localhost:{p['moonraker']}")
        print(f"   Mainsail:  http://localhost:{p['mainsail']}")
    else:
        print(f"Instance {instance_id} is already running")


def cmd_launch_all():
    launched = 0
    for inst in _farm.instances:
        if inst.serial and process.start(_farm, inst):
            launched += 1
    print(f"\u2705  {launched}/{len(_farm.instances)} instances launched")


def cmd_stop(instance_id):
    print(f"\u2705  Instance {instance_id} stopped" if process.stop(instance_id)
          else f"Instance {instance_id} was not running")


def cmd_stop_all():
    process.stop_all()
    print("\u2705  All instances stopped")


def _render_table(rows):
    if not rows:
        print("No instances configured.")
        return

    id_w = max(len(str(r[0].id)) for r in rows)
    name_w = max(len(r[0].name) for r in rows)
    label_w = max(len(r[0].label) for r in rows)
    id_w = max(id_w, 2)
    name_w = max(name_w, 4)
    label_w = max(label_w, 5)

    def sep():
        return f"├{'─' * (id_w + 2)}┼{'─' * (name_w + 2)}┼{'─' * (label_w + 2)}┼{'─' * 18}┼{'─' * 9}┤"

    print(f"┌{'─' * (id_w + 2)}┬{'─' * (name_w + 2)}┬{'─' * (label_w + 2)}┬{'─' * 18}┬{'─' * 9}┐")
    print(f"│ {'ID':>{id_w}} │ {'Name':<{name_w}} │ {'Label':<{label_w}} │ {'Serial':<16} │ {'State':<7} │")
    print(sep())
    for inst, state in rows:
        icon = {"running": "\U0001f7e2", "stopped": "\u26aa", "error": "\U0001f534"}.get(state, "\u26aa")
        s = os.path.basename(inst.serial)[:16] if inst.serial else "(none)"
        print(f"│ {inst.id:>{id_w}} │ {inst.name:<{name_w}} │ {inst.label:<{label_w}} │ {s:<16} │ {icon:<7} │")
    print(f"└{'─' * (id_w + 2)}┴{'─' * (name_w + 2)}┴{'─' * (label_w + 2)}┴{'─' * 18}┴{'─' * 9}┘")


def cmd_status():
    if not _farm or not _farm.instances:
        print("No instances configured. Use `setup` or `add`.")
        return
    _render_table(process.status(_farm))


def main():
    global DATA_DIR, _farm

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=str, help="data directory path")
    args = parser.parse_args()

    if args.data_dir:
        DATA_DIR = str(Path(args.data_dir).expanduser().resolve())
        CONFIG_FILE.write_text(json.dumps({"data_dir": DATA_DIR}))
    else:
        DATA_DIR = load_data_dir()

    setup_data_dir()
    _farm = Farm(DATA_DIR)

    while True:
        render_status()

        if process.running_count() > 0:
            raw = input("Commands: [stop N] [stop all] [status] [exit]\n> ").strip().lower()
            parts = raw.split(maxsplit=1)
            verb, arg = parts[0], parts[1] if len(parts) > 1 else None

            if verb == "exit":
                process.stop_all()
                print("Goodbye!")
                break
            elif verb == "status":
                cmd_status()
            elif verb == "stop":
                if arg == "all":
                    cmd_stop_all()
                elif arg:
                    try:
                        cmd_stop(int(arg))
                    except ValueError:
                        print("Usage: stop N or stop all")
                else:
                    running = [i for i in _farm.instances if process.is_running(i.id)]
                    cmd_stop(running[0].id) if len(running) == 1 else print("Specify: stop N")
            input("Press Enter...")

        else:
            raw = input(
                "Commands: [launch N] [launch all] [status] [setup] [add]\n"
                "          [remove N] [rename N] [label N] [assign N]\n"
                "          [detect] [setdir] [exit]\n> "
            ).strip().lower()
            parts = raw.split(maxsplit=1)
            verb, arg = parts[0], parts[1] if len(parts) > 1 else None

            if verb == "exit":
                print("Goodbye!")
                break
            elif verb == "detect":
                d = detect.scan()
                print(f"\u2713  Scanned: {len(d)} device(s) found")
            elif verb == "setdir":
                new = input("Enter new data directory path:\n> ").strip()
                if new:
                    new = str(Path(new).expanduser().resolve())
                    try:
                        Path(new).mkdir(parents=True, exist_ok=True)
                        (Path(new) / ".write_test").write_text("test")
                        Path(new, ".write_test").unlink()
                        DATA_DIR = new
                        CONFIG_FILE.write_text(json.dumps({"data_dir": DATA_DIR}))
                        _farm = Farm(DATA_DIR)
                        print(f"\u2705  Data directory set to: {DATA_DIR}")
                    except (OSError, PermissionError) as e:
                        print(f"\u274c  {e}")
            elif verb == "setup":
                cmd_setup()
            elif verb == "add":
                cmd_add()
            elif verb == "remove":
                if arg:
                    try:
                        cmd_remove(int(arg))
                    except ValueError:
                        print("Usage: remove N")
                else:
                    print("Usage: remove N")
            elif verb == "rename":
                if arg:
                    p2 = arg.split(maxsplit=1)
                    try:
                        iid = int(p2[0])
                        name = p2[1] if len(p2) > 1 else input("New name: ").strip()
                        cmd_rename(iid, name)
                    except ValueError:
                        print("Usage: rename N 'name'")
                else:
                    print("Usage: rename N 'name'")
            elif verb == "label":
                if arg:
                    p2 = arg.split(maxsplit=1)
                    try:
                        iid = int(p2[0])
                        label = p2[1] if len(p2) > 1 else input("New label: ").strip()
                        cmd_label(iid, label)
                    except ValueError:
                        print("Usage: label N 'label'")
                else:
                    print("Usage: label N 'label'")
            elif verb == "assign":
                if arg:
                    try:
                        cmd_assign(int(arg))
                    except ValueError:
                        print("Usage: assign N")
                else:
                    print("Usage: assign N")
            elif verb == "status":
                cmd_status()
            elif verb == "launch":
                if arg == "all":
                    cmd_launch_all()
                elif arg:
                    try:
                        cmd_launch(int(arg))
                    except ValueError:
                        print("Usage: launch N or launch all")
                elif len(_farm.instances) == 1:
                    cmd_launch(_farm.instances[0].id)
                else:
                    print("Specify: launch N")
            input("Press Enter...")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        process.stop_all()
        print("\nGoodbye!")
        sys.exit(0)
