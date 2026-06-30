import glob
import os

def scan():
    search_path = "/dev/serial/by-id/*"
    devices = glob.glob(search_path)
    return devices

def check_config(data_dir):
    config_file = os.path.join(data_dir, "printer.cfg")
    return os.path.isfile(config_file)

def update_serial(data_dir, device_path):
    config_file = os.path.join(data_dir, "printer.cfg")
    return _update_serial_in_file(config_file, device_path)


def update_serial_in_file(cfg_path, device_path):
    return _update_serial_in_file(cfg_path, device_path)


def _update_serial_in_file(cfg_path, device_path):
    if not os.path.isfile(cfg_path):
        return False

    with open(cfg_path, "r") as f:
        lines = f.readlines()

    found_mcu = False
    serial_replaced = False
    with open(cfg_path, "w") as f:
        for line in lines:
            if line.strip().startswith("[mcu]"):
                found_mcu = True
            elif found_mcu and line.strip().startswith("serial:"):
                line = f"serial: {device_path}\n"
                found_mcu = False
                serial_replaced = True
            f.write(line)

    return serial_replaced


def update_serial_in_file(cfg_path, device_path):
    if not os.path.isfile(cfg_path):
        return False

    with open(cfg_path, "r") as f:
        lines = f.readlines()

    found_mcu = False
    serial_replaced = False
    with open(cfg_path, "w") as f:
        for line in lines:
            if line.strip().startswith("[mcu]"):
                found_mcu = True
            elif found_mcu and line.strip().startswith("serial:"):
                line = f"serial: {device_path}\n"
                found_mcu = False
                serial_replaced = True
            f.write(line)

    return serial_replaced
