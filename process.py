import subprocess
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_running = {}


def _python():
    appdir = os.environ.get("APPDIR")
    if appdir:
        bundled = os.path.join(appdir, "usr", "bin", "python3")
        if os.path.isfile(bundled):
            return bundled
    venv = os.path.join(BASE_DIR, ".venv", "bin", "python")
    return venv if os.path.isfile(venv) else "python3"


def start(farm, inst):
    if inst.id in _running:
        return False

    p = farm.ports(inst.id)
    klipper_py = os.path.join(BASE_DIR, "klipper_core", "klippy", "klippy.py")
    klipper_cwd = os.path.join(BASE_DIR, "klipper_core", "klippy")
    moonraker_py = os.path.join(BASE_DIR, "moonraker_core", "moonraker", "moonraker.py")
    moonraker_cwd = os.path.join(BASE_DIR, "moonraker_core")
    py = _python()

    printer_cfg = str(farm.printer_cfg(inst.id))
    moonraker_conf = str(farm.moonraker_conf(inst.id))
    moonraker_data = str(farm.moonraker_data(inst.id))
    mainsail_dir = str(farm.mainsail_dir(inst.id))

    config_link = os.path.join(moonraker_data, "config", "printer.cfg")
    os.makedirs(os.path.dirname(config_link), exist_ok=True)
    if not os.path.islink(config_link) or os.path.realpath(config_link) != os.path.realpath(printer_cfg):
        if os.path.lexists(config_link):
            os.remove(config_link)
        os.symlink(printer_cfg, config_link)

    kproc = subprocess.Popen(
        [py, klipper_py, "-a", p["uds"], printer_cfg],
        cwd=klipper_cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    mproc = subprocess.Popen(
        [py, moonraker_py, "-c", moonraker_conf, "-d", moonraker_data],
        cwd=moonraker_cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    wproc = subprocess.Popen(
        [py, "-m", "http.server", str(p["mainsail"]), "--directory", mainsail_dir],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    _running[inst.id] = {"klipper": kproc, "moonraker": mproc, "mainsail": wproc}
    return True


def stop(instance_id):
    procs = _running.pop(instance_id, None)
    if not procs:
        return False
    for key in ("mainsail", "moonraker", "klipper"):
        p = procs.get(key)
        if p and p.poll() is None:
            p.terminate()
    return True


def stop_all():
    for pid in list(_running):
        stop(pid)


def is_running(instance_id):
    procs = _running.get(instance_id)
    if not procs:
        return False
    k = procs.get("klipper")
    return k is not None and k.poll() is None


def running_count():
    return len(_running)


def status(farm):
    rows = []
    for inst in farm.instances:
        if inst.id in _running:
            k = _running[inst.id]["klipper"]
            state = "running" if k and k.poll() is None else "error"
        else:
            state = "stopped"
        rows.append((inst, state))
    return rows


def check_serial_access(device_path):
    try:
        fd = os.open(device_path, os.O_RDWR)
        os.close(fd)
        return True
    except PermissionError:
        return False
    except OSError:
        return False
