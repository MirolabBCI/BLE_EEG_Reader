# BLE EEG Reader

This project provides a Python script to connect to a Bluetooth Low Energy (BLE) device, read EEG (electroencephalography) data from left and right ear channels, and save the processed data to a CSV file. It is designed for internal use by Mirolab to collect and analyze EEG signals from devices with unique BLE addresses.

## Features
- Connects to a BLE device with a user-specified address in the code.
- Reads EEG data from two channels (Left Ear and Right Ear).
- Processes raw BLE packets into microvolt values.
- Logs sampling rates and signal quality in real-time.
- Saves paired Left/Right ear data to a timestamped CSV file.

## Requirements
- Python 3.8+
- Windows OS (due to `ctypes` and `WindowsSelectorEventLoopPolicy`)
- Dependencies (install via `requirements.txt`):
  - `bleak` for BLE communication

## Installation
1. Clone this repository:
   ```bash
   git clone https://github.com/MirolaBCI/BLE_EEG_Reader.git
   cd BLE_EEG_Reader
