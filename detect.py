import glob
import os

def scan():

    search_path = "/dev/serial/by-id/*"
    devices = glob.glob(search_path)

    return devices
        
def check_config(data_dir):
    config_file = os.path.join(data_dir, "printer.cfg")
    return os.path.isfile(config_file)
