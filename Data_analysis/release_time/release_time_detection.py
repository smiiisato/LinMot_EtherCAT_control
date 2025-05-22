########################################################################
# What the script does:
# 1. It reads a CSV file containing force curve data.
# 2. It applies an Exponential Moving Average (EMA) filter to the data.
# 3. It detects the release time of the force curve.
# 4. It plots the filtered data and the release time.
########################################################################

import pandas as pd
import matplotlib.pyplot as plt
import os
import numpy as np

# Constants
CSV_FILE = "data_release_time/ReleaseTime2_0.12kV_flip_0_alpha_0_4.csv"  # Path to the CSV file
TITLE = CSV_FILE.split("/")[-1].split(".")[0]
CYCLE_TIME = 0.0015  # seconds
EMA_ALPHA = 0.07011191019798384  # Exponential Moving Average alpha

# reading the CSV file
df = pd.read_csv(
                os.path.join(os.path.dirname(__file__), CSV_FILE),
                parse_dates=["Time(s)"],)

# Analog voltage for voltage status
analog_voltage = df["Engage_flag"] #df["analog_voltage"]

# read time as datetime
time = df["Time(s)"]
start_time = time[0]
plot_idx = time < start_time + pd.Timedelta(seconds=1.5)

# apply EMA to estimated_analog_force
estimated_analog_force_ema_filtered = df["Force(N)"].ewm(alpha=EMA_ALPHA, adjust=False).mean()

def detect_release_time(force_data, threshold=0.1):
    # Find the peak force
    peak_idx = np.argmax(force_data)
    # list of indices where the force drops below the threshold
    release_idx = np.where((force_data < threshold))[0]

    # mask the release index to find the first one after the peak
    masked_release_idx = release_idx[release_idx > peak_idx][0] if len(release_idx[release_idx > peak_idx]) > 0 else None
    peak_force = force_data[peak_idx]

    return masked_release_idx, peak_force

# Detect off trigger time
# is the trigger time when the analog voltage is below 0.5V
off_triger_time = time[analog_voltage < 0.5].iloc[0]

# Detect release time
release_idx, peak_force = detect_release_time(estimated_analog_force_ema_filtered)
release_time = time[release_idx] - off_triger_time
print(f"peak force: {peak_force}")

# Convert release time to seconds
release_time_seconds = release_time.total_seconds()
print(f"Release time: {release_time_seconds:.6f} seconds")

# Plotting the measured force
plt.figure(figsize=(10, 5))
plt.plot(time[plot_idx], estimated_analog_force_ema_filtered[plot_idx], label=f"Force EMA_alpha={EMA_ALPHA}", color='blue')
plt.plot(time[plot_idx], df["Engage_flag"][plot_idx], label="Analog Voltage[V]", color='red')
plt.axhline(y=0.1, color='green', linestyle='--', label="Release Threshold")
plt.axvline(x=time[plot_idx][release_idx], color='orange', linestyle='--', label="Release Time")
plt.axvline(x=off_triger_time, color='purple', linestyle='--', label="Off Trigger Time")
plt.xlabel("Time (s)")
plt.ylabel("Measured Force[N]")
plt.title(f"{TITLE} - Release Time: {release_time_seconds:.2f}s")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
