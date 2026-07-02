import os
import sys
import json
import argparse
import re
import shutil
import signal
import select
import tty
import termios
from pathlib import Path
import detect
import process
from farm import Farm

# ── ANSI colors ──────────────────────────────────────────────────
PURPLE = "\033[38;2;211;211;255m"
LAVENDER = "\033[1m\033[38;2;180;180;235m"
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

# ── Live resize ──────────────────────────────────────────────────
_resize_flag = False

def _on_resize(signum, frame):
    global _resize_flag
    _resize_flag = True


# ── Config ───────────────────────────────────────────────────────
APP_DIR = Path(__file__).parent
CONFIG_FILE = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "farm" / "config.json"
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
    for i, t in enumerate(templates[:30], 1):
        print(f"  [{i}] {t.relative_to(config_dir)}")
    if len(templates) > 30:
        print(f"  ... and {len(templates) - 30} more")

    print("  (or type part of a filename to search)")
    choice = input(f"Select template [1-{min(30, len(templates))}]: ").strip()
    if not choice:
        return ""

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(templates):
            return str(templates[idx])
    except ValueError:
        pass

    matches = [t for t in templates if choice.lower() in t.name.lower()]
    if len(matches) == 1:
        return str(matches[0])
    elif len(matches) > 1:
        print("Multiple matches:")
        for i, m in enumerate(matches, 1):
            print(f"  [{i}] {m.relative_to(config_dir)}")
        try:
            idx = int(input("Select: ")) - 1
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
    for i, dev in enumerate(available, 1):
        print(f"  [{i}] {os.path.basename(dev)}")
    print("  (leave blank to skip)")
    choice = input("> ").strip()
    if not choice:
        return ""
    try:
        idx = int(choice) - 1
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

    default_name = f"Instance {_farm.next_id}"
    default_label = Farm.default_label(_farm.next_id)

    name = input(f"Name [{default_name}]: ").strip()
    if not name:
        name = default_name
    while _farm.name_exists(name):
        name = input(f"Name '{name}' already exists. Enter another [{default_name}]: ").strip()
        if not name:
            name = default_name

    label = input(f"Label [{default_label}]: ").strip().lower()
    if not label:
        label = default_label
    while _farm.label_exists(label):
        label = input(f"Label '{label}' already exists. Enter another [{default_label}]: ").strip().lower()
        if not label:
            label = default_label

    inst = _farm.create(name=name, label=label, serial=device, template_path=template)
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


def cmd_start_all():
    started = 0
    for inst in _farm.instances:
        if inst.serial and not process.is_running(inst.id):
            cmd_launch(inst)
            started += 1
    if started == 0:
        print("All instances are already running")
    else:
        print(f"\u2705  {started}/{len(_farm.instances)} instances started")


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


def cmd_dashboard():
    while True:
        os.system('clear')
        w = shutil.get_terminal_size().columns
        div = "-" * w
        dim_div = f"{DIM}{'-' * w}{RESET}"

        total = len(_farm.instances) if _farm else 0
        running = sum(1 for inst in (_farm.instances or []) if process.is_running(inst.id)) if _farm else 0

        print("")
        for line in _render_logo(w):
            print(line)
        print("")
        info = f"\U0001f4c1 {DATA_DIR}"
        parts = []
        if total > 0:
            parts.append(f"{total} instance{'s' if total > 1 else ''}")
        parts.append(f"{running} running")
        info += f"    \u26a1 {' \u00b7 '.join(parts)}"
        print(info)
        print(div)
        print("")
        print(f"  {LAVENDER}u{RESET}  update / rescan     {LAVENDER}/{RESET}  back")
        print("")
        print(div)
        print("")

        if total > 0:
            rows = {}
            uncategorized = []
            for inst, state in process.status(_farm):
                pl = _parse_label_range(inst.label)
                if pl:
                    letter, num = pl
                    rows.setdefault(letter, []).append((num, inst, state))
                else:
                    uncategorized.append((inst, state))

            sorted_rows = []
            for letter in sorted(rows.keys()):
                sorted_rows.append((letter, sorted(rows[letter], key=lambda x: x[0])))
            if uncategorized:
                sorted_rows.append(("_", sorted(uncategorized, key=lambda x: x[0].id)))

            for ri, (letter, items) in enumerate(sorted_rows):
                if ri > 0:
                    print(f"{dim_div}")

                for num, inst, state in items:
                    icon = "\U0001f7e2" if state == "running" else "\u26aa"
                    state_label = "running" if state == "running" else "stopped"
                    if state == "running":
                        p = _farm.ports(inst.id)
                        print(f"  {inst.label}  {inst.name}     {icon} {state_label}     http://localhost:{p['mainsail']}")
                    else:
                        print(f"  {inst.label}  {inst.name}     {icon} {state_label}")
                    if inst.serial:
                        print(f"      board: {os.path.basename(inst.serial)[:35]}")
                    else:
                        print(f"      no board assigned")
        else:
            print("No instances configured.")

        print("")
        print(div)
        print("")
        print(f"{'USB Devices':^{w}}")
        print("")
        print(div)
        print("")

        devices = detect.scan()
        if not devices:
            print("No USB devices found.")
        else:
            for i, dev in enumerate(devices, 1):
                owner = ""
                for inst in (_farm.instances or []):
                    if inst.serial == dev:
                        owner = f"  \u2190 {inst.label}"
                        break
                if not owner:
                    owner = "  \u2190 unassigned"
                print(f"  {i:2}. {dev}{owner}")

        print("")
        print(f"\u2713  {len(devices)} device(s) found \u00b7 {running} running")
        print(div)

        raw = input("\n> ").strip().lower()
        if not raw or raw in ("back", "/"):
            break
        elif raw == "u":
            continue


