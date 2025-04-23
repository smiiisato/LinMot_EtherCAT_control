import ctypes
import os
import struct
import csv
from queue import Queue
import threading
import time
import queue

def process_input_data(app):
        """
        Processes the input data received from the EtherCAT communication.

        This method retrieves data from the EtherCAT communication channel, updates internal data structures
        for each device, and calculates any necessary fields.

        Parameters:
            app: The main application instance containing shared data.
            data_length (int): The length of data block for each device.

        Functionality:
            - Locks access to shared data for thread safety.
            - Unpacks the data from the drives and updates internal data structures.
            - Tracks changes in the data to detect new updates.
        """
        with app.lock:
            all_slave_data = app.ethercat_comm.data[:]
        
        # Read Data from Drive
        device_data = bytes(all_slave_data[0:app.data_length])
        with app.lm_drive_lock.gen_wlock():
            app.lm_drive_data_dict[1].unpack_inputs(device_data)
            app.lm_drive_data_dict[1].update_calculated_fields()
        
        try: # This part of script is not necessery, if no time critical motion is needed.
            if device_data != app.device_data_old: # If new data avaiable change a value
                app.lm_drive_data_updated += 1
                if app.lm_drive_data_updated >= 65534:
                    app.lm_drive_data_updated = 0
        except:
            pass
        finally:
            app.device_data_old = device_data


def print_comm_messages(app):
        """
        Prints communication messages from the EtherCAT communication process.

        This method retrieves and prints any error or informational messages from the communication queues.

        Functionality:
            - Reads from the error queue and prints error messages.
            - Reads from the info queue and prints informational messages.
        """
        while not app.ethercat_comm.error_queue.empty(): print(f'Error: {app.ethercat_comm.error_queue.get()}')
        while not app.ethercat_comm.info_queue.empty(): print(f'Info: {app.ethercat_comm.info_queue.get()}')


def loop_print_data(app):
        """
        Continuously prints communication data in the background.
        """
        print(f'Background data printing started for {app.noDev} devices')
        while not app.ethercat_comm.stop_event.is_set():
            app.print_comm_messages()

            with app.lock:
                all_slave_data = app.ethercat_comm.data[:]
            app.process_input_data()

            with app.lm_drive_lock.gen_rlock():
                for i in range(app.noDev):
                    print(f'Received data from device {i + 1}: \n{app.lm_drive_data_dict[i + 1]}')

            print('\n')
            time.sleep(1)


