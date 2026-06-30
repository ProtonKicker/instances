import subprocess
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

_running = {}


def _get_python_exe():
    venv_python = BASE_DIR / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def start(farm, inst):
    if is_running(inst.id):
        return False

    inst_dir = farm._instance_dir(inst.id)
    printer_cfg = inst_dir / "printer.cfg"

    if not printer_cfg.exists():
        print(f"No printer.cfg for Instance {inst.id}")
        return False

    moonraker_conf = inst_dir / "moonraker.conf"

    mr_config = inst_dir / "moonraker_data" / "config"
    mr_config.mkdir(parents=True, exist_ok=True)
    config_link = mr_config / "printer.cfg"
    if config_link.exists() or config_link.is_symlink():
        config_link.unlink()
    config_link.symlink_to(printer_cfg)

    uds_dir = Path("/tmp/instances")
    uds_dir.mkdir(parents=True, exist_ok=True)
    uds_path = f"/tmp/instances/instance_{inst.id}.sock"

    klipper_py = BASE_DIR / "klipper_core" / "klippy" / "klippy.py"
    klipper_cwd = BASE_DIR / "klipper_core" / "klippy"

    klipper = subprocess.Popen(
        [_get_python_exe(), str(klipper_py), "-a", uds_path, str(printer_cfg)],
        cwd=str(klipper_cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    moonraker_py = BASE_DIR / "moonraker_core" / "moonraker" / "moonraker.py"
    moonraker_cwd = BASE_DIR / "moonraker_core"
    moonraker_data = inst_dir / "moonraker_data"

    moonraker = subprocess.Popen(
        [_get_python_exe(), str(moonraker_py), "-c", str(moonraker_conf), "-d", str(moonraker_data)],
        cwd=str(moonraker_cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    mainsail_dir = inst_dir / "mainsail"
    p = farm.ports(inst.id)

    mainsail = subprocess.Popen(
        [_get_python_exe(), "-m", "http.server", str(p["mainsail"]), "--directory", str(mainsail_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    _running[inst.id] = {
        "klipper": klipper,
        "moonraker": moonraker,
        "mainsail": mainsail,
    }

    return True


def stop(instance_id):
    procs = _running.pop(instance_id, None)
    if not procs:
        return False

    for name in ("moonraker", "klipper", "mainsail"):
        proc = procs.get(name)
        if proc and proc.poll() is None:
            proc.terminate()

    return True


def stop_all():
    for inst_id in list(_running.keys()):
        stop(inst_id)


def is_running(instance_id):
    procs = _running.get(instance_id)
    if not procs:
        return False
    return any(proc.poll() is None for proc in procs.values())


def running_count():
    return sum(1 for i in list(_running.keys()) if is_running(i))


def status(farm):
    result = []
    for inst in farm.instances:
        if is_running(inst.id):
            result.append((inst, "running"))
        else:
            result.append((inst, "stopped"))
    return result


def check_serial_access(device_path):
    try:
        fd = os.open(device_path, os.O_RDWR)
        os.close(fd)
        return True
    except PermissionError:
        return False
    except OSError:
        return False
