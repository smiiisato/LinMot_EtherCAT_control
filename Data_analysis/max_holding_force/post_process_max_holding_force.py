import pandas as pd
import numpy as np
import os
import re
from scipy.signal import find_peaks

########### CHANGE HERE ###########
INPUT_DIR = "./Data_analysis/data_max_holding_force"  # Directory containing CSV files
OUTPUT_FILE = "./Data_analysis/max_holding_force_summary.csv"
####################################

# Constants
CYCLE_TIME = 0.0015  # seconds
EMA_ALPHA = 0.07011191019798384  # Exponential Moving Average alpha

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
    #print(properties)

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

# List all CSV files in the directory
results = []

for fname in os.listdir(INPUT_DIR):
    if fname.endswith(".csv"):
        voltage, activated_time, flip = extract_parameters(fname)
        if None in (voltage, activated_time, flip):
            print(f"Skipped: {fname} (Invalid filename format)")
            continue

        filepath = os.path.join(INPUT_DIR, fname)
        try:
            df = pd.read_csv(filepath)
            analog_voltage = df["analog_voltage"]
            force_ema = df["estimated_analog_force"].ewm(alpha=EMA_ALPHA, adjust=False).mean()
            time = pd.to_datetime(df["Timestamp"], format="ISO8601")

            max_holding_force, peak_idx = detect_max_holding_force(force_ema)
            if max_holding_force is None:
                print(f"Max holding force not detected in {fname}")

            results.append({
                "Voltage[V]": voltage,
                "Activated time[s]": activated_time,
                "Flipping period[s]": flip,
                "Max holding force[N]": max_holding_force,
            })
        except Exception as e:
            print(f"Error processing {fname}: {e}")

# Save results to CSV
results_df = pd.DataFrame(results)
results_df = results_df.sort_values(
    by=["Voltage[V]", "Activated time[s]", "Flipping period[s]"],
)
results_df.to_csv(OUTPUT_FILE, index=False)
print(f"Summary saved to {OUTPUT_FILE}")
