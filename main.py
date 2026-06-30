import os
import sys
import json
import argparse
import re
from pathlib import Path
import detect
import process
from farm import Farm

# ── ANSI colors ──────────────────────────────────────────────────
PURPLE = "\033[38;2;211;211;255m"
GREEN = "\033[32m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

def strip_ansi(s):
    return ANSI_RE.sub('', s)

def vis_width(s):
    w = 0
    for ch in strip_ansi(s):
        if ord(ch) >= 0x2000:
            w += 2
        else:
            w += 1
    return w

# ── Config ───────────────────────────────────────────────────────
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


# ── Label helpers ───────────────────────────────────────────────
def _alpha_to_num(s):
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - ord('a') + 1)
    return n


def _num_to_alpha(n):
    result = ''
    while n > 0:
        n -= 1
        result = chr(n % 26 + ord('a')) + result
        n //= 26
    return result


def _parse_label_range(label):
    m = re.match(r'^([a-zA-Z]+)(\d+)$', label)
    if not m:
        return None
    return m.group(1).lower(), int(m.group(2))


def _generate_rectangle(left, right):
    l = _parse_label_range(left)
    r = _parse_label_range(right)
    if not l or not r:
        return set()
    row_start = _alpha_to_num(l[0])
    row_end = _alpha_to_num(r[0])
    col_start = l[1]
    col_end = r[1]
    result = set()
    for rn in range(row_start, row_end + 1):
        rl = _num_to_alpha(rn)
        for c in range(col_start, col_end + 1):
            result.add(f"{rl}{c}")
    return result


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


def _parse_selectors(spec):
    targets = {}
    parts = spec.split('.')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if ':' in part:
            left, right = part.split(':', 1)
            for label in _generate_rectangle(left.strip(), right.strip()):
                inst = _resolve_instance(label)
                if inst:
                    targets[inst.id] = inst
        elif ',' in part:
            for ref in part.split(','):
                ref = ref.strip()
                if ref:
                    inst = _resolve_instance(ref)
                    if inst:
                        targets[inst.id] = inst
        else:
            inst = _resolve_instance(part)
            if inst:
                targets[inst.id] = inst
    return list(targets.values())


# ── Template/device pickers ─────────────────────────────────────
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


# ── Core commands ────────────────────────────────────────────────
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


def cmd_launch(inst):
    if not inst.serial:
        print(f"{inst.name} ({inst.label}) has no serial device assigned")
        return
    if not process.check_serial_access(inst.serial):
        print(f"Cannot access serial: {inst.serial}")
        print("Try: newgrp uucp")
        return
    if process.start(_farm, inst):
        p = _farm.ports(inst.id)
        print(f"\u2705  {inst.name} ({inst.label}) launched")
        print(f"   Moonraker: http://localhost:{p['moonraker']}")
        print(f"   Mainsail:  http://localhost:{p['mainsail']}")
    else:
        print(f"{inst.name} is already running")


def cmd_stop(inst):
    print(f"\u2705  {inst.name} ({inst.label}) stopped" if process.stop(inst.id)
          else f"{inst.name} ({inst.label}) was not running")


def cmd_launch_all():
    launched = 0
    for inst in _farm.instances:
        if inst.serial and not process.is_running(inst.id):
            cmd_launch(inst)
            launched += 1
    if launched == 0:
        print("All instances are already running")
    else:
        print(f"\u2705  {launched}/{len(_farm.instances)} instances launched")


def cmd_stop_all():
    process.stop_all()
    print("\u2705  All instances stopped")


def _cmd_launch_targets(targets):
    if not targets:
        print("No matching instances found")
        return
    for inst in targets:
        cmd_launch(inst)


