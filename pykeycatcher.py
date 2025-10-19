#!/usr/bin/env python
import os
import hid
import sys
import yaml
import argparse
import traceback
import subprocess
from time import sleep
from socket import gethostname
from evdev import UInput, ecodes
from paho.mqtt import publish as pahomqtt_publish

def manual_device_menu(hid_devices):
	print("Listing all HID devices...")
	for i, device in enumerate(hid_devices):
		print(f"{i}: Vendor ID: {device['vendor_id']}, Product ID: {device['product_id']}, Product: {device['product_string']}")
	device_index = int(input("Enter device index: "))
	return hid_devices[device_index]

def parse_config(file_path):
	try:
		with open(file_path, 'r') as file:
			config = yaml.safe_load(file)
		return config
	except FileNotFoundError:
		print(f"Error: The file '{file_path}' was not found.")
	except yaml.YAMLError as e:
		print(f"Error parsing YAML file: {e}")
	except Exception as e:
		print(f"An unexpected error occurred: {e}")

	# Must have been an error
	sys.exit(1)

def main():

	# Initalize
	config = {}

	# Setup CLI arugments
	parser = argparse.ArgumentParser(description="HID Input Listener")
	parser.add_argument('--manual', action='store_true', help="Provide manual device selection menu")
	parser.add_argument('--debug', action='store_true', help="Enable debug logging")
	parser.add_argument('--config', type=str, help="Path to a configuration file")
	args = parser.parse_args()

	# Get all HID devices on the system
	hid_devices = hid.enumerate()
	hid_device = hid.device()
	if not hid_devices:
		print("ERROR: No HID devices found! Exiting...")
		sys.exit(1)

	if args.config:
		config = parse_config(args.config)

	elif args.manual:
		config['device'] = manual_device_menu(hid_devices)
	
	else:
		print("ERROR: No HID device was defined, use either --manual or --config to set one")
		sys.exit(1)

	while True:

		try:
			# Create a UInput device
			print("Creating virtual UInput device...")
			uinput_device = UInput()

			# Connect to the device
			print(f"Connecting to device {config['device']['vendor_id']},{config['device']['product_id']}...")
			hid_device.open(config['device']['vendor_id'], config['device']['product_id'])
			hid_device.set_nonblocking(1)
			
			# Open the selected HID device
			print("Listening for inputs...")

			while True:
				sleep(0.05)
				data = hid_device.read(64)

				if data:
					if args.debug:
						print("Received data: ", data)

					# Run against action
					if data[3] in config['actions']:

						# Value operation
						if 'values' in config['actions'][data[3]].keys():
							for value in config['actions'][data[3]]['values']:
								adjust_value(config, value)
	
						# MQTT operation
						if 'mqtt' in config['actions'][data[3]].keys():
							for mqtt_operation in config['actions'][data[3]]['mqtt']:
								mqtt_publish(config, mqtt_operation)

						# Mirror operation
						if 'mirror' in config['actions'][data[3]].keys() and config['actions'][data[3]]['mirror']:
							if args.debug:
								print(f'Sending mirror for key {data}')
								print(f'Sending mirror for key {[0] * 8}')
								uinput_device.write(ecodes.EV_KEY, data[3], 1)
								uinput_device.write(ecodes.EV_KEY, data[3], 0)
								uinput_device.syn()

						# Process operation
						if 'process' in config['actions'][data[3]].keys():
							for process_operation in config['actions'][data[3]]['process']:
								run_process(config, process_operation)

		except Exception:
			print("ERROR: reconnecting to device...")
			print(traceback.format_exc())
			uinput_device.close()
			hid_device.close()
			sleep(5)

def adjust_value(config, value):

	# Adjust values do a basic integer operation
	if 'adjust' in value.keys():

		# Change the value
		config['values'][value['name']]['value'] += value['adjust']

		# Apply clamping if its defined
		if 'clamp' in config['values'][value['name']].keys():
			config['values'][value['name']]['value'] = clamp(
				config['values'][value['name']]['value'],
				config['values'][value['name']]['clamp']['min'],
				config['values'][value['name']]['clamp']['max']
			)

def mqtt_publish(config, operation):
	payload = ''
	
	if 'value' in operation.keys():
		payload = config['values'][operation['value']]['value']

	if 'message' in operation.keys():
		payload = operation['message']
	
	print(f'Sending MQTT, topic: "{operation['topic']}", payload: "{payload}"')
	pahomqtt_publish.single(operation['topic'], payload, hostname=config['mqtt_host'])

def run_process(config, process):

	print(f'Running command: "{process['command']}"')
	subprocess.Popen(
		process['command'],
		stdout=subprocess.DEVNULL,
		stderr=subprocess.DEVNULL,
		stdin=subprocess.DEVNULL,
		preexec_fn=os.setsid,
		shell=True
	)


def clamp(n, min, max): 
	if n < min: 
		return min
	elif n > max: 
		return max
	else: 
		return n 

if __name__ == "__main__":
	main()

