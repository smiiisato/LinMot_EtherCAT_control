import pysoem # EtherCAT communication
# Install "pysoem": https://pysoem.readthedocs.io/en/stable/installation.html
# Follow the following instructions to get the additional software: https://pysoem.readthedocs.io/en/stable/requirements.html
import time
import struct
import multiprocessing as mp
import logging
import os
import traceback
import datetime
from readerwriterlock import rwlock
import LMDrive_Data as LMDD
import SendData as sendData
import csv
import queue
import utils


#----------------------------------------------------------------------------------------------------
# Error Handling
class SlaveCountError(Exception):
    pass

class SdoError(Exception):
    pass


#----------------------------------------------------------------------------------------------------
class EtherCATCommunication:
    """
    This class handles the EtherCAT communication process. It sets up the EtherCAT master, manages
    the communication cycle, and handles data exchange between the master and slaves.

    Attributes:
        adapter_id (str): The ID of the network adapter.
        noDev (int): The number of EtherCAT devices.
        cycle_time (float): The cycle time for communication in seconds.
        mp_log (int): The logging level for multiprocessing (internal Solution)
        master (pysoem.Master): The EtherCAT master object.
        stop_event (mp.Event): Event to signal stopping the communication process.
        no_Monitoring (int): Number of Monitoring channels (0 to 4).
        no_Parameter (int): Number of Parameter channels (0 to 4).
        InputLength (int): Length of input data (is calculated automaticaly)
        data (mp.Array): Shared array for storing data from slaves.
        lock (mp.Lock): Lock for synchronizing access to the data array.
        data_queue (mp.Queue): Queue with data from each cycle - can be activated independently
                               with data_queue_ON. (e.g. for Oszylloscope readings)
        data_queue_ON (mp.Event): While active, the data will be saved in data_queue.
                                  (Defaults to OFF immediately after communication is set up)
        slave_name (manager.list): A list with all the slave names (Types of LinMot Drive)
        update_queue (mp.Queue): Queue for receiving commands to update slave outputs.
                                 Will only process the latest entry!
        error_queue (mp.Queue): Queue for logging errors.
        info_queue (mp.Queue): Queue for logging informational messages.
        comm_proc (mp.Process): The communication process.
        MAX_CYCLE_OVERRUN (int): Maximum allowed cycle time overruns before stopping communication.
        MAX_SLAVE_COMM_ATTEMPTS (int): Maximum atempts to esablish communication with the slave
                                       before terminating the communication
        Activate_LMDrive_Data (bool): Deactivate data and update_queue and save all Data in
                                      lm_drive_data_dict, where the user can access them.
                                      Results in lower performance!
        lm_drive_data_dict (dict): Dictionary with all necessery motor information
                                   (File: _20250314a_LMDrive_Data_v3)
        
    """
    
    def __init__(self, adapter_id:str, noDev:int, cycle_time:float, lock:mp.Lock, no_Monitoring:int=0, no_Parameter:int=0, mp_logging:int=0,
                 ozsi_on:bool=True, record_latency:bool=False):
        """
        Initializes the EtherCATCommunication class with the given parameters.

        Args:
            adapter_id (str): The ID of the network adapter.
            noDev (int): The number of EtherCAT devices.
            cycle_time (float): The cycle time for communication in seconds.
            lock (mp.Lock): Lock for synchronizing access to the data array / LMDrive_Data_Dict
            no_Monitoring (int): Number of Monitoring channels (0 to 4). Valid for all Drives.
            no_Parameter (int): Number of Parameter channels (0 to 4). Valid for all Drives.
            Activate_LMDrive_Data (bool): If True = Create LMDrive_Data for each Drive.
                                          Might reduce performance!
            mp_logging (int, optional): The logging level for multiprocessing. Defaults to 0.
                                        Info: 20; Error: 40
        """
        self.adapter_id = adapter_id
        self.noDev = noDev
        self.cycle_time = cycle_time
        self.mp_log = mp_logging
        self.master = None
        self.stop_event = mp.Event()
        self.stop_event.set() # Default to Set
        self.no_Parameter = no_Parameter
        self.no_Monitoring = no_Monitoring
        self.InputLength = 18 + 8 + (4 * self.no_Monitoring)  #18 + 8 + (4 * self.no_Monitoring)
        self.data = mp.Array('i', noDev*self.InputLength) # Queue for data (Structure: TxData_Default_Inputs) ########################
        self.lock = lock
        self.data_queue = mp.Queue() # Queue for data
        self.data_queue_ON = mp.Event() # Putting data of each cycle in self.data_queue (e.g. for Oscyloscope readings)
        manager = mp.Manager()
        self.slave_name = manager.list([None] * noDev)  # Initialize slave_name list with Manager
        self.update_queue = mp.Queue() # Queue for commands (Structure: Output Data)
        self.error_queue = mp.Queue()# Queue for error (Level 40)
        self.info_queue = mp.Queue()# Queue for info (Level 20)
        self.comm_proc = None
        
        # Constant
        self.MAX_CYCLE_OVERRUN: int = 20
        self.MAX_SLAVE_COMM_ATTEMPTS: int = 10

        # Flag to evaluate the latency
        self.record_latency = record_latency
        self.evaluate_latency = mp.Event() # Default to False
        self.latency_queue = mp.Queue() # Queue for latency data

        # Flag to activate the oscilloscope recording
        self.ozsi_on = ozsi_on
        self.oszi_file_nr = 0
        self.ozsi_timestamp_list = [] # List to store timestamps
        
        
    def check_values(self):
        """
        Check input values.
        
        Return:
            Error, if a value is out of range.
        """
        if not(0 < self.noDev):
            raise ValueError(f"noDev {self.noDev} is out of range! Must be greater than 0.")
        if not(0.0001 <= self.cycle_time <= 1):
            raise ValueError(f"cycle_time {self.cycle_time} is out of range! Must be between 0.0001s and 1s.")
        if not(0 <= self.no_Monitoring <= 4):
            raise ValueError(f"no_Monitoring {self.no_Monitoring} is out of range! Must be between {0} and {4}.")
        if not(0 <= self.no_Parameter <= 4):
            raise ValueError(f"no_Parameter {self.no_Parameter} is out of range! Must be between {0} and {4}.")

    def setup_comm(self):
        """
        Sets up the EtherCAT master and configures the slaves.

        Returns:
            list: List of configured slaves if successful, None otherwise.
        """
        try:
            # Setup EtherCAT master
            self.master = pysoem.Master()
            self.master.open(self.adapter_id)
            if self.master.config_init() != self.noDev:
                raise SlaveCountError(f'Expected {self.noDev} devices, but found {self.master.config_init()}')
            
            # Change slave state to PREOP_STATE
            for i, slave in enumerate(self.master.slaves, start=0):
                self.master.state = pysoem.PREOP_STATE
                self.master.write_state()
                
                # Get the Name of each Slave
                try:
                    self.slave_name[i] = slave.sdo_read(0x1008, 0).decode('utf-8') # Reading the device name from the Object Dictionary
                except pysoem.SdoError as e:
                    self.error_queue.put(f'{datetime.datetime.now()} - Slave name not found: {e}') if self.mp_log >= 40 else None
                    
                # PDO mappings
                try:
                    slave.sdo_write(0x1C12, 0x00, b'\x00') # Clear Output
                    slave.sdo_write(0x1C13, 0x00, b'\x00') # Clear Input
                    slave.sdo_write(0x1A20, 0x00, b'\x00')
                    slave.sdo_write(0x1620, 0x00, b'\x00')
                    # Output
                    slave.sdo_write(0x1C12, 1, (0x1700).to_bytes(2, 'little')) # Default Output
                    slave.sdo_write(0x1C12, 2, (0x1708).to_bytes(2, 'little')) # Config Module Outputs
                    if self.no_Parameter == 0:
                        slave.sdo_write(0x1C12, 0, b'\x02')
                    if self.no_Parameter >= 1:
                        slave.sdo_write(0x1C12, 3, (0x1728).to_bytes(2, 'little')) # Par Channel 1 (Output)
                        if self.no_Parameter == 1:
                            slave.sdo_write(0x1C12, 0, b'\x03')
                    if self.no_Parameter >= 2:
                        slave.sdo_write(0x1C12, 4, (0x1729).to_bytes(2, 'little')) # Par Channel 2 (Output)
                        if self.no_Parameter == 2:
                            slave.sdo_write(0x1C12, 0, b'\x04')
                    if self.no_Parameter >= 3:
                        slave.sdo_write(0x1C12, 5, (0x172A).to_bytes(2, 'little')) # Par Channel 3 (Output)
                        if self.no_Parameter == 3:
                            slave.sdo_write(0x1C12, 0, b'\x05')
                    if self.no_Parameter >= 4:
                        slave.sdo_write(0x1C12, 6, (0x172B).to_bytes(2, 'little')) # Par Channel 4 (Output)
                        if self.no_Parameter == 4:
                            slave.sdo_write(0x1C12, 0, b'\x06')
                    # Input
                    slave.sdo_write(0x1C13, 1, (0x1B00).to_bytes(2, 'little')) # Default Input
                    slave.sdo_write(0x1C13, 2, (0x1B08).to_bytes(2, 'little')) # Config Module Inputs
                    if self.no_Monitoring == 0:
                        slave.sdo_write(0x1C13, 0, b'\x02')
                    if self.no_Monitoring >= 1:
                        slave.sdo_write(0x1C13, 3, (0x1B28).to_bytes(2, 'little')) # Mon Channel 1 (Input)
                        if self.no_Monitoring == 1:
                            slave.sdo_write(0x1C13, 0, b'\x03')
                    if self.no_Monitoring >= 2:
                        slave.sdo_write(0x1C13, 4, (0x1B29).to_bytes(2, 'little')) # Mon Channel 2 (Input)
                        if self.no_Monitoring == 2:
                            slave.sdo_write(0x1C13, 0, b'\x04')
                    if self.no_Monitoring >= 3:
                        slave.sdo_write(0x1C13, 5, (0x1B2A).to_bytes(2, 'little')) # Mon Channel 3 (Input)
                        if self.no_Monitoring == 3:
                            slave.sdo_write(0x1C13, 0, b'\x05')
                    if self.no_Monitoring >= 4:
                        slave.sdo_write(0x1C13, 6, (0x1B2B).to_bytes(2, 'little')) # Mon Channel 4 (Input)
                        if self.no_Monitoring == 4:
                            slave.sdo_write(0x1C13, 0, b'\x06')
                    
                except pysoem.pysoem.SdoError as e:
                    raise SdoError(f'{e} \n    ErrorNote: This error occurs at the startup of the Master/Slave system. '
                                   'Please try again after a while; it should resolve itself over time.')# We are working on a fix.
                except Exception as e:
                    raise SdoError(f'SDO setup error: {e}')
            
            # Change slave state to OP_STATE
            self.master.config_map()
            self.master.state_check(pysoem.OP_STATE, 50000)
            self.master.state = pysoem.OP_STATE
            self.master.write_state()

            print(f'[DEBUG] Master state: {self.master.state}')
            print(f'[DEBUG] Slave state: {self.master.slaves[0].state}')
            
            return self.master.slaves
            
        except Exception as e:
            self.master.close()
            self.error_queue.put(f'{datetime.datetime.now()} - Comm setup failed: {e}') if self.mp_log >= 40 else None
            return None

    def comm_process(self):
        """
        Main communication process that handles the EtherCAT communication cycle.
        """
        # Setup the EtherCAT communication
        slaves = self.setup_comm()
        if (slaves is None) or (None in slaves):
            self.stop_event.set()
            self.error_queue.put(f'{datetime.datetime.now()} - Communication could not be established with slaves / drives.') if self.mp_log >= 40 else None
            return
        
        self.info_queue.put(f'Setup communication successful.') if self.mp_log >= 20 else None
        overrun_count = 0
        self.data_queue_ON.clear() # Default Oszi recording off!
        self.stop_event.clear() # Enable Communication
        self.evaluate_latency.clear() # Default to False
        lock_timeout = max(self.cycle_time-0.010, 0.004)
        
        slave_state = [0]*self.noDev
        
        try:
            while not self.stop_event.is_set():
                start_time = time.perf_counter()
                
                # Check if connection to slave is present
                for i in range(self.noDev):
                    slave_state[i] = (slave_state[i] + 1) * (not slaves[i].state_check(pysoem.OP_STATE, 500) == 8)
                    if slave_state[i] >= 8: # Can be deleted
                        self.info_queue.put(f'{datetime.datetime.now()} - Connection to Salve {i} lost {slave_state[i]} times in a row') if self.mp_log >= 20 else None # Can be deleted
                    if slave_state[i] >= self.MAX_SLAVE_COMM_ATTEMPTS:
                        raise RuntimeError(f'Slave {i} is not in Operational State anymore.')

                # Send/Receive process data
                self.master.send_processdata()
                self.master.receive_processdata(2000)

                # Collect data from all slaves
                all_data = [input_data for slave in slaves for input_data in slave.input]
        
                # Put the received data into the data array
                if self.lock.acquire(timeout=lock_timeout):
                    self.data[:] = all_data[:]
                    self.lock.release()
                if self.ozsi_on and self.data_queue_ON.is_set():
                    #self.data_queue.put(all_data)
                    try:
                        #self.data_queue.put_nowait(all_data)
                        self.data_queue.put_nowait((datetime.datetime.now(), all_data))
                    except queue.Full:
                        self.error_queue.put('data_queue is full. Skipping this cycle.') if self.mp_log >= 30 else None

                # Process the update queue if new Rx data is available
                if not self.update_queue.empty():
                    try:
                        while not self.update_queue.empty(): # Empty queue to get the latest value from queue
                            new_rx_data = self.update_queue.get_nowait()
                        if isinstance(new_rx_data, list) and len(new_rx_data) == len(slaves):
                            for i, rx_data_instance in enumerate(new_rx_data):
                                slaves[i].output = rx_data_instance
                    except Exception as e:
                        self.error_queue.put(f'{datetime.datetime.now()} - Unexpected error while Sending Data: {e}') if self.mp_log >= 40 else None
                    

                if self.record_latency and self.evaluate_latency.is_set():
                    try:
                        latency = time.perf_counter() - start_time
                        self.latency_queue.put_nowait({
                        'timestamp': datetime.datetime.now(),
                        'latency': latency,
                    })
                    except queue.Full:
                        self.error_queue.put('data_queue is full. Skipping this cycle.') if self.mp_log >= 30 else None
                
                # Handle cycle time
                elapsed_time = time.perf_counter() - start_time
                sleep_time = self.cycle_time - elapsed_time - 0.0004
                    
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    overrun_count = 0
                else:
                    overrun_count += 1
                    self.error_queue.put(f'{datetime.datetime.now()} - Cycle time overrun: '
                                         f'No. {overrun_count} with {sleep_time}s') if self.mp_log >= 40 else None
                    if overrun_count > self.MAX_CYCLE_OVERRUN:
                        raise RuntimeError(f'Cycle time repeatedly ({self.MAX_CYCLE_OVERRUN}) overrun, stopping communication.')
        except KeyboardInterrupt:
            self.info_queue.put('Communication interrupted by user.') if self.mp_log >= 20 else None
            self.stop_event.set()
        except Exception as e:
            self.error_queue.put(f'{datetime.datetime.now()} - Unexpected error: {e}') if self.mp_log >= 40 else None
        finally:
            self.stop_event.set()
            self.info_queue.put('Setting master to SAFEOP_STATE and closing master.') if self.mp_log >= 20 else None
            self.master.state = pysoem.SAFEOP_STATE
            self.master.write_state()
            self.master.close()
            self.info_queue.put('Comm function stopped') if self.mp_log >= 20 else None
    
    def start(self):
        """
        Starts the EtherCAT communication process in a separate process.
        """
        try:
            self.check_values()
            self.comm_proc = mp.Process(target=self.comm_process)
            self.comm_proc.start()
            
        except Exception as e:
            logging.error(f"Failed to start communication process: {e}")
            self.error_queue.put(f"{datetime.datetime.now()} - Failed to start communication process: {e}") if self.mp_log >= 40 else None
            self.stop_event.set()
            self.stop()
    
    def stop(self):
        """
        Stops the EtherCAT communication process and clears all queues safely.
        """
        if self.record_latency:
            logging.info("Saving latency data to CSV file.")
            utils.save_latency_to_csv(latency_queue=self.latency_queue)
        
        if self.ozsi_on:
                # save oscilloscope data
                logging.info("Saving ozsi data to CSV file.")
                utils.save_oszi(self, filename=None)

        if self.comm_proc:
            logging.info("Setting stop event.")
            self.stop_event.set()

            # Try to join the communication process with timeout
            self.comm_proc.join(timeout=2)

            if self.comm_proc.is_alive():
                logging.warning("Communication process did not terminate. Attempting to clear queues.")

                # Helper function to safely drain a queue
                def drain_queue(q, name):
                    count = 0
                    while not q.empty():
                        try:
                            q.get_nowait()
                            count += 1
                        except Exception as e:
                            logging.warning(f"Failed to get from {name}: {e}")
                            break
                    logging.info(f"Cleared {count} entries from {name}.")

                # Drain all queues
                drain_queue(self.error_queue, "error_queue")
                drain_queue(self.info_queue, "info_queue")
                drain_queue(self.update_queue, "update_queue")
                drain_queue(self.data_queue, "data_queue")

                # Give the process another chance to terminate cleanly
                self.comm_proc.join(timeout=1)

                if self.comm_proc.is_alive():
                    logging.error("Communication process still alive. Forcefully terminating.")
                    self.comm_proc.terminate()
                    self.comm_proc.join(timeout=1)

            if self.comm_proc.is_alive():
                logging.error("Communication process did not terminate even after forceful termination.")
            else:
                logging.info("EtherCAT communication process stopped successfully.")