# ── Live resize helpers ─────────────────────────────────────────
def _render_logo(width):
    if width >= 68:
        return [
            f"{PURPLE}  ██╗███╗   ██╗███████╗████████╗ █████╗ ███╗   ██╗ ██████╗███████╗███████╗{RESET}",
            f"{PURPLE}  ██║████╗  ██║██╔════╝╚══██╔══╝██╔══██╗████╗  ██║██╔════╝██╔════╝██╔════╝{RESET}",
            f"{PURPLE}  ██║██╔██╗ ██║███████╗   ██║   ███████║██╔██╗ ██║██║     █████╗  ███████╗{RESET}",
            f"{PURPLE}  ██║██║╚██╗██║╚════██║   ██║   ██╔══██║██║╚██╗██║██║     ██╔══╝  ╚════██║{RESET}",
            f"{PURPLE}  ██║██║ ╚████║███████║   ██║   ██║  ██║██║ ╚████║╚██████╗███████╗███████║{RESET}",
            f"{PURPLE}  ╚═╝╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚══════╝{RESET}",
        ]
    else:
        return [f"{PURPLE}{'I N S T A N C E S':^{width}}{RESET}"]


def _adaptive_input(prompt=""):
    """input() replacement that redraws on terminal resize."""
    global _resize_flag

    if not sys.stdin.isatty():
        return input(prompt)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write(prompt)
        sys.stdout.flush()

        buf = ""
        while True:
            if _resize_flag:
                _resize_flag = False
                w = shutil.get_terminal_size().columns
                sys.stdout.write("\r" + " " * (w - 1) + "\r")
                render_status()
                sys.stdout.write(prompt + buf)
                sys.stdout.flush()

            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.3)
            except InterruptedError:
                continue
            if not r:
                continue

            ch = sys.stdin.read(1)
            if ch == "\n":
                sys.stdout.write("\n")
                sys.stdout.flush()
                return buf
            elif ch in ("\x7f", "\b"):
                if buf:
                    buf = buf[:-1]
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            else:
                buf += ch
                sys.stdout.write(ch)
                sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


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


def _build_content(width):
    total = len(_farm.instances) if _farm else 0
    running = sum(1 for inst in (_farm.instances or []) if process.is_running(inst.id)) if _farm else 0

    grid_lines, url_lines, has_any = _grid_display()

    div = "-" * width
    lines = [""]
    lines.extend(_render_logo(width))
    lines.append("")
    info = f"\U0001f4c1 {DATA_DIR}"
    if total > 0 or running > 0:
        parts = []
        if total > 0:
            parts.append(f"{total} printer{'s' if total > 1 else ''}")
        parts.append(f"{running} active")
        info += f"    \u26a1 {' \u00b7 '.join(parts)}"
    lines.append(info)
    if has_any:
        lines.append(div)
        lines.append("")
        lines.extend(grid_lines)
        if url_lines:
            lines.append("")
            lines.append(f"\U0001f517  Running")
            lines.extend(url_lines)
    else:
        lines.append(div)
        lines.append("")
        lines.append(f"\U0001f4a1  First time?  Type {LAVENDER}p{RESET} then add")
    lines.append("")
    lines.append(div)
    lines.append("")
    L = lambda s: f"{LAVENDER}{s}{RESET}"
    if width >= 60:
        lines.append(f"{L('p')}  add printer             {L('d')}  dashboard")
        lines.append(f"{L('s')}  set directory           {L('h')}  help")
        lines.append("")
        lines.append(f"{L('sa')}  start all                {L('ka')}  kill all")
        lines.append(f"{L('s-a1')}  start a1               {L('k-a1')}  kill a1")
        lines.append(f"{L('n-a1')}  rename a1              {L('l-a1')}  relabel a1")
        lines.append(f"{L('b-a1')}  assign board           {L('x-a1')}  remove a1")
        lines.append("")
        lines.append(f"{L('x-a1:b2')}  remove instances in outlined area")
    else:
        lines.append(f"{L('p')}          add printer")
        lines.append(f"{L('d')}          dashboard")
        lines.append(f"{L('s')}          set directory")
        lines.append(f"{L('h')}          help")
        lines.append("")
        lines.append(f"{L('sa')}         start all")
        lines.append(f"{L('ka')}         kill all")
        lines.append("")
        lines.append(f"{L('s-a1')}       start a1")
        lines.append(f"{L('k-a1')}       kill a1")
        lines.append(f"{L('n-a1')}       rename a1")
        lines.append(f"{L('l-a1')}       relabel a1")
        lines.append(f"{L('b-a1')}       assign board")
        lines.append(f"{L('x-a1')}       remove a1")
        lines.append("")
        lines.append(f"{L('x-a1:b2')}    remove instances in outlined area")
    lines.append("")
    lines.append(div)
    lines.append(f"Type a label ({L('a1')}) or name")
    lines.append(div)
    lines.append(f"{L('q')}  quit app")
    return lines