def _cmd_stop_targets(targets):
    if not targets:
        print("No matching instances found")
        return
    for inst in targets:
        cmd_stop(inst)


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
        return f"\u251c{'─' * (id_w + 2)}\u253c{'─' * (name_w + 2)}\u253c{'─' * (label_w + 2)}\u253c{'─' * 18}\u253c{'─' * 9}\u2524"

    print(f"\u250c{'─' * (id_w + 2)}\u252c{'─' * (name_w + 2)}\u252c{'─' * (label_w + 2)}\u252c{'─' * 18}\u252c{'─' * 9}\u2510")
    print(f"\u2502 {'ID':>{id_w}} \u2502 {'Name':<{name_w}} \u2502 {'Label':<{label_w}} \u2502 {'Serial':<16} \u2502 {'State':<7} \u2502")
    print(sep())
    for inst, state in rows:
        icon = {"running": "\U0001f7e2", "stopped": "\u26aa", "error": "\U0001f534"}.get(state, "\u26aa")
        s = os.path.basename(inst.serial)[:16] if inst.serial else "(none)"
        print(f"\u2502 {inst.id:>{id_w}} \u2502 {inst.name:<{name_w}} \u2502 {inst.label:<{label_w}} \u2502 {s:<16} \u2502 {icon:<7} \u2502")
    print(f"\u2514{'─' * (id_w + 2)}\u2534{'─' * (name_w + 2)}\u2534{'─' * (label_w + 2)}\u2534{'─' * 18}\u2534{'─' * 9}\u2518")


def cmd_status():
    if not _farm or not _farm.instances:
        print("No instances configured.")
        return
    _render_table(process.status(_farm))


# ── Main screen builder ─────────────────────────────────────────
def _grid_display():
    if not _farm or not _farm.instances:
        return [], [], False

    rows = {}
    uncategorized = []
    url_lines = []

    for inst, state in process.status(_farm):
        pl = _parse_label_range(inst.label)
        if pl:
            letter, num = pl
            rows.setdefault(letter, []).append((num, inst, state))
        else:
            uncategorized.append((inst, state))

        if state == "running":
            p = _farm.ports(inst.id)
            url_lines.append(f"    {inst.label}  http://localhost:{p['mainsail']}")

    grid_lines = []
    for letter in sorted(rows.keys()):
        items = sorted(rows[letter], key=lambda x: x[0])
        cells = []
        for num, inst, state in items:
            icon = "\U0001f7e2" if state == "running" else "\u26aa"
            cells.append(f"{inst.label} {icon}")
        grid_lines.append("  " + "  ".join(cells))

    for inst, state in uncategorized:
        icon = "\U0001f7e2" if state == "running" else "\u26aa"
        grid_lines.append(f"  {inst.label} {icon}")

    return grid_lines, url_lines, True


def _build_content():
    total = len(_farm.instances) if _farm else 0
    running = sum(1 for inst in (_farm.instances or []) if process.is_running(inst.id)) if _farm else 0

    grid_lines, url_lines, has_any = _grid_display()

    lines = []
    margin = "  "

    lines.append(f"{margin}{PURPLE}{BOLD}FARM{RESET}")
    lines.append("")
    lines.append(f"{margin}{BOLD}\U0001f4c1{RESET}  {DATA_DIR}")
    parts = []
    if total > 0:
        parts.append(f"{total} printer{'s' if total > 1 else ''}")
    parts.append(f"{running} active")
    lines.append(f"{margin}\u26a1  {' \u00b7 '.join(parts)}")
    lines.append("")
    lines.append(f"{margin}{BOLD}PRINTERS{RESET}")
    lines.append("")
    if has_any:
        lines.extend(grid_lines)
        lines.append("")
        if url_lines:
            lines.append(f"{margin}{GREEN}\U0001f517  Running{RESET}")
            lines.extend(url_lines)
            lines.append("")
    else:
        lines.append(f"{margin}\U0001f4a1  First time?  Type {GREEN}p{RESET} then add")
        lines.append("")

    lines.append(f"{margin}{BOLD}GENERAL{RESET}")
    lines.append("")
    lines.append(f"{margin}{GREEN}[p]{RESET}  printers    {GREEN}[d]{RESET}  detect")
    lines.append(f"{margin}{GREEN}[s]{RESET}  setdir      {GREEN}[h]{RESET}  help")
    lines.append(f"{margin}{GREEN}[q]{RESET}  quit")
    lines.append("")
    lines.append(f"{margin}{BOLD}INSTANCES{RESET}")
    lines.append("")
    lines.append(f"{margin}{GREEN}[la]{RESET}  launch all          {GREEN}[sa]{RESET}  stop all")
    lines.append(f"{margin}{GREEN}l-a1{RESET}  launch a1            {GREEN}s-a1{RESET}  stop a1")
    lines.append(f"{margin}   l-a1:a3  launch range  |  l-a1:b2  launch rectangle")
    lines.append("")
    lines.append(f"{margin}\U0001f4a1  Type a label or nickname to open its panel")
    lines.append(f"{margin}     e.g.  {GREEN}a1{RESET}  or  {GREEN}cherry{RESET}")

    return lines


