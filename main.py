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
    print(" 🪄  Instance 1 \n")
    print(f" \U0001f4c1  Data: {DATA_DIR}\n")

    devices = detect.scan()
    serial_to_inst = {}
    if _farm:
        for inst in _farm.instances:
            if inst.serial:
                serial_to_inst[inst.serial] = inst
    print(" \U0001f4cb  Devices:")
    shown = 0
    for dev in devices:
        if dev in serial_to_inst:
            inst = serial_to_inst[dev]
            print(f"       Instance {inst.id} ({inst.label}) - {os.path.basename(dev)}")
            shown += 1
        else:
            print(f"       (unassigned) - {os.path.basename(dev)}")
            shown += 1
    if shown == 0:
        print("       (none)")
    print()

    print(" \U0001f4e6  Instances:")
    print(_instance_summary())
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


def _resolve_instance(identifier):
    if not _farm:
        return None
    try:
        return _farm._get(int(identifier))
    except (ValueError, KeyError):
        pass
    for inst in _farm.instances:
        if inst.label.lower() == identifier:
            return inst
    for inst in _farm.instances:
        if inst.name.lower() == identifier.lower():
            return inst
    return None


def _instance_summary():
    lines = []
    if _farm:
        for inst, state in process.status(_farm):
            icon = {"running": "\U0001f7e2", "stopped": "\u26aa", "error": "\U0001f534"}[state]
            tag = f' "{inst.name}"' if inst.name != f"Instance {inst.id}" else ""
            url = f"  http://localhost:{_farm.ports(inst.id)['mainsail']}" if state == "running" else ""
            lines.append(f"       [{inst.id}] ({inst.label}){tag} {icon}{url}")
    if not lines:
        lines.append("       (none)")
    return "\n".join(lines)


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

    print(f"\n\u2705  {count} instances created.")


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


def cmd_launch(identifier):
    inst = _resolve_instance(identifier)
    if inst is None:
        print(f"Printer '{identifier}' not found")
        return
    if not inst.serial:
        print(f"Instance {inst.id} has no serial device assigned")
        return
    if not process.check_serial_access(inst.serial):
        print(f"Cannot access serial: {inst.serial}")
        print("Try: newgrp uucp")
        return
    if process.start(_farm, inst):
        p = _farm.ports(inst.id)
        print(f"\u2705  Instance {inst.id} ({inst.label}) launched")
        print(f"   Moonraker: http://localhost:{p['moonraker']}")
        print(f"   Mainsail:  http://localhost:{p['mainsail']}")
    else:
        print(f"Instance {inst.id} is already running")


def cmd_launch_all():
    launched = 0
    for inst in _farm.instances:
        if inst.serial and process.start(_farm, inst):
            launched += 1
    print(f"\u2705  {launched}/{len(_farm.instances)} instances launched")


def cmd_stop(identifier):
    inst = _resolve_instance(identifier)
    if inst is None:
        print(f"Printer '{identifier}' not found")
        return
    print(f"\u2705  Instance {inst.id} stopped" if process.stop(inst.id)
          else f"Instance {inst.id} was not running")


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
        print("No instances configured.")
        return
    _render_table(process.status(_farm))


def _printer_menu(inst):
    while True:
        os.system('clear')
        state = "running" if process.is_running(inst.id) else "stopped"
        icon = {"running": "\U0001f7e2", "stopped": "\u26aa", "error": "\U0001f534"}[state]
        serial_short = os.path.basename(inst.serial)[:30] if inst.serial else "(none)"

        print(f" \U0001fa84  Instance {inst.id} ({inst.label}) {icon}\n")
        print(f"  Name:   {inst.name}")
        print(f"  Label:  {inst.label}")
        print(f"  Serial: {serial_short}")
        p = _farm.ports(inst.id)
        if process.is_running(inst.id):
            print(f"  Moonraker: http://localhost:{p['moonraker']}")
            print(f"  Mainsail:  http://localhost:{p['mainsail']}")
        else:
            print(f"  Ports:   Moonraker:{p['moonraker']}  Mainsail:{p['mainsail']}")
        print()

        raw = input(
            "  [launch]   [stop]    [rename]  [label]\n"
            "  [assign]   [remove]  [back] or [/]\n> "
        ).strip().lower()
        if not raw:
            continue

        if raw in ("back", "/"):
            break
        elif raw == "launch":
            cmd_launch(str(inst.id))
        elif raw == "stop":
            cmd_stop(str(inst.id))
        elif raw == "remove":
            cmd_remove(inst.id)
            try:
                _farm._get(inst.id)
            except KeyError:
                break
        elif raw == "rename":
            name = input("New name: ").strip()
            if name:
                cmd_rename(inst.id, name)
                inst = _farm._get(inst.id)
        elif raw == "label":
            label = input("New label (letters + digits, e.g. b18): ").strip().lower()
            if label:
                cmd_label(inst.id, label)
                inst = _farm._get(inst.id)
        elif raw == "assign":
            cmd_assign(inst.id)
        input("Press Enter...")





def _printers_menu():
    while True:
        os.system('clear')
        print(" 🪄  Instance 1 FARM - Printer Management\n")
        if _farm and _farm.instances:
            print(" \U0001f4e6  Instances:")
            print(_instance_summary())
            print()

        raw = input(
            "Printer Management:\n"
            "  [add]              add new printer\n"
            "  [status]           show printer table\n"
            "  [back] or [/]      return to main menu\n> "
        ).strip().lower()
        if not raw:
            continue

        if raw in ("back", "/"):
            break
        elif raw == "add":
            cmd_add()
        elif raw == "status":
            cmd_status()
        input("Press Enter...")


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

        raw = input(
            "Commands:\n"
            "  [printers]  add, status\n"
            "  [detect]    rescan USB devices\n"
            "  [setdir]    change data directory\n"
            "\n"
            "  Or type a printer (label/ID/name) to manage it\n"
            "\n"
            "  [exit/quit]  quit\n"
            "\n> "
        ).strip().lower()
        if not raw:
            continue

        if raw in ("exit", "quit"):
            if process.running_count() > 0:
                process.stop_all()
            print("Goodbye! \n")
            break
        elif raw == "printers":
            _printers_menu()
        elif raw == "detect":
            d = detect.scan()
            print(f"\u2713  Scanned: {len(d)} device(s) found")
            input("Press Enter...")
        elif raw == "setdir":
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
                input("Press Enter...")
        else:
            inst = _resolve_instance(raw)
            if inst:
                _printer_menu(inst)
            else:
                print(f"Unknown command or printer '{raw}' not found")
                input("Press Enter...")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        process.stop_all()
        print("\nGoodbye!")
        sys.exit(0)
