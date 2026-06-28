import detect
import dir


def startup():
    
    # welcome line
    print("")
    print("🪽  Instance 1 ALIVE")
    print("")


    # show dir
    data_dir = dir.startup()
    print("🏛️  Data directory: ", data_dir)
    print("")


    # list devices
    devices = detect.scan()
    
    # if devices is empty, say no devices
    # if devices is not empty, list devices
    if len(devices) == 0:
        print("⚠️ No devices found")
    else:
        print("✅ Devices found (by ID):")
        for path in devices:
            print(f" - {path}")
    print("")

    # check for printer.cfg
    if detect.check_config(data_dir):
        print("✅ Config found: printer.cfg")
    else:
        print("⚠️  No printer.cfg found")
        print("   Place your printer.cfg in:", data_dir)


    # command hints
    print("")
    print(" Type 'launch' or 'start' to start the server or 'exit' to quit")
    