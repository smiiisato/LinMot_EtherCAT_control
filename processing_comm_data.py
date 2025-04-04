from readerwriterlock import rwlock

device_data_old = 0

def process_input_data(app, noDev, data_length):
    """
    Description:
    Processes EtherCAT communication data for connected drives and updates the application's internal data structures.
    
    Parameters:
        app: The main application instance containing shared data.
        noDev (int): Number of connected devices.
        data_length (int): Data block size for each device.

    Functionality:
        Thread-Safe Data Retrieval: Locks access and copies EtherCAT data.
        Device Data Processing: Iterates through devices, extracts their data, unpacks inputs, and updates calculated fields.

    Purpose:
    Keeps drive data updated for real-time monitoring and control.
    """
    # Read Data from Drive
    with app.lock:
        all_slave_data = app.ethercat_comm.data[:]
    
    for i in range(noDev):
        device_data = bytes(all_slave_data[i*data_length:(i+1)*data_length])
        with app.ethercat_comm.lm_drive_lock.gen_wlock():
            app.ethercat_comm.lm_drive_data_dict[i+1].unpack_inputs(device_data)
            app.ethercat_comm.lm_drive_data_dict[i+1].update_calculated_fields()
            
        try:
            if device_data != device_data_old: # If new data avaiable change a value
                app.ethercat_comm.lm_drive_data_updated += 1
                if app.ethercat_comm.lm_drive_data_updated >= 65534:
                    app.ethercat_comm.lm_drive_data_updated = 0
        except:
            # Handle the case where device_data_old is not defined
            app.ethercat_comm.lm_drive_data_updated = 0
            print("Error: device_data_old is not defined. Initializing to 0.")
            device_data_old = 0
        finally:
            device_data_old = device_data
        


def main():
    print("do nothing")
    
if __name__ == "__main__":
    main()
