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
    if not os.path.isfile(config_file):
        return False

    with open(config_file, "r") as f:
        lines = f.readlines()

    found_mcu = False
    serial_replaced = False
    with open(config_file, "w") as f:
        for line in lines:
            if line.strip().startswith("[mcu]"):
                found_mcu = True
            elif found_mcu and line.strip().startswith("serial:"):
                line = f"serial: {device_path}\n"
                found_mcu = False
                serial_replaced = True
            f.write(line)

    return serial_replaced
