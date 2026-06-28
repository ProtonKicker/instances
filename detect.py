# use pyserial for usb detectino
import serial.tools.list_ports

def scan():
    ports = serial.tools.list_ports.comports()

    devices = []

    # list out devices and say devices as array
    for port, desc, hwid in sorted(ports):

        # debug line
        # print(f"DEBUG: System raw comports found -> {[p.device for p in ports]}")
        
        # turn all upper case
        desc_upper = desc.upper()
        port_upper = port.upper()


        if any(x in desc_upper for x in ["USB", "CH340", "FTDI", "CP210", "ACM", "STM", "STMICRO", "KLIPPER"]) or \
           any(x in port_upper for x in ["ACM", "USB"]):
            devices.append(port)
    
    return devices
        