def render_status():
    os.system('clear')
    width = shutil.get_terminal_size().columns
    for line in _build_content(width):
        print(line)


# ── Help menu ─────────────────────────────────────────────────────
def _help_menu():
    os.system('clear')
    w = shutil.get_terminal_size().columns
    div = "-" * w
    lines = [f"{LAVENDER}HELP{RESET}"]
    lines.append("")
    lines.append(f"{LAVENDER}General{RESET}")
    lines.append(f"  {LAVENDER}p{RESET}     Add a new printer (opens wizard)")
    lines.append(f"  {LAVENDER}d{RESET}     Dashboard (overview + USB scan)")
    lines.append(f"  {LAVENDER}s{RESET}     Set data directory")
    lines.append(f"  {LAVENDER}h{RESET}     Show this help")
    lines.append(f"  {LAVENDER}q{RESET}     Quit")
    lines.append("")
    lines.append(f"{LAVENDER}Start / Stop{RESET}")
    lines.append(f"  {LAVENDER}sa{RESET}     Start all printers")
    lines.append(f"  {LAVENDER}ka{RESET}     Stop all printers")
    lines.append(f"  {LAVENDER}s-a1{RESET}   Start printer a1")
    lines.append(f"  {LAVENDER}s-a1:a3{RESET}  Start a1 through a3 (range)")
    lines.append(f"  {LAVENDER}s-a1:b2{RESET}  Start rectangle a1 to b2")
    lines.append(f"  {LAVENDER}s-cherry{RESET}  Start by name")
    lines.append(f"  {LAVENDER}k-a1{RESET}   Stop printer a1")
    lines.append(f"  {LAVENDER}k-a1:a3{RESET}  Stop a1 through a3")
    lines.append("")
    lines.append(f"{LAVENDER}Edit (single instance only){RESET}")
    lines.append(f"  {LAVENDER}n-a1{RESET}   Rename printer a1")
    lines.append(f"  {LAVENDER}l-a1{RESET}   Relabel printer a1")
    lines.append(f"  {LAVENDER}b-a1{RESET}   Assign serial board to a1")
    lines.append(f"  {LAVENDER}x-a1{RESET}   Remove printer a1")
    lines.append(f"  {LAVENDER}x-a1:b2{RESET}  Remove instances in outlined area")
    lines.append("")
    lines.append(f"{LAVENDER}Info{RESET}")
    lines.append(f"  {LAVENDER}a1{RESET}     Show printer details (serial, ports, URL)")
    lines.append(f"  {LAVENDER}cherry{RESET} Show printer by name")
    lines.append("")
    lines.append(div)
    lines.append("Only existing instances are affected — like cropping, s-a1:b99 won't error")
    for line in lines:
        print(line)
    input("\nPress Enter...")


# ── Printer info (inline, no sub-page) ───────────────────────────
def cmd_info(inst):
    state = "running" if process.is_running(inst.id) else "stopped"
    icon = {"running": "\U0001f7e2", "stopped": "\u26aa"}[state]
    serial_short = os.path.basename(inst.serial)[:30] if inst.serial else "(none)"
    p = _farm.ports(inst.id)
    print(f"  {icon}  {LAVENDER}{inst.label}{RESET}  \u2014  {inst.name}")
    print(f"  Serial: {serial_short}")
    if state == "running":
        print(f"  URL:    http://localhost:{p['mainsail']}")
    else:
        print(f"  Ports:  Moonraker {p['moonraker']}  Mainsail {p['mainsail']}")


