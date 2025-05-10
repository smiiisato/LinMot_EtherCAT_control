import pandas as pd
import numpy as np
import os
import re

########### CHANGE HERE ###########
INPUT_DIR = "./Data_analysis/data_release_time"  # Directory containing CSV files
OUTPUT_FILE = "./Data_analysis/release_time_summary.csv"
####################################

# Constants
CYCLE_TIME = 0.0015  # seconds
EMA_ALPHA = 0.07011191019798384  # Exponential Moving Average alpha

def detect_release_time(force_data):
    peak_idx = np.argmax(force_data)
    release_idx = np.where((force_data < 0.1))[0]
    # mask the release index to find the first one after the peak
    masked_release_idx = release_idx[release_idx > peak_idx][0] if len(release_idx[release_idx > peak_idx]) > 0 else None
    peak_force = force_data[peak_idx]
    return masked_release_idx, peak_force

def extract_parameters(filename):
    match = re.match(r"(\d+)V-flip-([\d.]+)-decayflip-([\d.]+)-alpha-([\d.]+)-([\d.]+)\.csv", filename)
    if match:
        voltage = float(match.group(1))
        flipping = float(match.group(2))
        decay_flipping = float(match.group(3))
        alpha = float(match.group(4))
        return voltage, flipping, decay_flipping, alpha
    return None, None, None, None

# List all CSV files in the directory
results = []

for fname in os.listdir(INPUT_DIR):
    if fname.endswith(".csv"):
        voltage, flip, decayflip, alpha = extract_parameters(fname)
        if None in (voltage, flip, decayflip, alpha):
            print(f"Skipped: {fname} (Invalid filename format)")
            continue

        filepath = os.path.join(INPUT_DIR, fname)
        try:
            df = pd.read_csv(filepath)
            analog_voltage = df["analog_voltage"]
            force_ema = df["estimated_analog_force"].ewm(alpha=EMA_ALPHA, adjust=False).mean()
            time = pd.to_datetime(df["Timestamp"], format="ISO8601")
            off_trigger_time = time[analog_voltage < 0.5].iloc[0]

            release_idx, peak_force = detect_release_time(force_ema)
            if release_idx is not None:
                release_time = (time[release_idx] - off_trigger_time).total_seconds()
                if peak_force < 1.0:
                    #release_time = None
                    print(f"Peak force too low in {fname}")
            else:
                release_time = None
                print(f"Release time not detected in {fname}")

            if alpha > 0:
                decay_duration = 0.15
            else:
                decay_duration = 0.0

            results.append({
                "Voltage[V]": voltage,
                "Flipping period[s]": flip,
                "Decaying flipping period[s]": decayflip,
                "Decaying alpha": alpha,
                "Decaying duration[s]": decay_duration,
                "Release time[s]": release_time
            })
        except Exception as e:
            print(f"Error processing {fname}: {e}")

# Save results to CSV
results_df = pd.DataFrame(results)
results_df = results_df.sort_values(
    by=["Voltage[V]", "Flipping period[s]", "Decaying alpha", "Decaying flipping period[s]"]
)
results_df.to_csv(OUTPUT_FILE, index=False)
print(f"Summary saved to {OUTPUT_FILE}")
