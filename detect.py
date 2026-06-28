# use pyserial for usb detectino
import serial.tools.list_ports
import os
import glob

def scan():
    # ports = serial.tools.list_ports.comports()

    # devices = []

    # # list out devices and say devices as array
    # for port, desc, hwid in sorted(ports):

        
    #     # turn all upper case
    #     desc_upper = desc.upper()
    #     port_upper = port.upper()


    #     if any(x in desc_upper for x in ["USB", "CH340", "FTDI", "CP210", "ACM", "STM", "STMICRO", "KLIPPER"]) or \
    #        any(x in port_upper for x in ["ACM", "USB"]):

    #        info = serial.tools.list_ports.comports()
    #        dev_id = getattr(port, 'serial_number', None) or hwid

    #        devices.append({
    #             "path": port,
    #             "desc": desc,
    #             "id": dev_id
    #         })

    search_path = "/dev/serial/by-id/*"
    devices = glob.glob(search_path)
    
    return devices
        
