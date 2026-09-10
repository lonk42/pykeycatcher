# PyKeyCatcher

Runs actions when keys are pressed on a USB HID keypad.
It is written for the CH57x macro keypads that [ch57x-keyboard-tool](https://github.com/kriomant/ch57x-keyboard-tool) programs, and reads the key code from the fourth byte of each HID report.

Each key code can trigger any mix of:

- **Mirror**, which sends the key on to the desktop through a virtual keyboard.
- **Values**, integers that keys step up and down by a fixed amount or a percentage, with optional clamping.
- **MQTT**, which publishes a fixed message, or the current value of a value, to a topic.
- **Process**, which runs a shell command in the background.

## Requirements

- Linux, with systemd and udev.
- Python 3 with the `venv` module.
- `sudo`, for the udev rule and the `input` group.

## Install

```bash
git clone https://github.com/lonk42/pykeycatcher.git
cd pykeycatcher
./install.sh
```

`install.sh` runs everything from the checkout, and is safe to re-run after a `git pull`.
It:

1. Creates `.venv` in the checkout and installs the requirements.
2. Copies the example config to `~/.config/pykeycatcher/config.yaml`, if there is none yet.
3. Writes `/etc/udev/rules.d/99-pykeycatcher.rules`, giving the `input` group access to the keypad and to `/dev/uinput`.
4. Adds you to the `input` group.
5. Installs and enables the systemd user unit `pykeycatcher.service`.

On a first install, edit the config, then run `systemctl --user start pykeycatcher`.
Log out and back in if you were added to the `input` group.
The udev rule is written from the device IDs in the config, so re-run `install.sh` after changing them.

If you followed an earlier version of this README, delete `/etc/udev/rules.d/40-usbkeyboard.rules`.

## Finding key codes

Stop the service first, since only one process can open the keypad.

```bash
systemctl --user stop pykeycatcher
.venv/bin/python pykeycatcher.py --manual
```

Pick the keypad from the list, then press each key.
The key code is the number after `Key code`:

```
DEBUG: Key code 232, report [...]
```

## Configuration

[`config.yaml.example`](config.yaml.example) has one of each action.
While pykeycatcher runs, the keys it reads no longer reach the desktop by themselves.
Each key code under `actions` can have any of:

| Action | Takes | Does |
|---|---|---|
| `mirror` | `true` | Sends the evdev key with the same number as the key code, so 190 arrives as `KEY_F20` |
| `values` | a list of `name`, plus `adjust` or `adjust_log_percent` | Adds `adjust`, or multiplies by `1 + adjust_log_percent / 100`, then clamps |
| `mqtt` | a list of `topic`, plus `message` or `value` | Publishes to `mqtt_host` on port 1883, with no authentication |
| `process` | a list of `command` | Runs it with `sh -c` in its own session, with output discarded |

A percentage step always moves a value by at least 1.
Values are held in memory, and go back to their configured `value` when the service restarts.

Commands run in the systemd user manager's environment.
Graphical apps need `DISPLAY` or `WAYLAND_DISPLAY` there; check with `systemctl --user show-environment`.

## Running

```bash
systemctl --user status pykeycatcher     # State
journalctl --user -u pykeycatcher -f     # Follow the log
systemctl --user restart pykeycatcher    # Reload the config
```

The service retries every 5 seconds while the keypad is missing or unplugged.
To run it by hand, stop the service and use the venv's Python:

```bash
.venv/bin/python pykeycatcher.py --config ~/.config/pykeycatcher/config.yaml --debug
```

## Troubleshooting

`Device error: open failed` repeating in the log means the keypad is unplugged, or you do not have access to it.
`Device error: "/dev/uinput" cannot be opened for writing` is the same problem for mirror actions.
Both nodes should be `crw-rw---- root input`, and `id -nG` should include `input`:

```bash
lsusb -d 1189:8890                   # Bus 001 Device 017: ...
ls -l /dev/bus/usb/001/017 /dev/uinput
```

A udev rule for the keypad numbered below 50 has no effect, since `50-udev-default.rules` sets every USB device to `0664` after it.

## Future

- MQTT port, authentication and TLS.