def render_status():
    os.system('clear')
    lines = _build_content()
    width = max(vis_width(line) for line in lines) + 4
    print('\u250c' + '─' * (width - 2) + '\u2510')
    for line in lines:
        clean = strip_ansi(line)
        pad = width - vis_width(line) - 3
        if pad < 0:
            pad = 0
        print('\u2502 ' + line + ' ' * pad + '\u2502')
    print('\u2514' + '─' * (width - 2) + '\u2518')


# ── Help menu ─────────────────────────────────────────────────────
def _help_menu():
    os.system('clear')
    lines = []
    lines.append(f"  {BOLD}HELP  \u2014  FARM{RESET}")
    lines.append("")
    lines.append(f"  {BOLD}General{RESET}")
    lines.append(f"  {GREEN}p{RESET}            Printer management menu (add, status)")
    lines.append(f"  {GREEN}d{RESET}            Rescan USB devices")
    lines.append(f"  {GREEN}s{RESET}            Set data directory")
    lines.append(f"  {GREEN}q{RESET}            Quit")
    lines.append("")
    lines.append(f"  {BOLD}Launch / Stop{RESET}")
    lines.append(f"  {GREEN}la{RESET}           Launch all printers")
    lines.append(f"  {GREEN}sa{RESET}           Stop all printers")
    lines.append(f"  {GREEN}l-a1{RESET}         Launch printer a1")
    lines.append(f"  {GREEN}l-a1:a3{RESET}      Launch a1 through a3 (range)")
    lines.append(f"  {GREEN}l-a1:b2{RESET}      Launch rectangle a1 to b2")
    lines.append(f"  {GREEN}l-cherry{RESET}     Launch by nickname")
    lines.append(f"  {GREEN}l-a1:b2.cherry{RESET}  Union: rectangle + nickname")
    lines.append(f"  {GREEN}s-a1{RESET}         Stop printer a1")
    lines.append(f"  {GREEN}s-a1:a3{RESET}      Stop a1 through a3")
    lines.append("")
    lines.append(f"  {BOLD}Edit{RESET}")
    lines.append(f"  {GREEN}a1{RESET}           Open a1's edit panel (rename/label/assign/remove)")
    lines.append(f"  {GREEN}cherry{RESET}       Open cherry's edit panel")
    lines.append("")
    lines.append(f"  \u2937  Only existing instances are affected")
    lines.append(f"     (like cropping \u2014 l-a1:b99 won't error)")

    width = max(vis_width(line) for line in lines) + 4
    print('\u250c' + '─' * (width - 2) + '\u2510')
    for line in lines:
        pad = width - vis_width(line) - 3
        if pad < 0:
            pad = 0
        print('\u2502 ' + line + ' ' * pad + '\u2502')
    print('\u2514' + '─' * (width - 2) + '\u2518')
    input("\nPress Enter...")


