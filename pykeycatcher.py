#!/usr/bin/env python3
"""Run configured actions when keys are pressed on a USB HID keypad."""
import sys
import logging
import argparse
import subprocess
from time import sleep
from contextlib import suppress

import hid
import yaml
from evdev import UInput, UInputError, ecodes
from paho.mqtt import publish

log = logging.getLogger('pykeycatcher')

KEY_BYTE = 3          # Index of the key code in each HID report
REPORT_SIZE = 64
POLL_INTERVAL = 0.05  # Seconds between reads
RECONNECT_DELAY = 5   # Seconds to wait before reopening after a device error


class StartupError(Exception):
	pass


def manual_device_menu():
	hid_devices = hid.enumerate()
	if not hid_devices:
		raise StartupError("No HID devices found")

	print("Listing all HID devices...")
	for i, device in enumerate(hid_devices):
		print(f"{i}: Vendor ID: {device['vendor_id']}, Product ID: {device['product_id']}, Product: {device['product_string']}")

	try:
		return hid_devices[int(input("Enter device index: "))]
	except (ValueError, IndexError):
		raise StartupError("Invalid device index")


def parse_config(file_path):
	try:
		with open(file_path) as file:
			config = yaml.safe_load(file) or {}
	except OSError as e:
		raise StartupError(f"Cannot read config: {e}")
	except yaml.YAMLError as e:
		raise StartupError(f"Cannot parse config: {e}")

	if not isinstance(config, dict):
		raise StartupError("Config must be a YAML mapping")

	validate_config(config)
	return config


def validate_config(config):
	# Check every reference up front, so a mistake stops startup instead of failing on a keypress
	device = config.get('device') or {}
	for key in ('vendor_id', 'product_id'):
		if not isinstance(device.get(key), int):
			raise StartupError(f"device.{key} must be an integer")

	values = config['values'] = config.get('values') or {}
	actions = config['actions'] = config.get('actions') or {}

	for name, value in values.items():
		if not isinstance(value, dict) or not isinstance(value.get('value'), int):
			raise StartupError(f"values.{name}.value must be an integer")

	for code, action in actions.items():
		if not isinstance(code, int) or not isinstance(action, dict):
			raise StartupError(f"actions.{code} must be an integer key code with a mapping of actions")

		for operation in action.get('values', []):
			if operation.get('name') not in values:
				raise StartupError(f"actions.{code}: no value named {operation.get('name')!r}")

		for operation in action.get('mqtt', []):
			if 'topic' not in operation:
				raise StartupError(f"actions.{code}: every mqtt entry needs a topic")
			if 'value' in operation and operation['value'] not in values:
				raise StartupError(f"actions.{code}: no value named {operation['value']!r}")
		if action.get('mqtt') and not config.get('mqtt_host'):
			raise StartupError("mqtt_host must be set to use mqtt actions")

		for operation in action.get('process', []):
			if 'command' not in operation:
				raise StartupError(f"actions.{code}: every process entry needs a command")


def listen(config):
	vendor_id = config['device']['vendor_id']
	product_id = config['device']['product_id']
	actions = config['actions']

	# /dev/uinput is only opened when an action needs it
	needs_uinput = any(action.get('mirror') for action in actions.values())

	hid_device = hid.device()
	uinput_device = None

	while True:
		try:
			if needs_uinput:
				log.info("Creating virtual UInput device...")
				uinput_device = UInput(name='pykeycatcher')

			log.info("Connecting to device %d,%d...", vendor_id, product_id)
			hid_device.open(vendor_id, product_id)
			hid_device.set_nonblocking(1)
			log.info("Listening for inputs...")

			while True:
				sleep(POLL_INTERVAL)
				data = hid_device.read(REPORT_SIZE)
				if len(data) <= KEY_BYTE:
					continue

				code = data[KEY_BYTE]
				log.debug("Key code %d, report %s", code, data)
				if code in actions:
					run_action(config, actions[code], code, uinput_device)

		except (OSError, UInputError) as e:
			log.error("Device error: %s. Retrying in %d seconds", e, RECONNECT_DELAY)
		except Exception:
			log.exception("Unexpected error. Retrying in %d seconds", RECONNECT_DELAY)

		# Either device may have failed to open, so close only what exists
		if uinput_device is not None:
			with suppress(Exception):
				uinput_device.close()
			uinput_device = None
		with suppress(Exception):
			hid_device.close()

		sleep(RECONNECT_DELAY)


def run_action(config, action, code, uinput_device):
	for operation in action.get('values', []):
		adjust_value(config, operation)

	if action.get('mirror'):
		mirror_key(uinput_device, code)

	for operation in action.get('mqtt', []):
		mqtt_publish(config, operation)

	for operation in action.get('process', []):
		run_process(operation)


def adjust_value(config, operation):
	value = config['values'][operation['name']]

	# Linear adjustment
	if 'adjust' in operation:
		value['value'] += operation['adjust']

	# Percentage adjustment, so the step grows with the value
	if 'adjust_log_percent' in operation:
		percent = operation['adjust_log_percent']
		new_value = int(value['value'] * (1 + percent / 100))

		# Always move by at least one, or small values never change
		if new_value == value['value'] and percent != 0:
			new_value += 1 if percent > 0 else -1

		value['value'] = new_value

	if 'clamp' in value:
		value['value'] = clamp(value['value'], value['clamp']['min'], value['clamp']['max'])


def mirror_key(uinput_device, code):
	log.info("Mirroring key code %d as %s", code, ecodes.KEY.get(code, 'an unnamed key'))
	uinput_device.write(ecodes.EV_KEY, code, 1)
	uinput_device.syn()
	uinput_device.write(ecodes.EV_KEY, code, 0)
	uinput_device.syn()


def mqtt_publish(config, operation):
	payload = ''
	if 'value' in operation:
		payload = config['values'][operation['value']]['value']
	if 'message' in operation:
		payload = operation['message']

	host = config['mqtt_host']
	log.info('Sending MQTT, topic: "%s", payload: "%s", host: "%s"', operation['topic'], payload, host)
	try:
		publish.single(operation['topic'], payload, hostname=host)
	except Exception as e:
		log.error("MQTT publish to %s failed: %s", host, e)


def run_process(operation):
	log.info('Running command: "%s"', operation['command'])
	try:
		subprocess.Popen(
			operation['command'],
			shell=True,
			start_new_session=True,
			stdin=subprocess.DEVNULL,
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
		)
	except OSError as e:
		log.error("Command failed to start: %s", e)


def clamp(n, low, high):
	return max(low, min(n, high))


def main():
	parser = argparse.ArgumentParser(description="Run configured actions when keys are pressed on a USB HID keypad.")
	mode = parser.add_mutually_exclusive_group(required=True)
	mode.add_argument('--config', help="path to a configuration file")
	mode.add_argument('--manual', action='store_true', help="choose a device from a menu and log its key codes, with no actions")
	parser.add_argument('--debug', action='store_true', help="log every HID report received")
	args = parser.parse_args()

	logging.basicConfig(
		level=logging.DEBUG if args.debug or args.manual else logging.INFO,
		format='%(levelname)s: %(message)s',
	)

	try:
		if args.config:
			config = parse_config(args.config)
		else:
			config = {'device': manual_device_menu(), 'values': {}, 'actions': {}}
	except StartupError as e:
		log.error("%s", e)
		sys.exit(1)

	with suppress(KeyboardInterrupt):
		listen(config)


if __name__ == "__main__":
	main()
