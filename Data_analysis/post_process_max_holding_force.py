import pandas as pd
import numpy as np
import os
import re
from scipy.signal import find_peaks

########### CHANGE HERE ###########
INPUT_DIR = "./Data_analysis/all_data"  # Directory containing CSV files
OUTPUT_FILE = "./Data_analysis/max_holding_force_summary.csv"
####################################

# Constants
CYCLE_TIME = 0.0015  # seconds
EMA_ALPHA = 0.07011191019798384  # Exponential Moving Average alpha

def detect_max_holding_force(force_ema):
    """
    Detect the maximum holding force from the estimated analog force data.
    This version uses peak detection to handle noise and multiple local maxima.
    """
    # Detect local maxima (peaks)
    peaks, _ = find_peaks(force_ema)

    if len(peaks) == 0:
        return None  # No peaks detected

    # Get the maximum value among all peaks
    max_holding_force = force_ema.iloc[peaks].max()
    
    return max_holding_force


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

            max_holding_force = detect_max_holding_force(force_ema)
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
