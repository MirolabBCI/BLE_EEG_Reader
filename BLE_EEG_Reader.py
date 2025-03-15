#!/usr/bin/env python3
"""
BLE EEG Reader: Connects to a BLE device to read EEG data from left and right ear channels,
processes it, and saves it to a CSV file.
"""

import asyncio
import time
import queue
from bleak import BleakClient
import ctypes
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Device configuration - Replace with your device's unique BLE address
DEVICE_ADDRESS = "E0:82:BB:70:3A:58"  # Update this with your device's address
UUIDS = {
    "Left Ear": "6e400003-b5b0-f393-e0a9-e50e24dcca9f",
    "Right Ear": "6e400003-b5b1-f393-e0a9-e50e24dcca9f"
}
EEG_DATA_FILENAME = datetime.now().strftime("%Y%m%d_%H%M%S") + "_eeg_data.csv"

class BLEDevice:
    """Handles BLE device connection and EEG data processing."""
    def __init__(self, address, uuids, data_queues, filename_prefix):
        self.address = address
        self.uuids = uuids
        self.packet_counts = {uuid: 0 for uuid in uuids.values()}
        self.total_packets = {uuid: 0 for uuid in uuids.values()}
        self.start_times = {uuid: time.time() for uuid in uuids.values()}
        self.first_second_skipped = {uuid: False for uuid in uuids.values()}
        self.buffers = {uuid: bytearray() for uuid in uuids.values()}
        self.data_queues = data_queues
        self.filename_prefix = filename_prefix
        self.uuid_to_name = {v: k for k, v in uuids.items()}

    def process_packet(self, uuid, packet):
        """Process incoming BLE packet and extract EEG data."""
        if len(packet) < 8:
            logger.warning(f"Invalid packet length: {len(packet)}")
            return
        hex_packet = ' '.join(f'{byte:02X}' for byte in packet)
        self.packet_counts[uuid] += 1
        self.total_packets[uuid] += 1
        signal_quality = int(hex_packet[15:17], 16)
        high_byte = int(hex_packet[18:20], 16)
        low_byte = int(hex_packet[21:23], 16)
        raw_value = (high_byte << 8) | low_byte
        if raw_value >= 32768:
            raw_value -= 65536
        raw_value_microvolts = raw_value * (1.8 / 4096) / 2000 * 1000
        self.data_queues[uuid].put((time.time(), raw_value_microvolts))

    def calculate_signal_quality(self, uuid):
        """Calculate and log sampling rate for the channel."""
        current_time = time.time()
        elapsed_time = current_time - self.start_times[uuid]
        if elapsed_time >= 1.0:
            sampling_rate = self.packet_counts[uuid] / elapsed_time
            if self.first_second_skipped[uuid]:
                channel_name = self.uuid_to_name[uuid]
                print(f"{channel_name} {sampling_rate:.2f} (Total: {self.total_packets[uuid]})")
            else:
                self.first_second_skipped[uuid] = True
            self.packet_counts[uuid] = 0
            self.start_times[uuid] = current_time

    async def notification_handler(self, uuid, sender, data):
        """Handle BLE notifications and process data packets."""
        self.buffers[uuid] += data
        while b'\xAA\xAA' in self.buffers[uuid]:
            start_index = self.buffers[uuid].find(b'\xAA\xAA')
            if len(self.buffers[uuid]) >= start_index + 8:
                packet = self.buffers[uuid][start_index:start_index + 8]
                self.process_packet(uuid, packet)
                self.buffers[uuid] = self.buffers[uuid][start_index + 8:]
            else:
                break
        self.calculate_signal_quality(uuid)

    async def read_data_from_device(self):
        """Connect to BLE device and start reading data."""
        retry_attempts = 5
        while retry_attempts > 0:
            try:
                async with BleakClient(self.address) as client:
                    print(f"Connected to {self.address}")
                    logger.info(f"Connected to {self.address}")
                    for ear, uuid in self.uuids.items():
                        await client.start_notify(uuid, lambda s, d, u=uuid: asyncio.create_task(self.notification_handler(u, s, d)))
                    while True:
                        await asyncio.sleep(1)
            except Exception as e:
                retry_attempts -= 1
                print(f"Retrying connection... ({retry_attempts} attempts left)")
                logger.error(f"Connection error: {e}. Retries left: {retry_attempts}")
                await asyncio.sleep(5)

async def save_data_to_file(data_queues, file_handle):
    """Save EEG data from queues to a CSV file."""
    left_ear_queue = data_queues["6e400003-b5b0-f393-e0a9-e50e24dcca9f"]
    right_ear_queue = data_queues["6e400003-b5b1-f393-e0a9-e50e24dcca9f"]
    buffer = []
    total_lines = 0
    left_buffer = []
    right_buffer = []

    file_handle.write("Left Ear,Right Ear\n")
    file_handle.flush()

    last_log_time = time.time()
    while True:
        while not left_ear_queue.empty():
            left_buffer.append(left_ear_queue.get())
        while not right_ear_queue.empty():
            right_buffer.append(right_ear_queue.get())

        while left_buffer and right_buffer:
            left_data = left_buffer.pop(0)
            right_data = right_buffer.pop(0)
            left_value = f"{left_data[1]:.6f}"
            right_value = f"{right_data[1]:.6f}"
            buffer.append(f"{left_value},{right_value}\n")
            total_lines += 1

            if len(buffer) >= 100:
                file_handle.writelines(buffer)
                buffer.clear()
                file_handle.flush()

        current_time = time.time()
        if current_time - last_log_time >= 1.0:
            print(f"Written {total_lines} lines")
            last_log_time = current_time

        if buffer:
            file_handle.writelines(buffer)
            buffer.clear()
            file_handle.flush()

        await asyncio.sleep(0)

async def main():
    """Main function to run BLE EEG data collection."""
    data_queues = {uuid: queue.Queue() for uuid in UUIDS.values()}
    ble_device = BLEDevice(DEVICE_ADDRESS, UUIDS, data_queues, "1")

    with open(EEG_DATA_FILENAME, "a", newline='') as file_handle:
        try:
            await asyncio.gather(
                ble_device.read_data_from_device(),
                save_data_to_file(data_queues, file_handle)
            )
        except KeyboardInterrupt:
            print("Shutting down, flushing remaining data...")
            left_buffer = []
            right_buffer = []
            while not data_queues["6e400003-b5b0-f393-e0a9-e50e24dcca9f"].empty():
                left_buffer.append(data_queues["6e400003-b5b0-f393-e0a9-e50e24dcca9f"].get())
            while not data_queues["6e400003-b5b1-f393-e0a9-e50e24dcca9f"].empty():
                right_buffer.append(data_queues["6e400003-b5b1-f393-e0a9-e50e24dcca9f"].get())
            while left_buffer and right_buffer:
                left_data = left_buffer.pop(0)
                right_data = right_buffer.pop(0)
                file_handle.write(f"{left_data[1]:.6f},{right_data[1]:.6f}\n")
            for left_data in left_buffer:
                file_handle.write(f"{left_data[1]:.6f},\n")
            for right_data in right_buffer:
                file_handle.write(f",{right_data[1]:.6f}\n")
            file_handle.flush()
            raise

if __name__ == "__main__":
    try:
        ctypes.windll.ole32.CoInitializeEx(0, 0x0)
    except AttributeError:
        pass  # Ignore if not on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program stopped by user.")
        logger.info("Program stopped by user. File saved.")
