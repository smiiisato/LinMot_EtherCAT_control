########################################################################
# What the script does:
# 1. It reads a CSV file containing force curve data.
# 2. It applies an Exponential Moving Average (EMA) filter to the data.
# 3. It detects the engage time of the force curve.
# 4. It plots the filtered data and the engage time.
########################################################################

import pandas as pd
import matplotlib.pyplot as plt
import os
import numpy as np

# Constants
CSV_FILE = "./data_engage_time/engage-120V-flip-0-speed-100-0.csv"  # Path to the CSV file
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
plot_idx = time < start_time + pd.Timedelta(seconds=1.5)

# apply EMA to estimated_analog_force
estimated_analog_force_ema_filtered = df["estimated_analog_force"].ewm(alpha=EMA_ALPHA, adjust=False).mean()

def detect_engage_time(force_data, threshold=1.0):
    # Find the peak force
    peak_idx = np.argmax(force_data)
    # list of indices where the force drops below the threshold
    engage_idx = np.where((force_data > threshold))[0][0] if len(np.where((force_data > threshold))[0]) > 0 else None

    peak_force = force_data[peak_idx]

    return engage_idx, peak_force

# Detect release time
engage_idx, peak_force = detect_engage_time(estimated_analog_force_ema_filtered)
engage_time = time[engage_idx] - start_time
print(f"peak force: {peak_force}")

# Convert engage time to seconds
engage_time_seconds = engage_time.total_seconds()
print(f"Engage time: {engage_time_seconds:.6f} seconds")

# Plotting the measured force
plt.figure(figsize=(10, 5))
plt.plot(time[plot_idx], estimated_analog_force_ema_filtered[plot_idx], label=f"Force EMA_alpha={EMA_ALPHA}", color='blue')
plt.plot(time[plot_idx], df["analog_voltage"][plot_idx], label="Analog Voltage[V]", color='red')
plt.axhline(y=0.1, color='green', linestyle='--', label="Release Threshold")
plt.axvline(x=time[plot_idx][engage_idx], color='orange', linestyle='--', label="Engage Time")
#lt.axvline(x=off_triger_time, color='purple', linestyle='--', label="Off Trigger Time")
plt.xlabel("Time (s)")
plt.ylabel("Measured Force[N]")
plt.title(f"{TITLE} - Engage Time: {engage_time_seconds:.2f}s")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