# ── Printer edit menu ────────────────────────────────────────────
def _printer_menu(inst):
    while True:
        os.system('clear')
        state = "running" if process.is_running(inst.id) else "stopped"
        icon = {"running": "\U0001f7e2", "stopped": "\u26aa", "error": "\U0001f534"}[state]
        serial_short = os.path.basename(inst.serial)[:30] if inst.serial else "(none)"
        p = _farm.ports(inst.id)

        lines = []
        lines.append(f"  {icon}  {BOLD}{inst.label}{RESET}")
        lines.append("")
        lines.append(f"  {BOLD}Name:{RESET}   {inst.name}")
        lines.append(f"  {BOLD}Serial:{RESET} {serial_short}")
        if state == "running":
            lines.append(f"  {GREEN}URL:{RESET}    http://localhost:{p['mainsail']}{RESET}")
        else:
            lines.append(f"  {BOLD}Ports:{RESET}  Moonraker:{p['moonraker']}  Mainsail:{p['mainsail']}")
        lines.append("")
        lines.append(f"  {GREEN}[r]{RESET}  rename    {GREEN}[l]{RESET}  relabel")
        lines.append(f"  {GREEN}[a]{RESET}  assign    {GREEN}[x]{RESET}  remove")
        lines.append(f"  {GREEN}[/]{RESET}  back")

        width = max(vis_width(line) for line in lines) + 4
        print('\u250c' + '─' * (width - 2) + '\u2510')
        for line in lines:
            pad = width - vis_width(line) - 3
            if pad < 0:
                pad = 0
            print('\u2502 ' + line + ' ' * pad + '\u2502')
        print('\u2514' + '─' * (width - 2) + '\u2518')

        raw = input("> ").strip().lower()
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


# ── Printer management menu ──────────────────────────────────────
def _printers_menu():
    while True:
        os.system('clear')

        lines = []
        lines.append(f"  {BOLD}PRINTER MANAGEMENT{RESET}")
        lines.append("")
        lines.append(f"  {GREEN}[add]{RESET}     add a new printer")
        lines.append(f"  {GREEN}[status]{RESET}  show instance table")
        lines.append(f"  {GREEN}[/]{RESET}       back")

        width = max(vis_width(line) for line in lines) + 4
        print('\u250c' + '─' * (width - 2) + '\u2510')
        for line in lines:
            pad = width - vis_width(line) - 3
            if pad < 0:
                pad = 0
            print('\u2502 ' + line + ' ' * pad + '\u2502')
        print('\u2514' + '─' * (width - 2) + '\u2518')

        raw = input("> ").strip().lower()
        if not raw:
            continue
        if raw in ("back", "/"):
            break
        elif raw == "add":
            cmd_add()
        elif raw == "status":
            cmd_status()
        input("Press Enter...")


# ── Main loop ─────────────────────────────────────────────────────
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

        raw = input("\n> ").strip().lower()
        if not raw:
            continue

        if raw in ("q", "quit", "exit"):
            if process.running_count() > 0:
                process.stop_all()
            print("Goodbye! \n")
            break
        elif raw in ("p", "printers"):
            _printers_menu()
        elif raw in ("d", "detect"):
            d = detect.scan()
            print(f"\u2713  Scanned: {len(d)} device(s) found")
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
                    print(f"\u2705  Data directory set to: {DATA_DIR}")
                except (OSError, PermissionError) as e:
                    print(f"\u274c  {e}")
                input("Press Enter...")
        elif raw in ("h", "help"):
            _help_menu()
        elif raw == "la":
            cmd_launch_all()
            input("Press Enter...")
        elif raw == "sa":
            cmd_stop_all()
            input("Press Enter...")
        elif raw.startswith("l-"):
            targets = _parse_selectors(raw[2:])
            _cmd_launch_targets(targets)
            input("Press Enter...")
        elif raw.startswith("s-"):
            targets = _parse_selectors(raw[2:])
            _cmd_stop_targets(targets)
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
