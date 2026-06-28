# use pyserial for usb detectino
import serial.tools.list_ports

def scan():
    ports = serial.tools.list_ports.comports()

    devices = []

    # list out devices and say devices as array
    for port, desc, hwid in sorted(ports):
        desc_upper = desc.upper()
        if "USB" in desc_upper or "CH340" in desc_upper or "FTDI" in desc_upper or "CP210" in desc_upper or "ACM" in desc_upper:
            devices.append(port)
    
    return devices
        
