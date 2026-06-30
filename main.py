import startup
import process

def main():
    startup.startup()

    while True:
        # Capture the user input ONCE at the top of the loop
        user_choice = input("👉 ").strip().lower()

        if user_choice == "exit":
            print("Goodbye!")
            break

        # Check server status
        if not process.get_state():
            if user_choice in ["launch", "start"]:
                process.start_klipper()

                # confirm start
                if process.get_state():
                    print("Klipper active")
                else:
                    print("Klipper failed to start")

        else:
            if user_choice in ["kill", "stop"]:
                process.kill_klipper()

                # confirm shutdown
                if not process.get_state():
                    print("Klipper down")
                else:
                    print("Klipper failed to stop")



# tells Python to execute the main() function when this file is run
if __name__ == "__main__":
    main()
