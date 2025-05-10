########################################################################
# What the script does:
# 1. It reads a CSV file containing force curve data.
# 2. It applies an Exponential Moving Average (EMA) filter to the data.
# 3. It detects the maximum holding force from the estimated analog force data.
# 4. It plots the filtered data and the maximum holding force.
########################################################################

import pandas as pd
import matplotlib.pyplot as plt
import os
import numpy as np
from scipy.signal import find_peaks
import re

# Constants
CSV_FILE = "./data_max_holding_force/120V-activated-0.2-flip-0-2.csv"
TITLE = CSV_FILE.split("/")[-1].split(".")[0]
CYCLE_TIME = 0.0015  # seconds
EMA_ALPHA = 0.07011191019798384  # Exponential Moving Average alpha

# reading the CSV file
df = pd.read_csv(os.path.join(os.path.dirname(__file__), CSV_FILE))

# Analog voltage for voltage status
analog_voltage = df["analog_voltage"]

# read time as datetime
time = pd.to_datetime(df["Timestamp"], format="ISO8601")
start_time = time[0]
plot_idx = time < start_time + pd.Timedelta(seconds=30)

# apply EMA to estimated_analog_force
estimated_analog_force_ema_filtered = df["estimated_analog_force"].ewm(alpha=EMA_ALPHA, adjust=False).mean()

def detect_max_holding_force(force_ema, distance=100, prominence=0.05):
    """
    Detect the maximum holding force using `find_peaks` with stricter conditions.
    Parameters:
        force_ema: EMA-filtered force data (pd.Series)
        distance: Minimum number of samples between peaks
        prominence: Minimum prominence of peaks to be considered
    Returns:
        max_holding_force: Value of max force
        peak_idx: Index of the detected peak
    """
    # Set the height to a percentage of the maximum value
    height = 0.7 * force_ema.max()  # Set height to 10% of the maximum value

    # Detect local maxima (peaks)
    peaks, properties = find_peaks(force_ema, distance=distance, prominence=prominence, height=height)

    # print properties
    print(properties)

    if len(peaks) == 0:
        return None  # No peaks detected

    # get the first 2 peaks
    if len(peaks) > 2:
        peaks = peaks[:2]
    else:
        peaks = peaks
        max_holding_force = force_ema.iloc[peaks].max()
        return max_holding_force, peaks
    
    # Get the maximum value among the first 2 peaks
    #max_holding_force = force_ema.iloc[peaks].max()
    if force_ema.iloc[peaks[0]] < force_ema.iloc[peaks[1]]:
        max_holding_force = force_ema.iloc[peaks[1]]
        peak_idx = peaks[1]
    else:
        max_holding_force = force_ema.iloc[peaks[0]]
        peak_idx = peaks[0]
    
    return max_holding_force, peak_idx


def extract_parameters(filename):
    match = re.match(r"(\d+)V-activated-([\d.]+)-flip-([\d.]+)-([\d.]+)\.csv", filename)
    if match:
        voltage = float(match.group(1))
        activated_time = float(match.group(2))
        flipping = float(match.group(3))
        return voltage, activated_time, flipping
    return None, None, None

# Detect the maximum holding force
max_holding_force, peak_idx = detect_max_holding_force(estimated_analog_force_ema_filtered)
print(f"Max holding force: {max_holding_force}")

# Plotting the measured force
plt.figure(figsize=(10, 5))
plt.plot(time[plot_idx], estimated_analog_force_ema_filtered[plot_idx], label=f"Force EMA_alpha={EMA_ALPHA}", color='blue')
plt.plot(time[plot_idx], df["analog_voltage"][plot_idx], label="Analog Voltage[V]", color='red')
plt.axvline(x=time[plot_idx][peak_idx], color='orange', linestyle='--', label="Peak Force")
plt.xlabel("Time (s)")
plt.ylabel("Measured Force[N]")
plt.title(f"{TITLE} - Max force: {max_holding_force:.2f}N")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
