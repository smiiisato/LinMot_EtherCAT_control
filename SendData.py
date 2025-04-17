import time

# Motor Control Functions --------------------------------------------------------

def swichON_motor(app, active_drive_number):
    """
    Turns the motor ON by modifying the control word:
        Sends the current control word to the drive.
        Clears bit 0 (Switch ON = 0).
        Sends the updated control word.
        Sets bit 0 (Switch ON = 1).
        Sends the final updated control word.
    """
    #send_data_to_slaves(app) # Send Current Control Word
    with app.lm_drive_lock.gen_wlock():
        app.lm_drive_data_dict[active_drive_number].outputs['control_word'] &= ~0x0001 # Clear bit 0 (Switch ON = 0)
    send_data_to_slaves(app) # Send Current Control Word
    time.sleep(max(app.cycle_time * 2, 0.001))
    with app.lm_drive_lock.gen_wlock():
        app.lm_drive_data_dict[active_drive_number].outputs['control_word'] |= 0x0001 # Set bit 0 (Switch ON = 1)
    send_data_to_slaves(app)# Send Current Control Word

def swichOFF_motor(app, active_drive_number):
    """
    Turns the motor OFF by clearing bit 0 of the control word and sending the updated control word.
    """
    with app.lm_drive_lock.gen_wlock():
        app.lm_drive_data_dict[active_drive_number].outputs['control_word'] &= ~0x0001 # Clear bit 0 (Switch ON = 0)
    send_data_to_slaves(app)

def home_motor(app, active_drive_number):
    """
    Initiates the homing process by setting bit 11 (Home = 1) in the control word and sending the updated control word.
    """
    with app.lm_drive_lock.gen_wlock():
        app.lm_drive_data_dict[active_drive_number].outputs['control_word'] |= 0x0800 # Set bit 11 (Home = 1)
    send_data_to_slaves(app)

def end_home_motor(app, active_drive_number):
    """
    Ends the homing process by clearing bit 11 (Home = 0) in the control word and sending the updated control word.
    """
    with app.lm_drive_lock.gen_wlock():
        app.lm_drive_data_dict[active_drive_number].outputs['control_word'] &= ~0x0800 # Clear bit 11 (Home = 0)
    send_data_to_slaves(app)
    
def error_ack(app, active_drive_number):
    """
    Acknowledges and clears errors in the drive:
        Sets bit 7 (Error Acknowledge = 1).
        Clears bit 0 (Switch ON = 0).
        Sends the updated control word.
        Clears bit 7 (Error Acknowledge = 0).
        Sends the updated control word again.
    """
    with app.lm_drive_lock.gen_wlock():
        app.lm_drive_data_dict[active_drive_number].outputs['control_word'] |= 0x0080 # Set bit 7 (Error Acknoledge = 1)
        app.lm_drive_data_dict[active_drive_number].outputs['control_word'] &= ~0x0001 # Clear bit 0 (Switch ON = 0)
    send_data_to_slaves(app) # Send Data
    time.sleep(max(app.cycle_time * 2, 0.001))
    with app.lm_drive_lock.gen_wlock():
        app.lm_drive_data_dict[active_drive_number].outputs['control_word'] &= ~0x0080 # Clear bit 7 (Error Acknoledge = 1)
    send_data_to_slaves(app) # Send Data

# Utility Functions -----------------------------------------------------------------

def get_unit_scale(app, active_drive_number):
    """
    Returns the scaling factor for the selected drive:
        If the motor is rotary, it returns the modulo_factor.
        If not, it returns the unit_scale.
    """
    with app.lm_drive_lock.gen_rlock():
        if app.lm_drive_data_dict[active_drive_number].config['is_rotary_motor']:
            return app.lm_drive_data_dict[active_drive_number].config['modulo_factor']
        else:
            return app.lm_drive_data_dict[active_drive_number].config['unit_scale']
    
    
def hex_valid(app, value:hex, bit=16):
    """
    Validates and converts a hexadecimal value:
        If input is a string, it converts it to an integer.
        If input is an integer or float, it ensures it's an integer.
        If input is invalid, it prints an error message and returns None.
    """
    try:
        if isinstance(value, str):
            return int(value, bit)
        elif isinstance(value, int):
            return value
        elif isinstance(value, float):
            return int(value)
        else:
            return None
    except ValueError:
        app.insert_message('Invalid hex string in Control Word')
        print('Invalid hex string')
        return None
    
def toggle_bits(app, active_drive_number, header):
    """
    Toggles the command counter bits in a 16-bit header:
        Extracts the lower 4 bits of state_var (command count).
        Increments the count (modulo 16).
        Updates the header with the new command count.
    """
    with app.lm_drive_lock.gen_rlock():
        cmd_count_old = app.lm_drive_data_dict[active_drive_number].inputs['state_var'] & 0x000F
    if int(cmd_count_old) == 15:
        cmd_count_old = 0
    cmd_count_new = (cmd_count_old + 1) % 16
    return (header & 0xFFF0) | cmd_count_new

