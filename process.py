import subprocess
import os
import sys
import http.server
import socketserver
import threading

_klipper_proc = None
_moonraker_proc = None
_web_thread = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_python_exe():
    venv_python = os.path.join(BASE_DIR, ".venv", "bin", "python")
    if os.path.isfile(venv_python):
        return venv_python
    return sys.executable


def start(data_dir):
    global _klipper_proc, _moonraker_proc, _web_thread

    if get_state():
        print("Instance 1 is already running")
        return False

    printer_cfg = os.path.join(data_dir, "printer.cfg")
    if not os.path.isfile(printer_cfg):
        print("No printer.cfg found at:", printer_cfg)
        return False

    moonraker_conf = _ensure_moonraker_config(data_dir)

    config_link = os.path.join(data_dir, "moonraker_data", "config", "printer.cfg")
    os.makedirs(os.path.dirname(config_link), exist_ok=True)
    if not os.path.islink(config_link) or os.path.realpath(config_link) != os.path.realpath(printer_cfg):
        if os.path.lexists(config_link):
            os.remove(config_link)
        os.symlink(printer_cfg, config_link)

    klipper_py = os.path.join(BASE_DIR, "klipper_core", "klippy", "klippy.py")
    klipper_cwd = os.path.join(BASE_DIR, "klipper_core", "klippy")
    _klipper_proc = subprocess.Popen(
        [_get_python_exe(), klipper_py, "-a", "/tmp/instance1_uds", config_link],
        cwd=klipper_cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    moonraker_py = os.path.join(BASE_DIR, "moonraker_core", "moonraker", "moonraker.py")
    moonraker_cwd = os.path.join(BASE_DIR, "moonraker_core")
    moonraker_data = os.path.join(data_dir, "moonraker_data")
    _moonraker_proc = subprocess.Popen(
        [_get_python_exe(), moonraker_py, "-c", moonraker_conf, "-d", moonraker_data],
        cwd=moonraker_cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    mainsail_dir = os.path.join(BASE_DIR, "mainsail_web")
    _web_thread = threading.Thread(
        target=_run_web_server, args=(mainsail_dir, 8080), daemon=True
    )
    _web_thread.start()

    print("Mainsail: http://localhost:8080")
    return True


def kill():
    global _klipper_proc, _moonraker_proc

    if _moonraker_proc and _moonraker_proc.poll() is None:
        _moonraker_proc.terminate()

    if _klipper_proc and _klipper_proc.poll() is None:
        _klipper_proc.terminate()

    _klipper_proc = None
    _moonraker_proc = None


def get_state():
    if _klipper_proc is None:
        return False
    return _klipper_proc.poll() is None


def check_serial_access(device_path):
    try:
        fd = os.open(device_path, os.O_RDWR)
        os.close(fd)
        return True
    except PermissionError:
        return False
    except OSError:
        return False


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def _run_web_server(directory, port):
    os.chdir(directory)
    with socketserver.TCPServer(("", port), _QuietHandler) as httpd:
        httpd.serve_forever()


def _ensure_moonraker_config(data_dir):
    conf_path = os.path.join(data_dir, "moonraker.conf")
    if os.path.isfile(conf_path):
        return conf_path

    with open(conf_path, "w") as f:
        f.write("[server]\n")
        f.write("host: 0.0.0.0\n")
        f.write("port: 7125\n")
        f.write("klippy_uds_address: /tmp/instance1_uds\n\n")
        f.write("[authorization]\n")
        f.write("cors_domains:\n")
        f.write("    http://localhost:8080\n")
        f.write("trusted_clients:\n")
        f.write("    127.0.0.1\n")
        f.write("    192.168.0.0/16\n\n")

    return conf_path
