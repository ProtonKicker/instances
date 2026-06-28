import detect
import dir


def startup():
    
    # welcome line
    print("")
    print("🪽  Instance 1 ALIVE")


    # show dir
    data_dir = dir.startup()
    print("🏛️  Data directory: ", data_dir)


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

    