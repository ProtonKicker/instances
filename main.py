# main function

# imports
import detect

def main():
    start()


def start():
    
    print("Instance 1 ALIVE")

    # call detect
    detect.scan()


# tells Python to execute the main() function when this file is run
if __name__ == "__main__":
    main()