def toggle_bits_cfg(app, active_drive_number, header):
    """
    Toggles the configuration command counter bits in a 16-bit header:
        Extracts the lower 4 bits of cfg_status (config status count).
        Increments the count (modulo 16).
        Updates the header with the new count.
    """
    with app.lm_drive_lock.gen_rlock():
        cmd_count_old = app.lm_drive_data_dict[active_drive_number].inputs['cfg_status'] & 0x000F
    cmd_count_new = (cmd_count_old + 1) % 16
    return (header & 0xFFF0) | cmd_count_new

def convert23to16(value):
    """
    Splits a 23-bit value into two 16-bit values:
        The lower 16 bits (value_1).
        The upper bits shifted right (value_2).
    """
    value_1 = int(value) & 0xFFFF
    value_2 = int(value) >> 16 & 0xFFFF
    return value_1, value_2

# Drive Communication Functions --------------------------------------------------------------

def update_output_drive_data(app, active_drive_number, controlWord:str, header:str, para_word):
    """
    Updates the drive's output data:
        Processes input data using process_input_data().
        Validates and updates the control_word if provided.
        Validates and updates the mc_header with toggled command bits.
        Processes para_word:
            If values are valid, assigns them to corresponding mc_para_word fields.
            Ensures the number of parameters does not exceed the limit.
        Sends the updated data to the slaves.
    """
    # Update drive Data
    app.process_input_data()
    # control_word
    if controlWord and not controlWord == '0':
        controlWord = hex_valid(app, controlWord)
        if controlWord == None:
            return None
        with app.lm_drive_lock.gen_wlock():
            app.lm_drive_data_dict[active_drive_number].outputs['control_word'] = controlWord
        
    if not header == '' or not header == 0:
        # mc_header
        header = hex_valid(app, header)
        if header == None:
                print('Invalid header')
                return None
        header = toggle_bits(app, active_drive_number, header)
        print(f'header: {header}')
        with app.lm_drive_lock.gen_wlock():
            app.lm_drive_data_dict[active_drive_number].outputs['mc_header'] = header
        
        # para_word
        bit_count = 0
        for pw in para_word:
            if bit_count <= 10:
                if pw is not None:
                    if pw[0] == 1:
                        value_1 = pw[1]
                    if pw[0] == 2:
                        value_1, value_2 = convert23to16(pw[1])
                    with app.lm_drive_lock.gen_wlock():
                        for i in range(pw[0]):
                            app.lm_drive_data_dict[active_drive_number].outputs[f'mc_para_word{bit_count:02}'] = locals()[f'value_{i+1}']
                            bit_count += 1
            else:
                app.insert_message(f'Someting went wrong - there is too much data.')
    send_data_to_slaves(app)

def update_output_cfg(app, active_drive_number, cfg_control, cfg_index_out, cfg_value_out):
    """
    Updates drive configuration data:
        Validates and toggles cfg_control bits.
        Converts and updates cfg_index_out.
        Converts and updates cfg_value_out (if provided).
        Sends the updated configuration to the drive.
    """
    # cfg_control
    cfg_control = hex_valid(app, cfg_control)
    if cfg_control == None:
        return None
    cfg_control = toggle_bits_cfg(app, active_drive_number, cfg_control)
    # cfg_index_out
    cfg_index_out = hex_valid(app, cfg_index_out)
    # cfg_value_out
    if cfg_value_out is not None:
        cfg_value_out = hex_valid(app, cfg_value_out, bit=32)
    
    with app.lm_drive_lock.gen_wlock():
        app.lm_drive_data_dict[active_drive_number].outputs['cfg_control'] = cfg_control
        app.lm_drive_data_dict[active_drive_number].outputs['cfg_index_out'] = cfg_index_out
        if cfg_value_out is not None:
            app.lm_drive_data_dict[active_drive_number].outputs['cfg_value_out'] = cfg_value_out
    
    # Send data to drive
    send_data_to_slaves(app)
    
# Send to Drive ----------------------------------------------------------------------------------
    
def send_data_to_slaves(app):
    """
    Sends packed output data from all drives to the EtherCAT communication queue.
    """
    with app.lm_drive_lock.gen_wlock():
        packed_outputs = [app.lm_drive_data_dict[device].pack_outputs() for device in range(1, app.noDev+1)]
    app.ethercat_comm.update_queue.put(packed_outputs)
    





def main():
    print("do nothing")
    
if __name__ == "__main__":
    main()