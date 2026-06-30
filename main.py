import os
import sys
import json
import argparse
import re
from pathlib import Path
import detect
import process
from farm import Farm

APP_DIR = Path(__file__).parent
CONFIG_FILE = APP_DIR / ".instances_config.json"
DATA_DIR = str(Path.home() / "Documents" / "instances")
_farm = None


def load_data_dir():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())["data_dir"]
        except (json.JSONDecodeError, KeyError):
            pass
    return str(Path.home() / "Documents" / "instances")


def setup_data_dir():
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def _parse_label_range(label):
    m = re.match(r'^([a-zA-Z]+)(\d+)$', label)
    if not m:
        return None
    return m.group(1).lower(), int(m.group(2))


def _resolve_instance(identifier):
    if not _farm:
        return None
    try:
        return _farm._get(int(identifier))
    except (ValueError, KeyError):
        pass
    identifier = identifier.lower()
    for inst in _farm.instances:
        if inst.label.lower() == identifier:
            return inst
    for inst in _farm.instances:
        if inst.name.lower() == identifier:
            return inst
    return None


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


def cmd_add():
    template = _pick_template()
    all_devices = detect.scan()
    available = _farm.unassigned_usb_devices(all_devices) if _farm else []
    device = _pick_device(available) if available else ""
    label = Farm.default_label(_farm.next_id)
    inst = _farm.create(label=label, serial=device, template_path=template)
    print(f"  Created Instance {inst.id} [{inst.label}]")


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
        print(f"  Removed Instance {instance_id}")
    else:
        print("Cancelled")


def cmd_rename(instance_id, name):
    try:
        _farm.rename(instance_id, name)
        print(f"  Instance {instance_id} renamed to '{name}'")
    except KeyError:
        print(f"Instance {instance_id} not found")


def cmd_label(instance_id, label):
    try:
        _farm.relabel(instance_id, label)
        print(f"  Instance {instance_id} labeled '{label}'")
    except KeyError:
        print(f"Instance {instance_id} not found")


def cmd_assign(instance_id):
    try:
        inst = _farm._get(instance_id)
    except KeyError:
        print(f"Instance {instance_id} not found")
        return

    all_devices = detect.scan()
    available = _farm.unassigned_usb_devices(all_devices) if _farm else []
    if not available:
        print("No unassigned USB devices available")
        return

    device = _pick_device(available)
    if device:
        _farm.assign_serial(instance_id, device)
        print(f"  Serial updated for Instance {instance_id}")


def cmd_launch(inst):
    if not inst.serial:
        print(f"Instance {inst.id} ({inst.label}) has no serial device assigned")
        return
    if not process.check_serial_access(inst.serial):
        print(f"Cannot access serial: {inst.serial}")
        print("Try: newgrp uucp")
        return
    if process.start(_farm, inst):
        p = _farm.ports(inst.id)
        print(f"  Instance {inst.id} ({inst.label}) launched")
        print(f"  Moonraker: http://localhost:{p['moonraker']}")
        print(f"  Mainsail:  http://localhost:{p['mainsail']}")
    else:
        print(f"Instance {inst.id} is already running")


def cmd_stop(inst):
    print(f"  Instance {inst.id} stopped" if process.stop(inst.id)
          else f"  Instance {inst.id} was not running")


def cmd_launch_all():
    launched = 0
    for inst in _farm.instances:
        if inst.serial and not process.is_running(inst.id):
            cmd_launch(inst)
            launched += 1
    if launched == 0:
        print("All instances are already running")
    else:
        print(f"  {launched}/{len(_farm.instances)} instances launched")


def cmd_stop_all():
    process.stop_all()
    print("  All instances stopped")


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
        icon = {"running": "🟢", "stopped": "⚪", "error": "🔴"}.get(state, "⚪")
        s = os.path.basename(inst.serial)[:16] if inst.serial else "(none)"
        print(f"│ {inst.id:>{id_w}} │ {inst.name:<{name_w}} │ {inst.label:<{label_w}} │ {s:<16} │ {icon:<7} │")
    print(f"└{'─' * (id_w + 2)}┴{'─' * (name_w + 2)}┴{'─' * (label_w + 2)}┴{'─' * 18}┴{'─' * 9}┘")


def cmd_status():
    if not _farm or not _farm.instances:
        print("No instances configured.")
        return
    _render_table(process.status(_farm))


