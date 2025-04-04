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
import _20250314a_LMDrive_Data_v3 as LMDD


#----------------------------------------------------------------------------------------------------
# Data Structures Definition
# These are mont for usage in the main function.
# Depending on how many monitoring channels are used, the TxData_Default_Inputs_...M have to be adjusted in main.
class TxData_Default_Inputs_0M:
    """
    This class is mainly for use in this 'main' function. With 0 Monitoring chennels.
    """
    def __init__(self, data):
        (
            self.StateVar,
            self.StatusWord,
            self.WarnWord,
            self.DemandPosition,
            self.ActualPosition,
            self.DemandCurrent,
            self.CfgStatus,
            self.CfgIndexIn,
            self.CfgValueIn
        ) = struct.unpack('<HHHiiiHHi', data)

    def __str__(self):
        return (f"StateVar: {self.StateVar}, "
                f"StatusWord: {self.StatusWord}, "
                f"WarnWord: {self.WarnWord}, "
                f"DemandPosition: {self.DemandPosition}, "
                f"ActualPosition: {self.ActualPosition}, "
                f"DemandCurrent: {self.DemandCurrent}, "
                f"CfgStatus: {self.CfgStatus}, "
                f"CfgIndexIn: {self.CfgIndexIn}, "
                f"CfgValueIn: {self.CfgValueIn} "
                )

