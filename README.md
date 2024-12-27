# PyKeyCatcher

This is a generic script for catching keystrokes from a specific HID keyboard device. This repo is designed to by used in conjunction with generic addon USB keyboards, configured with the repo [ch57x-keyboard-tool](https://github.com/kriomant/ch57x-keyboard-tool).

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

To use without a configuration file run with the `--manual` switch.
```bash
./pykeycatcher.py --manual
```
