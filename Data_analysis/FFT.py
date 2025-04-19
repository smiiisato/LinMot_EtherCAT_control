import pandas as pd
import matplotlib.pyplot as plt
import os
import numpy as np

CSV_FILE = "Oszi_recoding_0/Oszi_recoding.csv"
CYCLE_TIME = 0.003  # seconds
TARGET = "analog_diff_voltage"

# read data
df = pd.read_csv(os.path.join(os.path.dirname(__file__), CSV_FILE))
signal = df[TARGET].values
time = np.arange(len(signal)) * CYCLE_TIME

# --- FFT ---
fs = 1 / CYCLE_TIME  # sampling frequency
freqs = np.fft.rfftfreq(len(signal), d=CYCLE_TIME)
fft_vals = np.abs(np.fft.rfft(signal))

# --- plot FFT spectrum ---
plt.figure(figsize=(10, 4))
plt.plot(freqs, fft_vals)
plt.xlabel("Frequency [Hz]")
plt.ylabel("Amplitude")
plt.title("FFT of Analog Diff Voltage")
plt.grid(True)
plt.tight_layout()
plt.show()

# --- choose cutoff frequency manually from the plot ---
cutoff_freq = 4  # e.g., low-pass at 10 Hz

# --- calculate alpha from cutoff frequency ---
omega_c = 2 * np.pi * cutoff_freq
alpha = (omega_c * CYCLE_TIME) / (1 + omega_c * CYCLE_TIME)
print(f"alpha: {alpha}")

# --- apply EMA filter ---
analog_diff_voltage_ema_filtered = df["analog_diff_voltage"].ewm(alpha=alpha, adjust=False).mean()

# --- plot filtered signal ---
plt.figure(figsize=(10, 5))
plt.plot(time, signal, label="Raw", color='red')
plt.plot(time, analog_diff_voltage_ema_filtered, label=f"EMA (cutoff = {cutoff_freq} Hz)", color='blue')
plt.xlabel("Time (s)")
plt.ylabel("Analog Diff Voltage [V]")
plt.title("Analog Diff Voltage with EMA Filter")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
