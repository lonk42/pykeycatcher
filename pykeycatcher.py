#!/usr/bin/env python
import hid
import sys
import argparse
from time import sleep

def manual_device_menu(hid_devices):
	print("Listing all HID devices...")
	for i, device in enumerate(hid_devices):
		print(f"{i}: Vendor ID: {device['vendor_id']}, Product ID: {device['product_id']}, Product: {device['product_string']}")
	device_index = int(input("Select a device index to connect to: "))
	return hid_devices[device_index]

def main():

	# Setup CLI arugments
	parser = argparse.ArgumentParser(description="HID Input Listener")
	parser.add_argument('--manual', action='store_true', help="Provide manual device selection menu")
	parser.add_argument('--config', type=str, help="Path to a configuration file")
	# TODO add  --device
	args = parser.parse_args()

	# Get all HID devices on the system
	hid_devices = hid.enumerate()
	hid_device = hid.device()
	if not hid_devices:
		print("ERROR: No HID devices found! Exiting...")
		sys.exit(1)

	if args.config:
		pass
	elif args.manual:
		chosen_device = manual_device_menu(hid_devices)
	else:
		print("ERROR: No HID device was selected, use either --manual or --config to set one")
		sys.exit(1)

	# Select the device to connect
	print(f"Connecting to {chosen_device['product_string']}")
	hid_device.open(chosen_device['vendor_id'], chosen_device['product_id'])
	hid_device.set_nonblocking(1)
	
	# Open the selected HID device
	print("Listening for inputs... (Press Ctrl+C to exit)")
		
	try:
		while True:
			sleep(0.05)
			data = hid_device.read(64)
			if data:
				print("Received data:", data)
	except Exception as e:
		print(e)

if __name__ == "__main__":
	main()

