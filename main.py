# main function

# imports
import detect

def main():
    start()


def start():
    

    print("🪽  Instance 1 ALIVE")


    # call detect
    devices = detect.scan()
    
    # if devices is empty, say no devices
    # if devices is not empty, list devices
    if len(devices) == 0:
        print("⚠️  No devices found")
    else:
        print("✅  Devices found (by ID):")
        for index, path in enumerate(devices):
            print(f" {index + 1} - {path}")


# tells Python to execute the main() function when this file is run
if __name__ == "__main__":
    main()