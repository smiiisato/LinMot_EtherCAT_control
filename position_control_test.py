from EtherCATCommunication import EtherCATCommunication
import LMDrive_Data as LMDD
import processing_comm_data as pro_comm_data
import multiprocessing as mp
import threading
from readerwriterlock import rwlock
import queue
import time
import logging


class LinMotController:
    def __init__(self, adapter_id, cycle_time, no_Monitoring, no_Parameter, Activate_LMDrive_Data, mp_logging):
        self.adapter_id = adapter_id
        self.noDev = 1  # Number of devices
        self.cycle_time = cycle_time
        self.mp_logging = mp_logging
        self.master = None
        self.stop_event = mp.Event()
        self.stop_event.set()  # Default to Set
        self.no_Parameter = no_Parameter
        self.no_Monitoring = no_Monitoring
        self.InputLength = 18 + 8 + (4 * self.no_Monitoring)
        self.data = mp.Array('i', self.noDev * self.InputLength)  # Shared memory for data
        self.lock = mp.Lock()  # Lock for synchronizing access to the data array
        self.data_queue = mp.Queue()  # Queue for data
        self.data_queue_ON = mp.Event()  # Event flag for data queue usage
        manager = mp.Manager()
        self.slave_name = manager.list([None] * self.noDev)  # Shared list for slave names
        self.update_queue = mp.Queue()  # Queue for commands
        self.error_queue = mp.Queue()  # Queue for error messages
        self.info_queue = mp.Queue()  # Queue for info messages
        self.comm_proc = None
        self.comm_running = False

        # EtherCAT communication instance
        self.ethercat_comm = EtherCATCommunication(adapter_id, cycle_time, no_Monitoring, no_Parameter, Activate_LMDrive_Data, mp_logging)

        # Threading setup
        self.is_updating2 = False  # Flag to prevent multiple update threads
        self.specific_update_interval = [False, 0.5]  # [active_flag, update_interval]

    def start_communication(self):
        """Starts the EtherCAT communication process."""
        self.ethercat_comm.start()

        if self.ethercat_comm.comm_proc and self.ethercat_comm.comm_proc.is_alive():
            j = 1
            while bool(j):
                EC_is_running = not self.ethercat_comm.stop_event.wait(timeout=1)
                print('Wait for the master to establish communication with the drive.')
                if not EC_is_running:
                    time.sleep(0.2)
                    j += 1
                    if j > 20:
                        EC_is_running = False
                        j = 0
                else:
                    j = 0

            print(f'EC_is_running {EC_is_running}')
            if EC_is_running:
                self.comm_running = True
                for i in range(self.noDev):
                    self.ethercat_comm.lm_drive_data_dict[i + 1] = LMDD.LMDrive_Data(
                        num_mon_channels=self.no_Monitoring, num_par_channels=self.no_Parameter
                    )

                print('EtherCAT communication running... Press Ctrl+C to stop.')
                time.sleep(3)

                # Start updating data in a separate thread
                self.start_fast_update_thread()
            else:
                print('Communication could not be established')
                self.stop_communication()

    def stop_communication(self):
        """Stops the EtherCAT communication process and the update thread."""
        if self.mp_logging != 0:
            while not self.ethercat_comm.error_queue.empty():
                print(f'Error: {self.ethercat_comm.error_queue.get()}')
            while not self.ethercat_comm.info_queue.empty():
                print(f'Info: {self.ethercat_comm.info_queue.get()}')

        # Stop updating data
        self.stop_fast_update()

        # Stop EtherCAT communication
        self.ethercat_comm.stop()
        self.comm_running = False
        logging.info("Stopped EtherCAT communication.")
        input("Press Enter to exit;")

    def fast_update_drive_data(self):
        """Runs in a separate thread and continuously updates data until stopped."""
        if self.is_updating2:
            return  # Prevent duplicate threads
        self.is_updating2 = True

        while self.specific_update_interval[0]:  # Loop while active
            pro_comm_data.process_input_data(
                self,
                noDev=self.noDev,
                data_length=self.ethercat_comm.InputLength
            )

            # Simulate data processing
            time.sleep(self.specific_update_interval[1])  # Wait before next update

        self.is_updating2 = False  # Reset flag when stopping

    def start_fast_update_thread(self):
        """Starts fast_update_drive_data in a separate thread if not already running."""
        if not self.is_updating2:
            self.specific_update_interval[0] = True  # Enable updates
            self.update_thread = threading.Thread(target=self.fast_update_drive_data, daemon=True)
            self.update_thread.start()

    def stop_fast_update(self):
        """Stops the update thread."""
        self.specific_update_interval[0] = False  # Disable updates

    def main(self):
        """Main function to test the EtherCAT communication."""
        try:
            self.start_communication()

            if Activate_LMDrive_Data:
                for i in range(self.noDev):
                    print(f"Drive Type {i} = {self.ethercat_comm.lm_drive_data_dict[i + 1].config['drive_type']}")

            data_length = self.ethercat_comm.InputLength
            while not self.ethercat_comm.stop_event.is_set():
                try:
                    while not self.ethercat_comm.error_queue.empty():
                        print(f'Error: {self.ethercat_comm.error_queue.get()}')
                    while not self.ethercat_comm.info_queue.empty():
                        print(f'Info: {self.ethercat_comm.info_queue.get()}')

                    if Activate_LMDrive_Data:
                        with self.lock:
                            for i in range(self.noDev):
                                print(f'--D{i} = {self.ethercat_comm.lm_drive_data_dict[i + 1]}')
                    else:
                        with self.lock:
                            all_slave_data = self.ethercat_comm.data[:]
                        for i in range(self.noDev):
                            print(f'Received data from device {i}: {all_slave_data[i * data_length:(i + 1) * data_length]}')

                    time.sleep(1)

                except Exception as e:
                    logging.error(e)
                    self.ethercat_comm.stop_event.set()

                except KeyboardInterrupt:
                    logging.info('Keyboard interrupt received, stopping EtherCAT communication.')
                    self.ethercat_comm.stop_event.set()
                    break

        finally:
            self.stop_communication()


if __name__ == "__main__":
    # Example usage
     # parameters
    adapter_id = 'enx4cea4161b64f'
    cycle_time = 0.002
    no_Monitoring = 4
    no_Parameter = 4
    Activate_LMDrive_Data = True
    mp_logging = 50
    controller = LinMotController(adapter_id, cycle_time, no_Monitoring, no_Parameter, Activate_LMDrive_Data, mp_logging)
    controller.main()
