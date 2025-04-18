import pandas as pd
import matplotlib.pyplot as plt
import os

CSV_FILE = "Oszi_recoding_0/Oszi_recoding.csv"
CYCLE_TIME = 0.003  # seconds
EMA_ALPHA = 0.07011191019798384  # Exponential Moving Average alpha
TARGET = "measured_force"  # The target column to plot
#TARGET = "actual_position"  # The target column to plot
#TARGET = "analog_diff_voltage"  # The target column to plot

# reading the CSV file
df = pd.read_csv(os.path.join(os.path.dirname(__file__), CSV_FILE))

# Check if the DataFrame is empty
time = [i * CYCLE_TIME for i in range(len(df))]

# apply EMA to analog_diff_voltage
analog_diff_voltage_ema_filtered = df["analog_diff_voltage"].ewm(alpha=EMA_ALPHA, adjust=False).mean()

# apply EMA to estimated_analog_force
estimated_analog_force_ema_filtered = df["estimated_analog_force"].ewm(alpha=EMA_ALPHA, adjust=False).mean()

# Plotting the measured force
plt.figure(figsize=(10, 5))
if TARGET == "actual_position":
    plt.plot(time, df["actual_position"], label="Actual Position[mm]", color='green')
    plt.xlabel("Time (s)")
    plt.ylabel("Actual Position[mm]")
    plt.title("Actual Position Over Time")
elif TARGET == "measured_force":
    #plt.plot(time, df["estimated_analog_force"], label="Estimated Analog Force[N]", color='red')
    plt.plot(time, estimated_analog_force_ema_filtered, label=f"EMA_alpha={EMA_ALPHA}", color='blue')
    #plt.plot(time, df["measured_force"], label="Measured Force[N]", color='blue')
    plt.xlabel("Time (s)")
    plt.ylabel("Measured Force[N]")
    plt.title("Measured Force Over Time")
elif TARGET == "analog_diff_voltage":
    plt.plot(time, df["analog_diff_voltage"], label="Analog Diff Voltage[V]", color='red')
    plt.plot(time, analog_diff_voltage_ema_filtered, label=f"EMA_alpha={EMA_ALPHA}", color='blue')
    #plt.plot(time, df["analog_diff_voltage_filtered"], label="Analog Diff Voltage Filtered[V]", color='blue')
    plt.xlabel("Time (s)")
    plt.ylabel("Analog Diff Voltage[V]")
    plt.title("Analog Diff Voltage Over Time")

plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
