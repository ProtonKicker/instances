import startup
import process


def main():
    startup.startup()

    # while user didnt input "exit" , keep input active
    while input() != "exit":

        # check server status
        if not process.get_state():
            print("Server is inactive")

            #start klipper
            if input() in ["launch", "start"]:
                process.start_klipper()
                print("Klipper active")
        
        if process.get_state():

            # if user input "kill" or "stop", kill klipper
            if input() in ["kill", "stop"]:
                process.kill_klipper()
                print("Klipper down")



# tells Python to execute the main() function when this file is run
if __name__ == "__main__":
    main()