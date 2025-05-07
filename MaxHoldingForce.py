import time
import multiprocessing as mp
import logging
from readerwriterlock import rwlock
import LMDrive_Data as LMDD
import SendData as sendData
import threading
from EtherCATCommunication import EtherCATCommunication
import utils

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
        self.cycle_time: float = 0.0015 # Cycle time in seconds
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
        self.config = None
        
        self.lm_drive_lock = rwlock.RWLockFairD()
        self.manager = mp.Manager()

        # flag to print the status of the drive
        self.print_drive_status = False

        # Clutch engaged flag
        self.clutch_engaged = False
        # flag to check if the activated time is finished
        self.activation_finished = False

        # logging 
        self.ozsi_on = True
        self.record_latency = False

        VOLTAGE = 100
        ACTIVATED_TIME = 0.2 # Time in seconds
        FLIPPING_PERIOD = [0] # 0 or 0.05 or 0.1
        self.loop_nr = 5  # default = 6
        self.test_duration = 8

        self.filenames = []
        for flipping_period in FLIPPING_PERIOD:
            for i in range(self.loop_nr):
                filename = f'{VOLTAGE}V-activated-{ACTIVATED_TIME}-flip-{flipping_period}-{i+1}'
                self.filenames.append(filename)
        

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
        self.ethercat_comm = EtherCATCommunication(self.adapter_id, 
                                                   self.noDev, 
                                                   self.cycle_time, 
                                                   self.lock, 
                                                   self.no_Monitoring, 
                                                   self.no_Parameter, 
                                                   self.mp_logging,
                                                   ozsi_on=self.ozsi_on,
                                                   record_latency=self.record_latency
                                                    )
        
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
                print_thread = threading.Thread(target=utils.loop_print_data(self), daemon=True)
                print_thread.start()
            else: # Print only error messages
                print_thread = threading.Thread(target=utils.print_comm_messages(self), daemon=True)
                print_thread.start()

            # start the actuation
            self.max_holding_force_motion_control()
            
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
    

    def max_holding_force_motion_control(self):
        """
        Switches on the motor -> homes it -> trigger the command table -> switches off the motor.

        Raises:
            RuntimeError: If motion cannot be completed.
        """
        # Setup
        sleep_time_cycle = max(self.cycle_time, 0.001)
        
        # Swich On Motor
        utils.process_input_data(self) # Recieve most current data
        with self.lm_drive_lock.gen_rlock():
            motor_started = self.lm_drive_data_dict[1].status['operation_enabled']
        if not motor_started: # If motor is not swiched on, then swich it on
            sendData.swichON_motor(self, active_drive_number=1)
            
        while not motor_started: # Wait for motor to start
            time.sleep(0.1)
            utils.process_input_data(self) # Recieve most current data
            with self.lm_drive_lock.gen_rlock():
                motor_started = self.lm_drive_data_dict[1].status['operation_enabled']
            #print('wait for motor to start...')
        print(f'Motor swiched on')
        
        # Home Motor
        utils.process_input_data(self)
        
        with self.lm_drive_lock.gen_rlock():
            homing_started = (self.lm_drive_data_dict[1].outputs['control_word'] & 0x0800) != 0
        while not homing_started:
            sendData.home_motor(self, active_drive_number=1)
            print(f'Homing was not started, try again')
            utils.process_input_data(self)
            with self.lm_drive_lock.gen_rlock():
                homing_started = (self.lm_drive_data_dict[1].outputs['control_word'] & 0x0800) != 0
            time.sleep(0.1) # Wait for 0.1 seconds to make sure that the bits have updated
            
        homing_finished = False
        while not homing_finished: # Wait for Motor to home
            time.sleep(0.5) # Longer wait time in order to make sure that the bits have updated
            utils.process_input_data(self) # Recieve most current data
            with self.lm_drive_lock.gen_rlock():
                homing_finished = self.lm_drive_data_dict[1].status['homed']
                print(f'Homing finished: {homing_finished}')
            print(f'Wait for motor to home...')
        
        utils.process_input_data(self)
        with self.lm_drive_lock.gen_rlock(): # End homing procedere
            homing_started = (self.lm_drive_data_dict[1].outputs['control_word'] & 0x0800) != 0
        if homing_started:
            sendData.end_home_motor(self, active_drive_number=1)
        print(f'Motor homed')

        time.sleep(0.1) # Wait to make sure that eveything is updated
        
        # Move to 15 mm
        print('Send move to 15 mm')
        sendData.send_motion_command(self, drive=1, header='Absolute_VAI', target_pos=15, max_v=0.01, acc=0.1, dcc=0.1, jerk=10000)
        sendData.motion_finished(self, sleep_time_cycle, active_drive_number=1)
        
        # Wait for 0.2 seconds
        time.sleep(0.2)

        # === Main experiment loop over filenames ===
        for i, filename in enumerate(self.filenames):
            # Wait for clutch engagement
            while not self.clutch_engaged:
                utils.process_input_data(self)
                with self.lm_drive_lock.gen_rlock():
                    self.clutch_engaged = (self.lm_drive_data_dict[1].status['analog_voltage'] > 0.5)

            # Start oscilloscope
            self.ethercat_comm.data_queue_ON.set()
            self.ethercat_comm.evaluate_latency.set()

            while not self.activation_finished:
                utils.process_input_data(self)
                with self.lm_drive_lock.gen_rlock():
                    self.activation_finished = (self.lm_drive_data_dict[1].status['analog_voltage'] < 0.5)

            # Trigger command table at the same time as the clutch is engaged
            sendData.update_output_drive_data(app=self, active_drive_number=1, controlWord=None, header=0x2000, para_word=[[1, 1]])

            print(f'Clutch engaged: {self.clutch_engaged}')
            print('Trigger command table: Start motion')
            time.sleep(self.test_duration)

            # Trigger command table: Stop motion
            print('Trigger command table: Stop motion')
            sendData.update_output_drive_data(app=self, active_drive_number=1, controlWord=None, header=0x2000, para_word=[[1, 6]])
            self.ethercat_comm.data_queue_ON.clear()

            # Save data
            if self.ozsi_on:
                logging.info(f"Saving ozsi data to CSV file: {filename}")
                utils.save_oszi(self.ethercat_comm, filename=filename)

            # Return to 15 mm
            print('Send move to 15 mm')
            sendData.send_motion_command(self, drive=1, header='Absolute_VAI', target_pos=15, max_v=0.01, acc=0.1, dcc=0.1, jerk=10000)
            sendData.motion_finished(self, sleep_time_cycle, active_drive_number=1)

            # Reset clutch state
            self.clutch_engaged = False
        
        # Swich Off Motor
        utils.process_input_data(self)
        with self.lm_drive_lock.gen_rlock():
            motor_started = self.lm_drive_data_dict[1].status['operation_enabled']
        if motor_started:
            sendData.swichOFF_motor(self, active_drive_number=1)
        
        while motor_started: # Wait for motor to start
            time.sleep(0.1)
            utils.process_input_data(self) # Recieve most current data
            with self.lm_drive_lock.gen_rlock():
                motor_started = self.lm_drive_data_dict[1].status['operation_enabled']
        print(f'Motor swiched off')
    


if __name__ == "__main__":
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
    app = main_test()
    app.start()