class TxData_Default_Inputs_4M:
    """
    This class is mainly for use in this 'main' function. With 4 Monitoring chennels.
    """
    def __init__(self, data):
        (
            self.StateVar,
            self.StatusWord,
            self.WarnWord,
            self.DemandPosition,
            self.ActualPosition,
            self.DemandCurrent,
            self.CfgStatus,
            self.CfgIndexIn,
            self.CfgValueIn,
            self.MonCh1,
            self.MonCh2,
            self.MonCh3,
            self.MonCh4
        ) = struct.unpack('<HHHiiiHHiiiii', data)

    def __str__(self):
        return (f"StateVar: {self.StateVar}, "
                f"StatusWord: {self.StatusWord}, "
                f"WarnWord: {self.WarnWord}, "
                f"DemandPosition: {self.DemandPosition}, "
                f"ActualPosition: {self.ActualPosition}, "
                f"DemandCurrent: {self.DemandCurrent}, "
                f"CfgStatus: {self.CfgStatus}, "
                f"CfgIndexIn: {self.CfgIndexIn}, "
                f"CfgValueIn: {self.CfgValueIn}, "
                f"MonCh1: {self.MonCh1}, "
                f"MonCh2: {self.MonCh2}, "
                f"MonCh3: {self.MonCh3}, "
                f"MonCh4: {self.MonCh4} "
                )

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
    
    def __init__(self, adapter_id:str, noDev:int, cycle_time:float, lock:mp.Lock, no_Monitoring:int=0, no_Parameter:int=0, Activate_LMDrive_Data:bool=False, mp_logging:int=0):
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
        self.InputLength = 18 + 8 + (4 * self.no_Monitoring)
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
        
        self.Activate_LMDrive_Data = Activate_LMDrive_Data
        if self.Activate_LMDrive_Data:
            self.lm_drive_data_dict = manager.dict({i+1: LMDD.LMDrive_Data(no_Monitoring, no_Parameter) for i in range(self.noDev)})
        
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
        
        if self.Activate_LMDrive_Data: # Add drive type to each LMDrive Data
            with self.lock:
                for i in range(self.noDev):
                    drive_type = self.slave_name[i]
                    lm_data = self.lm_drive_data_dict[i+1]
                    lm_data.config['drive_type'] = drive_type # Modify its 'drive_type' inside config
                    self.lm_drive_data_dict[i+1] = lm_data
        
        self.info_queue.put(f'Setup communication successful.') if self.mp_log >= 20 else None
        overrun_count = 0
        self.data_queue_ON.clear() # Default Oszi recording off!
        self.stop_event.clear() # Enable Communication
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
                        raise RuntimeError(f'Salve {i} is not in Operational State anymore.')

                # Send/Receive process data
                self.master.send_processdata()
                self.master.receive_processdata(2000)

                # Collect data from all slaves
                all_data = [input_data for slave in slaves for input_data in slave.input]
                
                # Process Data
                if self.Activate_LMDrive_Data:
                    if self.lock.acquire(timeout=lock_timeout):
                        for i in range(self.noDev):
                            # Put the data into the lm_drive_data_dict
                            device_data = bytes(all_data[i*self.InputLength:(i+1)*self.InputLength])
                            lm_data = self.lm_drive_data_dict[i+1] # Extract the object
                            lm_data.unpack_inputs(device_data) # Modify the object
                            lm_data.update_calculated_fields()
                            self.lm_drive_data_dict[i+1] = lm_data # Reassign it back to the dictionary
                            
                            # Write Data from LMDrive_Data to Drive
                            packed_data = self.lm_drive_data_dict[i+1].pack_outputs() # Pack the processed data for sending
                            slaves[i].output = packed_data # Send packed data to the corresponding slave
                        self.lock.release()
                else:
                    # Put the received data into the data array
                    if self.lock.acquire(timeout=lock_timeout):
                        self.data[:] = all_data[:]
                        self.lock.release()
                    if self.data_queue_ON.is_set():
                        self.data_queue.put(all_data)

                    # Process the update queue if new Rx data is available
                    if not self.update_queue.empty():
                        try:
                            while not self.update_queue.empty(): # Empty queue to get the latest value from 
                                new_rx_data = self.update_queue.get_nowait()
                            if isinstance(new_rx_data, list) and len(new_rx_data) == len(slaves):
                                for i, rx_data_instance in enumerate(new_rx_data):
                                    slaves[i].output = rx_data_instance 
                        except Exception as e:
                            self.error_queue.put(f'{datetime.datetime.now()} - Unexpected error while Sending Data: {e}') if self.mp_log >= 40 else None
                
                
                if self.data_queue_ON.is_set():
                    # Put the received data into the queue (if active)
                    self.data_queue.put(all_data)
                    
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
        Stops the EtherCAT communication process.
        """
        if self.comm_proc:
            logging.info("Setting stop event.")
            self.stop_event.set()
            self.comm_proc.join(timeout=2)
            
            if self.comm_proc.is_alive():
                # Empty every queue
                logging.info('Communication process did not terminate. Try emptying queues:')
                if not self.error_queue.empty():
                    logging.info(f'Clearing error_queue with {self.error_queue.qsize()} entries.')
                    while not self.error_queue.empty():
                        self.error_queue.get_nowait()
                if not self.info_queue.empty():
                    logging.info(f'Clearing info_queue with {self.info_queue.qsize()} entries.')
                    while not self.info_queue.empty():
                        self.info_queue.get_nowait()
                if not self.update_queue.empty():
                    logging.info(f'Clearing update_queue with {self.update_queue.qsize()} entries.')
                    while not self.update_queue.empty():
                        self.update_queue.get_nowait()
                if not self.data_queue.empty():
                    logging.info(f'Clearing data_queue with {self.data_queue.qsize()} entries.')
                    while not self.data_queue.empty():
                        self.data_queue.get_nowait()
                self.comm_proc.join()
                
            if self.comm_proc.is_alive():  
                logging.error('Communication process did not terminate within the timeout period.')
            else:
                logging.info('EtherCAT communication process stopped successfully.')


#----------------------------------------------------------------------------------------------------
# Main Execution
def main() -> None:
    """
    Main function to test the EtherCAT communication. It displays the received values from the slaves
    without sending any commands. The user needs to update the adapter_id, noDev, and cycle_time as per their setup.
    """
    # Configuration parameters
    #adapter_id = '\\Device\\NPF_{F9600FA0-8A4E-41C1-AEA3-976092EB012E}' # Replace with actual adapter ID
    adapter_id = 'enx4cea4161b64f'
    noDev: int = 1 # Number of expected EtherCAT devices
    cycle_time: float = 0.015 # Cycle time in seconds
    no_Monitoring: int = 4 # How many Monitoring Channels do you want to recieve. Please change "TxData_Default_Inputs_...M" accordingly
    no_Parameter: int = 4 # How many Parameter Channels do you want to send
    Activate_LMDrive_Data: bool = False # If the recieved data has to be processed inside the LMDrive_Data calss (Lower performance if True)
    mp_logging: int = 50 # Logging level for multiprocessing
    
    lock = mp.Lock()  # Lock for synchronizing access to the data array
    
    # Create an instance of the EtherCATCommunication class
    ethercat_comm = EtherCATCommunication(adapter_id, noDev, cycle_time, lock, no_Monitoring, no_Parameter, Activate_LMDrive_Data, mp_logging)

    # Start the EtherCAT communication process
    try:
        ethercat_comm.start()
        
        if ethercat_comm.comm_proc and ethercat_comm.comm_proc.is_alive(): # Check if communication has been established
            # Wait for the communication to work, if it doesn't work within a certain amount of time termintate the process.
            j = 1
            while bool(j):
                EC_is_running = not ethercat_comm.stop_event.wait(timeout=1)
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
            while not ethercat_comm.error_queue.empty(): print(f'Error: {ethercat_comm.error_queue.get()}')
            while not ethercat_comm.info_queue.empty(): print(f'Info: {ethercat_comm.info_queue.get()}')
            raise RuntimeError(f'Communication could not be established')
            
        # Simulate running the communication until stopped with Ctrl+C
        print('EtherCAT communication running... Press Ctrl+C to stop.')
        time.sleep(3)
        if Activate_LMDrive_Data:
            for i in range(noDev):
                print(f"Drive Type {i} = {ethercat_comm.lm_drive_data_dict[i+1].config['drive_type']}")
        data_length = ethercat_comm.InputLength
        while not ethercat_comm.stop_event.is_set():
            try:
                # Allow the communication to run, checking for external events
                while not ethercat_comm.error_queue.empty(): print(f'Error: {ethercat_comm.error_queue.get()}')
                while not ethercat_comm.info_queue.empty(): print(f'Info: {ethercat_comm.info_queue.get()}')
                
                if Activate_LMDrive_Data:
                    with lock:
                        for i in range(noDev):
                            print(f'--D{i} = {ethercat_comm.lm_drive_data_dict[i+1]}')
                else:
                    with lock:
                        all_slave_data = ethercat_comm.data[:]
                    for i in range(noDev):
                        print(f'Received data from device {i}: {TxData_Default_Inputs_4M(bytes(all_slave_data[i*data_length:(i+1)*data_length]))}')
                
                time.sleep(1)

            except Exception as e:
                logging.error(e)
                ethercat_comm.stop_event.set()
                    
            except KeyboardInterrupt:
                logging.info('Keyboard interrupt received, stopping EtherCAT communication.')
                ethercat_comm.stop_event.set()  # Signal the communication process to stop
                break

    finally:
        # Print all Error Statements
        while not ethercat_comm.error_queue.empty(): print(f'Error: {ethercat_comm.error_queue.get()}')
        while not ethercat_comm.info_queue.empty(): print(f'Info: {ethercat_comm.info_queue.get()}')
        # Ensure that the EtherCAT communication process is stopped properly
        logging.info("Stop EtherCAT communication.")
        ethercat_comm.stop()
        input("Press enter to exit;")


if __name__ == "__main__":
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
    main()