# ── Printer wizard (add / status) ────────────────────────────────
def _printers_menu():
    while True:
        os.system('clear')
        w = shutil.get_terminal_size().columns
        div = "-" * w
        print(f"{LAVENDER}PRINTER WIZARD{RESET}")
        print("")

        grid_lines, url_lines, has_any = _grid_display()
        if has_any:
            for line in grid_lines:
                print(line)
            if url_lines:
                print("")
                print(f"\U0001f517  Running")
                for line in url_lines:
                    print(line)
        else:
            print("No instances configured.")
        print("")
        print(div)
        print("")
        print(f"{LAVENDER}add{RESET}     add a new printer")
        print(f"{LAVENDER}/{RESET}       back")
        print(div)

        raw = input("> ").strip().lower()
        if not raw:
            continue
        if raw in ("back", "/"):
            break
        elif raw == "add":
            cmd_add()
        input("Press Enter...")


# ── Main loop ─────────────────────────────────────────────────────
def main():
    global DATA_DIR, _farm

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=str, help="data directory path")
    args = parser.parse_args()

    if args.data_dir:
        DATA_DIR = str(Path(args.data_dir).expanduser().resolve())
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps({"data_dir": DATA_DIR}))
    else:
        DATA_DIR = load_data_dir()

    setup_data_dir()
    _farm = Farm(DATA_DIR)

    signal.signal(signal.SIGWINCH, _on_resize)
    signal.siginterrupt(signal.SIGWINCH, True)

    while True:
        render_status()

        raw = _adaptive_input("\n> ").strip().lower()
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
            cmd_dashboard()
        elif raw in ("s", "setdir"):
            new = input("Enter new data directory path:\n> ").strip()
            if new:
                new = str(Path(new).expanduser().resolve())
                try:
                    Path(new).mkdir(parents=True, exist_ok=True)
                    (Path(new) / ".write_test").write_text("test")
                    Path(new, ".write_test").unlink()
                    DATA_DIR = new
                    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                    CONFIG_FILE.write_text(json.dumps({"data_dir": DATA_DIR}))
                    _farm = Farm(DATA_DIR)
                    print(f"\u2705  Data directory set to: {DATA_DIR}")
                except (OSError, PermissionError) as e:
                    print(f"\u274c  {e}")
                input("Press Enter...")
        elif raw in ("h", "help"):
            _help_menu()
        elif raw == "sa":
            cmd_start_all()
            input("Press Enter...")
        elif raw == "ka":
            cmd_stop_all()
            input("Press Enter...")
        elif raw.startswith("s-"):
            targets = _parse_selectors(raw[2:])
            _cmd_launch_targets(targets)
            input("Press Enter...")
        elif raw.startswith("k-"):
            targets = _parse_selectors(raw[2:])
            _cmd_stop_targets(targets)
            input("Press Enter...")
        elif raw.startswith("n-"):
            spec = raw[2:]
            inst = _resolve_instance(spec)
            if not inst:
                print(f"Instance '{spec}' not found")
            else:
                new_name = input(f"New name for {inst.label} [{inst.name}]: ").strip()
                if new_name:
                    if _farm.name_exists(new_name) and _farm.find_by_name(new_name).id != inst.id:
                        print(f"\u274c  Name '{new_name}' already exists")
                    else:
                        cmd_rename(inst.id, new_name)
            input("Press Enter...")
        elif raw.startswith("l-"):
            spec = raw[2:]
            inst = _resolve_instance(spec)
            if not inst:
                print(f"Instance '{spec}' not found")
            else:
                new_label = input(f"New label for {inst.name} [{inst.label}]: ").strip().lower()
                if new_label:
                    if _farm.label_exists(new_label) and _farm.find_by_label(new_label).id != inst.id:
                        print(f"\u274c  Label '{new_label}' already exists")
                    else:
                        cmd_label(inst.id, new_label)
            input("Press Enter...")
        elif raw.startswith("b-"):
            spec = raw[2:]
            inst = _resolve_instance(spec)
            if not inst:
                print(f"Instance '{spec}' not found")
            else:
                cmd_assign(inst.id)
            input("Press Enter...")
        elif raw.startswith("x-"):
            targets = _parse_selectors(raw[2:])
            if not targets:
                print("No matching instances found")
            else:
                names = ", ".join(f"{t.label} ({t.name})" for t in targets)
                print(f"Remove: {names}")
                if input("Type 'yes' to confirm: ").strip().lower() == "yes":
                    for t in targets:
                        if process.is_running(t.id):
                            process.stop(t.id)
                        _farm.remove(t.id)
                        print(f"\u2705  Removed {t.label}")
            input("Press Enter...")
        else:
            inst = _resolve_instance(raw)
            if inst:
                cmd_info(inst)
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
