import struct
import ctypes

class LMDrive_Data:
    """Class for LinMot drive data
    Includes communication data, motor config parameters and scaled drive status.
    """
    def __init__(self, num_mon_channels, num_par_channels):
        self.num_mon_ch = num_mon_channels  # Number of monitoring channels
        self.num_par_ch = num_par_channels  # Number of parameter channels
        
        self.config = {
            'is_rotary_motor': False,
            'pos_scale_numerator': 10000.0,
            'pos_scale_denominator': 1.0,
            'unit_scale': 10000.0,
            'modulo_factor': 360000,
            'fc_force_scale': 0.1,
            'analog_diff_voltage_scale': 0.0048828125, # V/bit
            'analog_voltage_scale': 0.00244140625, # V/bit
            'fc_torque_scale': 0.00057295779513082,
            'drive_name': "LMDrive",
            'drive_type': "0" #"Undefined"
        }
        
        self.status = {
            'operation_enabled': False,
            'switch_on_locked': False,
            'homed': False,
            'motion_active': False,
            'jogging': False,
            'warning': False,
            'error': False,
            'error_code': 0x00,
            'demand_position': 0.0,
            'actual_position': 0.0,
            'difference_position': 0.0,
            'actual_current': 0.0,
            'nr_of_revolutions': 0,
            'meaured_force': 0.0,
            'analog_diff_voltage': 0.0,
            'analog_voltage': 0.0,
        }
        
        self.outputs = {
            'control_word': 0x003E,
            'mc_header': 0x0000,
            'mc_para_word00': 0x0000,
            'mc_para_word01': 0x0000,
            'mc_para_word02': 0x0000,
            'mc_para_word03': 0x0000,
            'mc_para_word04': 0x0000,
            'mc_para_word05': 0x0000,
            'mc_para_word06': 0x0000,
            'mc_para_word07': 0x0000,
            'mc_para_word08': 0x0000,
            'mc_para_word09': 0x0000,
            'cfg_control': 0x0000,
            'cfg_index_out': 0x0000,
            'cfg_value_out': 0x00000000,
        }
        for i in range(1, self.num_par_ch + 1):
            self.outputs[f'par_ch{i}'] = 0x0000
        
        self.inputs = {
            'state_var': 0x0000,
            'status_word': 0x0000,
            'warn_word': 0x0000,
            'demand_pos': 0x00000000,
            'actual_pos': 0x00000000,
            'demand_curr': 0x0000,
            'cfg_status': 0x0000,
            'cfg_index_in': 0x0000,
            'cfg_value_in': 0x00000000,
        }
        for i in range(1, self.num_mon_ch + 1):
            self.inputs[f'mon_ch{i}'] = 0x0000
        
        
    def update_calculated_fields(self):
        """
        Updates calculated fields based on current input values and configuration.
        """
        # Update `unit_scale` in config
        self.config['unit_scale'] = self.config['pos_scale_numerator'] / self.config['pos_scale_denominator']

        # Update status fields based on inputs
        self.status['operation_enabled'] = bool(self.inputs['status_word'] & 0x0001)  # Bit 0
        self.status['switch_on_locked'] = bool(self.inputs['status_word'] & 0x0040)   # Bit 6
        self.status['homed'] = bool(self.inputs['status_word'] & 0x0800)             # Bit 11
        self.status['motion_active'] = bool(self.inputs['status_word'] & 0x2000)     # Bit 13
        self.status['warning'] = bool(self.inputs['status_word'] & 0x0080)           # Bit 7
        self.status['error'] = bool(self.inputs['status_word'] & 0x0008)             # Bit 3

        # Check error state and set error code
        if self.inputs['state_var'] & 0xFF00 == 0x0400:  # Error state
            self.status['error_code'] = self.inputs['state_var'] & 0x00FF
        else:
            self.status['error_code'] = 0x00

        # Calculate scaled positions and current
        self.status['demand_position'] = ctypes.c_int32(self.inputs['demand_pos']).value / self.config['unit_scale']
        self.status['actual_position'] = ctypes.c_int32(self.inputs['actual_pos']).value / self.config['unit_scale']
        self.status['difference_position'] = round(self.status['demand_position'] - self.status['actual_position'], 4)
        self.status['actual_current'] = ctypes.c_int16(self.inputs['demand_curr']).value / 1000.0

        # measured force
        self.status['measured_force'] = ctypes.c_int32(self.inputs['mon_ch1']).value * self.config['fc_force_scale']  # N

        # update analog diff voltage
        self.status['analog_diff_voltage'] = ctypes.c_int32(self.inputs['mon_ch2']).value * self.config['analog_diff_voltage_scale']  # V

        # update analog voltage
        self.status['analog_voltage'] = ctypes.c_int32(self.inputs['mon_ch3']).value * self.config['analog_voltage_scale']  # V
        
    def unpack_inputs(self, data):
        """
        Unpack input data from a binary structure, adjusting for the number of monitoring channels.
        """
        base_format = '<HHHiiiHHi'  # Format for fixed fields
        mon_channel_format = 'i' * self.num_mon_ch  # Format for dynamic monitoring channels # H = unsigned 16-bit int
        full_format = base_format + mon_channel_format  # Combine formats
        
        unpacked_data = struct.unpack(full_format, data)
        
        (
            self.inputs['state_var'],
            self.inputs['status_word'],
            self.inputs['warn_word'],
            self.inputs['demand_pos'],
            self.inputs['actual_pos'],
            self.inputs['demand_curr'],
            self.inputs['cfg_status'],
            self.inputs['cfg_index_in'],
            self.inputs['cfg_value_in'],
            *mon_channels
        ) = unpacked_data

        # Assign monitoring channels dynamically
        for i, value in enumerate(mon_channels, start=1):
            self.inputs[f'mon_ch{i}'] = value
            signed_value = self.uint16_to_sint16(value)
            self.inputs[f'mon_ch{i}'] = signed_value

    def uint16_to_sint16(self, val):
        return val - 0x10000 if val >= 0x8000 else val

    def unpack_outputs(self, data):
        """
        Unpack output data from a binary structure, adjusting for the number of parameter channels.
        """
        base_format_par = '<HHHHHHHHHHHHHHi'  # Format for fixed fields
        par_channel_format = 'i' * self.num_par_ch  # Format for dynamic monitoring channels
        full_format_par = base_format_par + par_channel_format  # Combine formats
        
        unpacked_par_data = struct.unpack(full_format_par, data)
        (
            self.outputs['control_word'],
            self.outputs['mc_header'],
            self.outputs['mc_para_word00'],
            self.outputs['mc_para_word01'],
            self.outputs['mc_para_word02'],
            self.outputs['mc_para_word03'],
            self.outputs['mc_para_word04'],
            self.outputs['mc_para_word05'],
            self.outputs['mc_para_word06'],
            self.outputs['mc_para_word07'],
            self.outputs['mc_para_word08'],
            self.outputs['mc_para_word09'],
            self.outputs['cfg_control'],
            self.outputs['cfg_index_out'],
            self.outputs['cfg_value_out'],
            *par_channels
        ) = unpacked_par_data

        # Assign monitoring channels dynamically
        for i, value in enumerate(par_channels, start=1):
            self.outputs[f'par_ch{i}'] = value
    
    def pack_outputs(self):
        """
        Packs the `outputs` dictionary into a binary format.
        """
        # Define the fixed structure for outputs
        base_format = '<HHHHHHHHHHHHHHi'
        par_channel_format = 'H' * self.num_par_ch  # Dynamically add parameter channels
        full_format = base_format + par_channel_format

        # Prepare data for packing
        data_to_pack = [
            self.outputs['control_word'],
            self.outputs['mc_header'],
            self.outputs['mc_para_word00'],
            self.outputs['mc_para_word01'],
            self.outputs['mc_para_word02'],
            self.outputs['mc_para_word03'],
            self.outputs['mc_para_word04'],
            self.outputs['mc_para_word05'],
            self.outputs['mc_para_word06'],
            self.outputs['mc_para_word07'],
            self.outputs['mc_para_word08'],
            self.outputs['mc_para_word09'],
            self.outputs['cfg_control'],
            self.outputs['cfg_index_out'],
            self.outputs['cfg_value_out'],
        ]

        # Add parameter channels dynamically
        for i in range(1, self.num_par_ch + 1):
            data_to_pack.append(self.outputs[f'par_ch{i}'])

        # Pack the data
        return struct.pack(full_format, *data_to_pack)

    def __str__(self):
        return (f"Operation_Enabled: {self.status['operation_enabled']}, "
                f"SwitchOn_Locked: {self.status['switch_on_locked']}, "
                f"Homed: {self.status['homed']}, "
                f"Motion_Active: {self.status['motion_active']}, "
                f"Jogging: {self.status['jogging']}, "
                f"Warning: {self.status['warning']}, "
                f"Error: {self.status['error']}, "
                f"Error_Code: {self.status['error_code']}, "
                f"Demand_Position: {self.status['demand_position']}, "
                f"Actual_Position: {self.status['actual_position']}, "
                f"Difference_Position: {self.status['difference_position']}, "
                f"Actual_Current: {self.status['actual_current']}, "
                f"Measured_Force: {self.status['measured_force']}, "
                f"Analog_Diff_Voltage: {self.status['analog_diff_voltage']}, "
                f"Analog_Voltage: {self.status['analog_voltage']}, "
                f"MonCh1: {self.inputs['mon_ch1']}, "
                f"MonCh2: {self.inputs['mon_ch2']}, "
                f"MonCh3: {self.inputs['mon_ch3']}, "
                f"MonCh4: {self.inputs['mon_ch4']} "
                )


    def __getstate__(self):
        """Make the class picklable by returning a serializable state dictionary."""
        return self.__dict__.copy()  # Shallow copy of the instance's dictionary

    def __setstate__(self, state):
        """Restore the state from a pickled dictionary."""
        self.__dict__.update(state)  # Restore state
