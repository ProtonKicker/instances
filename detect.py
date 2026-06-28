# use pyserial for usb detectino
import serial.tools.list_ports

def scan():
    ports = serial.tools.list_ports.comports()

    # list out devices and say devices as array
    for port, desc, hwid in sorted(ports):
        print("{}: {} [{}]".format(port, desc, hwid))
        
