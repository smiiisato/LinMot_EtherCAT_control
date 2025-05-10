import pandas as pd
import numpy as np
import os
import re

########### CHANGE HERE ###########
INPUT_DIR = "./Data_analysis/data_engage_time"  # Directory containing CSV files
OUTPUT_FILE = "./Data_analysis/engage_time_summary.csv"
####################################

# Constants
CYCLE_TIME = 0.0015  # seconds
EMA_ALPHA = 0.07011191019798384  # Exponential Moving Average alpha

def detect_engage_time(force_data, threshold=1.0):
    # Find the peak force
    peak_idx = np.argmax(force_data)
    # list of indices where the force drops below the threshold
    engage_idx = np.where((force_data > threshold))[0][0] if len(np.where((force_data > threshold))[0]) > 0 else None

    peak_force = force_data[peak_idx]

    return engage_idx, peak_force


def extract_parameters(filename):
    match = re.match(r"engage-(\d+)V-flip-([\d.]+)-speed-([\d.]+)-([\d.]+)\.csv", filename)
    if match:
        voltage = float(match.group(1))
        flipping = float(match.group(2))
        speed = float(match.group(3))
        return voltage, flipping, speed
    return None, None, None

# List all CSV files in the directory
results = []

for fname in os.listdir(INPUT_DIR):
    if fname.endswith(".csv"):
        voltage, flip, speed = extract_parameters(fname)
        if None in (voltage, flip, speed):
            print(f"Skipped: {fname} (Invalid filename format)")
            continue

        filepath = os.path.join(INPUT_DIR, fname)
        try:
            df = pd.read_csv(filepath)
            analog_voltage = df["analog_voltage"]
            force_ema = df["estimated_analog_force"].ewm(alpha=EMA_ALPHA, adjust=False).mean()
            time = pd.to_datetime(df["Timestamp"], format="ISO8601")
            start_time = time[0]

            engage_idx, peak_force = detect_engage_time(force_ema)
            if engage_idx is not None:
                engage_time = (time[engage_idx] - start_time).total_seconds()
                if peak_force < 1.0:
                    #engage_time = None
                    print(f"Peak force too low in {fname}")
            else:
                engage_time = None
                print(f"engage time not detected in {fname}")

            results.append({
                "Voltage[V]": voltage,
                "Flipping period[s]": flip,
                "Speed[mm/min]": speed,
                "Engage time[s]": engage_time
            })
        except Exception as e:
            print(f"Error processing {fname}: {e}")

# Save results to CSV
results_df = pd.DataFrame(results)
results_df = results_df.sort_values(
    by=["Voltage[V]", "Flipping period[s]", "Speed[mm/min]"],
)
results_df.to_csv(OUTPUT_FILE, index=False)
print(f"Summary saved to {OUTPUT_FILE}")
