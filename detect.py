import glob

def scan():

    search_path = "/dev/serial/by-id/*"
    devices = glob.glob(search_path)

    return devices
        