def save_latency_to_csv(latency_queue, filename="latency_log.csv"):
        #fieldnames = ["timestamp", "comm_latency", "data_lock_latency", "update_latency", "cycle_time"]
        fieldnames = ["timestamp", "latency"]
        
        # Check if the file exists to determine if we need to write the header
        file_exists = os.path.isfile(filename)

        if file_exists:
            os.remove(filename)
            print(f"Existing file '{filename}' removed.")
            file_exists = False
        
        with open(filename, mode='a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()

            while not latency_queue.empty():
                latency_data = latency_queue.get()
                writer.writerow(latency_data)


def save_oszi(app, filename=None):
        """
        Saves oscilloscope data to CSV files.

        This method saves the unpacked EtherCAT data to CSV files. Each device's data is saved in a separate file
        within a directory, and the files are named based on the device number.

        Parameters:
            filename (str, optional): The base name for the CSV files. If not provided,
                                        the default name 'Oszi_recoding' is used.

        Functionality:
            - Drains the EtherCAT communication queue.
            - Unpacks the data for each device.
            - Saves the data to separate CSV files for each device.
            - Increments the file number for each saved batch of data.
        """
        # Drain queue
        raw_data_list = []
        while True:
            try:
                raw_data_list.append(app.data_queue.get_nowait())
            except queue.Empty:
                time.sleep(0.01)
                try:
                    raw_data_list.append(app.data_queue.get_nowait())
                except queue.Empty:
                    break

        if not raw_data_list:
            print("Queue is empty. Nothing to save.")
            return

        if filename is None: #TODO : add datetime to filename
            filename = 'Oszi_recoding'

        # Create a directory to store the separate files if it doesn't exist
        output_dir = f'{filename}_{app.oszi_file_nr}'
        os.makedirs(output_dir, exist_ok=True)

        # Unpack and write to separate CSV files for each device
        #for device_index in range(app.noDev):
        device_filename = os.path.join(output_dir, f'{filename}.csv')
        
        if os.path.exists(device_filename):
            os.remove(device_filename)
            print(f"Existing file '{device_filename}' deleted.")

        csv_data = []
        header_written = False

        for raw_data in raw_data_list:
            # Ensure raw_data is a bytes-like object
            if isinstance(raw_data, list):  # Convert if it's a list
                raw_data = bytes(raw_data)

            # Extract the data for the current device based on its index
            device_data_chunk = raw_data[0:app.InputLength] # the device number is 1 always
            unpacked_dict = unpack_input_data(app, device_data_chunk)
            # Update the calculated fields
            status = update_calculated_fields_from_inputs(app, unpacked_dict)

            # Write the header once and then the data for this device
            if not header_written:
                csv_data.append(list(status.keys()))
                header_written = True
            csv_data.append(list(status.values()))

        # Write the CSV data for this device
        with open(device_filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(csv_data)

        print(f"Saved {len(raw_data_list)} entries to {device_filename}")

        # Increment file number for the next time
        app.oszi_file_nr += 1


def unpack_input_data(app, data):
    """
    Unpacks binary data into a structured dictionary.

    This method unpacks the raw binary data received from the EtherCAT communication and organizes it
    into a dictionary for easier access and processing.

    Parameters:
        data (bytes): The raw binary data to unpack.

    Returns:
        dict: A dictionary containing the unpacked data, with keys corresponding to the device's status
                and monitoring channels.
    """
    def uint16_to_sint16(val):
        """
        Converts a 16-bit unsigned integer to a signed integer.
        """
        return val - 0x10000 if val >= 0x8000 else val
    
    def int32_to_floatieee754(val):
        """
        Converts a signed 32-bit integer to a float using IEEE 754 format.
        """
        import struct
        packed_val = struct.pack('<i', val)  # pack as int32 (little endian)
        return struct.unpack('<f', packed_val)[0]
    
    base_format = '<HHHiiiHHi'
    mon_channel_format = 'i' * app.no_Monitoring
    full_format = base_format + mon_channel_format

    unpacked = struct.unpack(full_format, data)

    # Convert the monitoring channels to signed integers
    unpacked = list(unpacked)
    for i in range(len(unpacked) - app.no_Monitoring, len(unpacked) - 1):
        unpacked[i] = uint16_to_sint16(unpacked[i])
    # Convert the 32-bit signed integers to floats
    unpacked[-1] = int32_to_floatieee754(unpacked[-1])

    base_keys = [
        'state_var',
        'status_word',
        'warn_word',
        'demand_pos',
        'actual_pos',
        'demand_curr',
        'cfg_status',
        'cfg_index_in',
        'cfg_value_in'
    ]
    mon_keys = [f'mon_ch{i}' for i in range(1, app.no_Monitoring + 1)]

    all_keys = base_keys + mon_keys

    return dict(zip(all_keys, unpacked))
    

def update_calculated_fields_from_inputs(app, inputs):
        """
        Calculates derived status values from given input dictionary and config,
        and returns a status dictionary.
        """
        config = {
            'is_rotary_motor': False,
            'pos_scale_numerator': 10000.0,
            'pos_scale_denominator': 1.0,
            'unit_scale': 10000.0,
            'modulo_factor': 360000,
            'fc_force_scale': 0.1,
            'analog_diff_voltage_scale': 0.0048828125, # V/bit
            'analog_voltage_scale': 0.00244140625, # V/bit
            'fc_torque_scale': 0.00057295779513082,
            'load_cell_scale': 19.6133, # N/V
            'drive_name': "LMDrive",
            'drive_type': "0" #"Undefined"
        }

        status = {}

        unit_scale = config['pos_scale_numerator'] / config['pos_scale_denominator']

        # Update status fields based on inputs
        status['operation_enabled'] = bool(inputs['status_word'] & 0x0001)
        status['switch_on_locked'] = bool(inputs['status_word'] & 0x0040)
        status['homed'] = bool(inputs['status_word'] & 0x0800)
        status['motion_active'] = bool(inputs['status_word'] & 0x2000)
        status['warning'] = bool(inputs['status_word'] & 0x0080)
        status['error'] = bool(inputs['status_word'] & 0x0008)

        # Check error state
        if inputs['state_var'] & 0xFF00 == 0x0400:
            status['error_code'] = inputs['state_var'] & 0x00FF
        else:
            status['error_code'] = 0x00

        # Scaled physical values
        status['demand_position'] = ctypes.c_int32(inputs['demand_pos']).value / unit_scale
        status['actual_position'] = ctypes.c_int32(inputs['actual_pos']).value / unit_scale
        status['difference_position'] = round(status['demand_position'] - status['actual_position'], 4)
        status['actual_current'] = ctypes.c_int16(inputs['demand_curr']).value / 1000.0

        status['measured_force'] = ctypes.c_int32(inputs['mon_ch1']).value * config['fc_force_scale']
        status['analog_diff_voltage'] = ctypes.c_int32(inputs['mon_ch2']).value * config['analog_diff_voltage_scale']
        status['analog_diff_voltage_filtered'] = ctypes.c_float(inputs['mon_ch4']).value * config['analog_diff_voltage_scale']  # V
        status['analog_voltage'] = ctypes.c_int32(inputs['mon_ch3']).value * config['analog_voltage_scale']
        # calculate the estimated force from analog_diff_voltage filtered
        status['estimated_analog_force'] = status['analog_diff_voltage_filtered'] * config['load_cell_scale']  # N

        return status
