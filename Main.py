import pysoem # EtherCAT communication
# Install "pysoem": https://pysoem.readthedocs.io/en/stable/installation.html
# Follow the following instructions to get the additional software: https://pysoem.readthedocs.io/en/stable/requirements.html
# For Windows we reccomend Npcap
import time
import struct
import multiprocessing as mp
import logging
import os
import traceback
import datetime
from readerwriterlock import rwlock
import csv
import LMDrive_Data as LMDD
import SendData as sendData
import numpy as np
import threading
import ctypes
from EtherCATCommunication import EtherCATCommunication

class main_test():
    
    def __init__(self):
        """
        Initializes the main_test class instance.

        Sets up the configuration parameters for EtherCAT communication, device monitoring, logging, and data synchronization.

        Attributes:
            adapter_id (str): The EtherCAT adapter identifier.
            noDev (int): The number of expected EtherCAT devices.
            cycle_time (float): The EtherCAT communication cycle time in seconds.
            no_Monitoring (int): Number of monitoring channels.
            no_Parameter (int): Number of parameter channels.
            Activate_LMDrive_Data (bool): A flag to activate or deactivate LMDrive data functionality.
            mp_logging (int): The logging level for multiprocessing.
            lock (mp.Lock): A lock to synchronize access to shared data.
            lm_drive_data_dict (dict): A dictionary to store LMDrive data for each device.
            data_length (int): The length of data per device.
            lm_drive_data_updated (int): A counter to track updates in LMDrive data.
            device_data_old (int): A variable to track the last device data.
            oszi_file_nr (int): A counter to track saved oscilloscope files.
            lm_drive_lock (rwlock.RWLockFairD): A read-write lock for synchronization.
        """
        # Configuration parameters - Setup
        self.adapter_id = 'enx606d3cf95ad1'
        self.noDev: int = 1 # Number of expected EtherCAT devices
        self.cycle_time: float = 0.003 # Cycle time in seconds
        self.no_Monitoring: int = 4 # How many Monitoring Channels do you want to recieve. Please change "TxData_Default_Inputs_...M" accordingly
        self.no_Parameter: int = 0 # How many Parameter Channels do you want to send
        self.Activate_LMDrive_Data: bool = False # This script works only when set to False
        self.mp_logging: int = 50 # Logging level for multiprocessing
        self.lock = mp.Lock()  # Lock for synchronizing access to the data array
        
        # Parameters
        self.lm_drive_data_dict = {}
        self.data_length = 0
        self.lm_drive_data_updated = 0
        self.device_data_old = 0
        self.oszi_file_nr = 0
        self.config = None
        
        self.lm_drive_lock = rwlock.RWLockFairD()
        self.manager = mp.Manager()

        # flag to print the status of the drive
        self.print_drive_status = False
        # flag to save the oscilloscope data
        self.ozsi_on = True

    def start(self):
        """
        Starts the EtherCAT communication and runs the test process.

        This method initializes the EtherCAT communication, establishes a connection with the drives,
        and handles error checking. It runs the communication process, processes data,
        and performs motor operations like switching on, homing, and motion control.

        Raises:
            RuntimeError: If communication cannot be established or if the script is incorrectly configured.
            KeyboardInterrupt: If the process is interrupted manually.
        """
        # Create an instance of the EtherCATCommunication class
        self.ethercat_comm = EtherCATCommunication(self.adapter_id, self.noDev, self.cycle_time, self.lock, self.no_Monitoring, self.no_Parameter, self.mp_logging)
        
        # Start the EtherCAT communication process
        try:
            self.ethercat_comm.start()
            
            if self.ethercat_comm.comm_proc and self.ethercat_comm.comm_proc.is_alive(): # Check if communication has been established
                # Wait for the communication to work, if it doesn't work within a certain amount of time termintate the process.
                j = 1
                while bool(j):
                    EC_is_running = not self.ethercat_comm.stop_event.wait(timeout=1)
                    print(f'Wait for the master to establish communication with the drive.')
                    if not EC_is_running:
                        time.sleep(0.2)
                        j += 1
                        if j > 20:
                            EC_is_running = False
                            j = 0
                    else:
                        j = 0
            if not EC_is_running:
                while not self.ethercat_comm.error_queue.empty(): print(f'Error: {self.ethercat_comm.error_queue.get()}')
                while not self.ethercat_comm.info_queue.empty(): print(f'Info: {self.ethercat_comm.info_queue.get()}')
                raise RuntimeError(f'Communication could not be established')
                
            # Simulate running the communication until stopped with Ctrl+C
            print('EtherCAT communication running... Press Ctrl+C to stop.')
            time.sleep(3)
            if self.Activate_LMDrive_Data:
                raise RuntimeError(f'This script works only when Activate_LMDrive_Data is set to False')
            else:
                for i in range(self.noDev): # Create LMDrive_Data
                    self.lm_drive_data_dict[i+1] = LMDD.LMDrive_Data(num_mon_channels=self.no_Monitoring, num_par_channels=self.no_Parameter)
            self.config = self.lm_drive_data_dict[1].config
            self.data_length = self.ethercat_comm.InputLength
            
            # Start loop_print_data in a background thread
            if self.print_drive_status:
                print_thread = threading.Thread(target=self.loop_print_data, daemon=True)
                print_thread.start()
            else: # Print only error messages
                print_thread = threading.Thread(target=self.print_comm_messages, daemon=True)
                print_thread.start()

            # start the actuation
            self.test_command_table()
            
        except Exception as e:
            logging.error(e)
            logging.info("Stop EtherCAT communication.")
            self.ethercat_comm.stop_event.set()
        except KeyboardInterrupt:
            logging.info('Keyboard interrupt received, stopping EtherCAT communication.')
            self.ethercat_comm.stop_event.set()  # Signal the communication process to stop
        
        finally:
            # Print all Error Statements
            while not self.ethercat_comm.error_queue.empty(): print(f'Error: {self.ethercat_comm.error_queue.get()}')
            while not self.ethercat_comm.info_queue.empty(): print(f'Info: {self.ethercat_comm.info_queue.get()}')
            # Ensure that the EtherCAT communication process is stopped properly
            logging.info("Stop EtherCAT communication.")
            self.ethercat_comm.stop()
            input("Press enter to exit;")
            
            
    def loop_print_data(self):
        """
        Continuously prints communication data in the background.
        """
        print(f'Background data printing started for {self.noDev} devices')
        while not self.ethercat_comm.stop_event.is_set():
            self.print_comm_messages()

            with self.lock:
                all_slave_data = self.ethercat_comm.data[:]
            self.process_input_data()

            with self.lm_drive_lock.gen_rlock():
                for i in range(self.noDev):
                    print(f'Received data from device {i + 1}: \n{self.lm_drive_data_dict[i + 1]}')

            print('\n')
            time.sleep(1)
    

    def test_command_table(self):
        """
        Switches on the motor -> homes it -> trigger the command table -> switches off the motor.

        Raises:
            RuntimeError: If motion cannot be completed.
        """
        # Setup
        sleep_time_cycle = max(self.cycle_time, 0.001)
        
        # Swich On Motor
        self.process_input_data() # Recieve most current data
        with self.lm_drive_lock.gen_rlock():
            motor_started = self.lm_drive_data_dict[1].status['operation_enabled']
        if not motor_started: # If motor is not swiched on, then swich it on
            sendData.swichON_motor(self, active_drive_number=1)
            
        while not motor_started: # Wait for motor to start
            time.sleep(0.1)
            self.process_input_data() # Recieve most current data
            with self.lm_drive_lock.gen_rlock():
                motor_started = self.lm_drive_data_dict[1].status['operation_enabled']
            #print('wait for motor to start...')
        print(f'Motor swiched on')
        
        # Home Motor
        self.process_input_data()
        
        with self.lm_drive_lock.gen_rlock():
            homing_started = (self.lm_drive_data_dict[1].outputs['control_word'] & 0x0800) != 0
        while not homing_started:
            sendData.home_motor(self, active_drive_number=1)
            print(f'Homing was not started, try again')
            self.process_input_data()
            with self.lm_drive_lock.gen_rlock():
                homing_started = (self.lm_drive_data_dict[1].outputs['control_word'] & 0x0800) != 0
            time.sleep(0.1) # Wait for 0.1 seconds to make sure that the bits have updated
            
        homing_finished = False
        while not homing_finished: # Wait for Motor to home
            time.sleep(0.5) # Longer wait time in order to make sure that the bits have updated
            self.process_input_data()
            with self.lm_drive_lock.gen_rlock():
                homing_finished = self.lm_drive_data_dict[1].status['homed']
                print(f'Homing finished: {homing_finished}')
            print(f'Wait for motor to home...')
        
        self.process_input_data()
        with self.lm_drive_lock.gen_rlock(): # End homing procedere
            homing_started = (self.lm_drive_data_dict[1].outputs['control_word'] & 0x0800) != 0
        if homing_started:
            sendData.end_home_motor(self, active_drive_number=1)
        print(f'Motor homed')

        time.sleep(0.1) # Wait to make sure that eveything is updated
        
        
        # Start oscilloscope reading
        self.ethercat_comm.data_queue_ON.set()
        
        # Move to 50 mm
        print('Send move to 50 mm')
        self.send_motion_command(drive=1, header='Absolute_VAI', target_pos=50, max_v=0.01, acc=0.1, dcc=0.1, jerk=10000)
        self.motion_finished(sleep_time_cycle, active_drive_number=1)
        
        # Wait for 0.2 seconds
        time.sleep(0.2)
        
        # Start command table
        print('Trigger command table')
        sendData.update_output_drive_data(app=self, active_drive_number=1, controlWord=None, header=0x2000, para_word=[[1, 1]]) #start command table

        time.sleep(50)

        # Stop oscilloscope reading
        self.ethercat_comm.data_queue_ON.clear()
        if self.ozsi_on:
            # save oscilloscope data
            self.save_oszi(filename='Oszi_recoding')
        
        # Swich Off Motor
        self.process_input_data()
        with self.lm_drive_lock.gen_rlock():
            motor_started = self.lm_drive_data_dict[1].status['operation_enabled']
        if motor_started:
            sendData.swichOFF_motor(self, active_drive_number=1)
        
        while motor_started: # Wait for motor to start
            time.sleep(0.1)
            self.process_input_data() # Recieve most current data
            with self.lm_drive_lock.gen_rlock():
                motor_started = self.lm_drive_data_dict[1].status['operation_enabled']
        print(f'Motor swiched off')
        
    def print_comm_messages(self):
        """
        Prints communication messages from the EtherCAT communication process.

        This method retrieves and prints any error or informational messages from the communication queues.

        Functionality:
            - Reads from the error queue and prints error messages.
            - Reads from the info queue and prints informational messages.
        """
        while not self.ethercat_comm.error_queue.empty(): print(f'Error: {self.ethercat_comm.error_queue.get()}')
        while not self.ethercat_comm.info_queue.empty(): print(f'Info: {self.ethercat_comm.info_queue.get()}')
    
    def process_input_data(self):
        """
        Processes the input data received from the EtherCAT communication.

        This method retrieves data from the EtherCAT communication channel, updates internal data structures
        for each device, and calculates any necessary fields.

        Parameters:
            self: The main application instance containing shared data.
            data_length (int): The length of data block for each device.

        Functionality:
            - Locks access to shared data for thread safety.
            - Unpacks the data from the drives and updates internal data structures.
            - Tracks changes in the data to detect new updates.
        """
        with self.lock:
            all_slave_data = self.ethercat_comm.data[:]
        
        # Read Data from Drive
        for i in range(self.noDev):
            device_data = bytes(all_slave_data[i*self.data_length:(i+1)*self.data_length])
            with self.lm_drive_lock.gen_wlock():
                self.lm_drive_data_dict[i+1].unpack_inputs(device_data)
                self.lm_drive_data_dict[i+1].update_calculated_fields()
        
        try: # This part of script is not necessery, if no time critical motion is needed.
            if device_data != self.device_data_old: # If new data avaiable change a value
                app.lm_drive_data_updated += 1
                if app.lm_drive_data_updated >= 65534:
                    app.lm_drive_data_updated = 0
        except:
            pass
        finally:
            self.device_data_old = device_data
        
    
    def send_motion_command(self, drive, header, target_pos, max_v, acc, dcc, jerk=100000):
        """
        Sends a motion command to a specified drive.

        This method formats and sends a motion command to the connected drive using parameters like
        position, velocity, acceleration, deceleration, and jerk.
        The header specifies the motion type (absolute, relative, etc.).

        Parameters:
            drive (int): The drive number to send the motion command to.
            header (str): The type of motion (e.g., "Absolute_VAI").
            target_pos (float): The target position for the motion.
            max_v (float): The maximum velocity for the motion.
            acc (float): The acceleration value.
            dcc (float): The deceleration value.
            jerk (float, optional): The jerk value. Defaults to 100000 if not provided.

        Raises:
            ValueError: If the header is not recognized.
        """
        # Get active Drive
        active_drive_number = int(drive)
        # Assign Motion command
        acc_combined = False
        jerc_necessery = False
        if header == "Absolute_VAI":
            header1 = 0x0100
        elif header == "Relative_VAI":
            header1 = 0x0110
        elif header == "Absolute_VAJI":
            header1 = 0x3A00
            jerc_necessery = True
        elif header == "Relative_VAJI":
            header1 = 0x3A10
            jerc_necessery = True
        elif header == "Incr_Act_Pos_RstI":
            header1 = 0x0D90
        elif header == "Absolute_Sin":
            header1 = 0x0E00
            acc_combined = True
        elif header == "Relative_Sin":
            header1 = 0x0E10
            acc_combined = True
        else:
            raise ValueError('No motion mode defined / found.')

        
        unit_scale = sendData.get_unit_scale(self, active_drive_number) # 10000.0
        pw = [None]*5
        pw[0] = [2, float(target_pos) * unit_scale]
        pw[1] = [2, float(max_v) * unit_scale * 100]
        pw[2] = [2, float(acc) * unit_scale * 10]
        if not acc_combined:
            pw[3] = [2, float(dcc) * unit_scale * 10]
        if jerc_necessery:
            pw[4] = [2, float(jerk) * unit_scale]
        sendData.update_output_drive_data(self, active_drive_number, controlWord = 0, header = header1, para_word=pw)
    
    def motion_finished(self, sleep_time_cycle, active_drive_number):
        """
        Waits for the motion to finish for the given drive.

        This method monitors the motion status of the specified drive and waits until the motion is completed.
        It periodically checks the drive's status and sleeps between checks.

        Parameters:
            sleep_time_cycle (float): The sleep time between each status check.
            active_drive_number (int or list): The drive(s) to monitor for motion completion.

        Returns:
            bool: Returns True when the motion is completed.
        """
        time.sleep(sleep_time_cycle * 4)
        self.process_input_data()
        ldd_old = self.lm_drive_data_updated # Is not necessery, but nice to have
        ma = True # motion_active
        while ma:
            self.process_input_data()
            ldd_new = self.lm_drive_data_updated  # Is not necessery
            if ldd_new != ldd_old:  # Is not necessery
                ldd_old = ldd_new
                if isinstance(active_drive_number, list):
                    j = True
                    with self.lm_drive_lock.gen_rlock():
                        for i in active_drive_number:
                            j = j & (not self.lm_drive_data_dict[i].status['motion_active'])
                    ma = not j
                elif isinstance(active_drive_number, int):
                    with self.lm_drive_lock.gen_rlock():
                        ma = self.lm_drive_data_dict[active_drive_number].status['motion_active']
                else:
                    raise TypeError('active_drive_number is expected to be an integer or list')
                time.sleep(sleep_time_cycle * 2)
        return True
    
    def save_oszi(self, filename=None):
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
        while not self.ethercat_comm.data_queue.empty():
            raw_data_list.append(self.ethercat_comm.data_queue.get())

        if not raw_data_list:
            print("Queue is empty. Nothing to save.")
            return

        if filename is None: #TODO : add datetime to filename
            filename = 'Oszi_recoding'

        # Create a directory to store the separate files if it doesn't exist
        output_dir = f'{filename}_{self.oszi_file_nr}'
        os.makedirs(output_dir, exist_ok=True)

        # Unpack and write to separate CSV files for each device
        #for device_index in range(self.noDev):
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
            device_data_chunk = raw_data[0:self.data_length] # the device number is 1 always
            unpacked_dict = self.unpack_input_data(device_data_chunk)
            # Update the calculated fields
            status = self.update_calculated_fields_from_inputs(unpacked_dict)

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
        self.oszi_file_nr += 1

    def unpack_input_data(self, data):
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
        mon_channel_format = 'i' * self.no_Monitoring
        full_format = base_format + mon_channel_format

        unpacked = struct.unpack(full_format, data)

        # Convert the monitoring channels to signed integers
        unpacked = list(unpacked)
        for i in range(len(unpacked) - self.no_Monitoring, len(unpacked) - 1):
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
        mon_keys = [f'mon_ch{i}' for i in range(1, self.no_Monitoring + 1)]

        all_keys = base_keys + mon_keys

        return dict(zip(all_keys, unpacked))
    
    def update_calculated_fields_from_inputs(self, inputs):
        """
        Calculates derived status values from given input dictionary and config,
        and returns a status dictionary.
        """
        status = {}

        unit_scale = self.config['pos_scale_numerator'] / self.config['pos_scale_denominator']

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

        status['measured_force'] = ctypes.c_int32(inputs['mon_ch1']).value * self.config['fc_force_scale']
        status['analog_diff_voltage'] = ctypes.c_int32(inputs['mon_ch2']).value * self.config['analog_diff_voltage_scale']
        status['analog_diff_voltage_filtered'] = ctypes.c_float(inputs['mon_ch4']).value * self.config['analog_diff_voltage_scale']  # V
        status['analog_voltage'] = ctypes.c_int32(inputs['mon_ch3']).value * self.config['analog_voltage_scale']
        # calculate the estimated force from analog_diff_voltage filtered
        status['estimated_analog_force'] = status['analog_diff_voltage_filtered'] * self.config['load_cell_scale']  # N

        return status



if __name__ == "__main__":
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
    app = main_test()
    app.start()