def _instance_summary():
    lines = []
    if _farm:
        for inst in _farm.instances:
            icon = "🟢" if process.is_running(inst.id) else "⚪"
            tag = f' "{inst.name}"' if inst.name != f"Instance {inst.id}" else ""
            lines.append(f"  [{inst.id}] ({inst.label}){tag} {icon}")
    if not lines:
        lines.append("  (none)")
    return "\n".join(lines)


def render_status():
    os.system('clear')
    print("Instances\n")

    print(f"Data: {DATA_DIR}\n")

    devices = detect.scan()
    serial_to_inst = {}
    if _farm:
        for inst in _farm.instances:
            if inst.serial:
                serial_to_inst[inst.serial] = inst

    print("Devices:")
    shown = 0
    for dev in devices:
        if dev in serial_to_inst:
            inst = serial_to_inst[dev]
            print(f"  Instance {inst.id} ({inst.label}) - {os.path.basename(dev)}")
        else:
            print(f"  (unassigned) - {os.path.basename(dev)}")
        shown += 1
    if shown == 0:
        print("  (none)")
    print()

    print("Instances:")
    print(_instance_summary())
    print()


def _printer_menu(inst):
    while True:
        os.system('clear')
        state = "running" if process.is_running(inst.id) else "stopped"
        icon = {"running": "🟢", "stopped": "⚪", "error": "🔴"}[state]
        serial_short = os.path.basename(inst.serial)[:30] if inst.serial else "(none)"
        p = _farm.ports(inst.id)

        print(f" {icon}  Instance {inst.id} ({inst.label})\n")
        print(f"  Name:   {inst.name}")
        print(f"  Label:  {inst.label}")
        print(f"  Serial: {serial_short}")
        if state == "running":
            print(f"  URL:    http://localhost:{p['mainsail']}")
        else:
            print(f"  Ports:  Moonraker:{p['moonraker']}  Mainsail:{p['mainsail']}")
        print()

        raw = input(
            "  [r] rename   [l] label   [a] assign\n"
            "  [x] remove   [/] back\n> "
        ).strip().lower()
        if not raw:
            continue

        if raw in ("back", "/"):
            break
        elif raw in ("r", "rename"):
            name = input("New name: ").strip()
            if name:
                cmd_rename(inst.id, name)
                inst = _farm._get(inst.id)
        elif raw in ("l", "label"):
            label = input("New label (letters + digits, e.g. b18): ").strip().lower()
            if label:
                cmd_label(inst.id, label)
                inst = _farm._get(inst.id)
        elif raw in ("a", "assign"):
            cmd_assign(inst.id)
        elif raw in ("x", "remove"):
            cmd_remove(inst.id)
            try:
                _farm._get(inst.id)
            except KeyError:
                break
        input("Press Enter...")


def _printers_menu():
    while True:
        os.system('clear')
        print("Printer Management\n")
        if _farm and _farm.instances:
            print("Instances:")
            print(_instance_summary())
            print()

        raw = input(
            "  [add]      add new printer\n"
            "  [status]   show instance table\n"
            "  [/]        back\n> "
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
            "  [p] printers   [d] detect   [s] setdir\n"
            "  [la] launch all    [sa] stop all\n"
            "  [q] quit\n"
            "  Or type a printer label/ID/name to manage it\n> "
        ).strip().lower()
        if not raw:
            continue

        if raw in ("q", "quit", "exit"):
            if process.running_count() > 0:
                process.stop_all()
            print("Goodbye!")
            break
        elif raw in ("p", "printers"):
            _printers_menu()
        elif raw in ("d", "detect"):
            d = detect.scan()
            print(f"Scanned: {len(d)} device(s) found")
            input("Press Enter...")
        elif raw in ("s", "setdir"):
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
                    print(f"Data directory set to: {DATA_DIR}")
                except (OSError, PermissionError) as e:
                    print(f"  {e}")
                input("Press Enter...")
        elif raw == "la":
            cmd_launch_all()
            input("Press Enter...")
        elif raw == "sa":
            cmd_stop_all()
            input("Press Enter...")
        elif raw.startswith("l-"):
            inst = _resolve_instance(raw[2:])
            if inst:
                cmd_launch(inst)
            else:
                print(f"Instance '{raw[2:]}' not found")
            input("Press Enter...")
        elif raw.startswith("s-"):
            inst = _resolve_instance(raw[2:])
            if inst:
                cmd_stop(inst)
            else:
                print(f"Instance '{raw[2:]}' not found")
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
