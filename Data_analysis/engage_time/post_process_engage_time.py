import pandas as pd
import numpy as np
import os
import re

########### CHANGE HERE ###########
INPUT_DIR = "data_engage_time/"  # Directory containing CSV files
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
    match = re.match(r"EngageTime_(\d.+)kV_flip_([\d.]+)_([\d.]+)\.csv", filename)
    if match:
        voltage = float(match.group(1)) * 1000  # Convert kV to V
        flipping = float(match.group(2))
        return voltage, flipping
    return None, None

# List all CSV files in the directory
results = []

for fname in os.listdir(os.path.join(os.path.dirname(__file__), INPUT_DIR)):
    if fname.endswith(".csv"):
        voltage, flip = extract_parameters(fname)
        if None in (voltage, flip):
            print(f"Skipped: {fname} (Invalid filename format)")
            continue

        filepath = os.path.join(INPUT_DIR, fname)
        try:
            #df = pd.read_csv(filepath)
            df = pd.read_csv(
                os.path.join(os.path.dirname(__file__), filepath),
                parse_dates=["Time(s)"],)
            analog_voltage = df["Engage_flag"]  # df["analog_voltage"]
            force_ema = df["Force(N)"].ewm(alpha=EMA_ALPHA, adjust=False).mean()
            time = df["Time(s)"]
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
                "Engage time[s]": engage_time
            })
        except Exception as e:
            print(f"Error processing {fname}: {e}")

# Save results to CSV
results_df = pd.DataFrame(results)
results_df = results_df.sort_values(
    by=["Voltage[V]", "Flipping period[s]"],
)
results_df.to_csv(OUTPUT_FILE, index=False)
print(f"Summary saved to {OUTPUT_FILE}")
