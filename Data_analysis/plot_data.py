import pandas as pd
import matplotlib.pyplot as plt
import os

# Constants
CSV_FILE = "data_release_time/ReleaseTime_0.08kV_flip_0.05_alpha_0_0.csv"  # Path to the CSV file
TITLE = CSV_FILE.split("/")[-1].split(".")[0]
CYCLE_TIME = 0.0015  # seconds
EMA_ALPHA = 0.07011191019798384  # Exponential Moving Average alpha
TARGET = "measured_force"  # The target column to plot
#TARGET = "actual_position"  # The target column to plot
#TARGET = "analog_diff_voltage"  # The target column to plot

# reading the CSV file
df = pd.read_csv(
                os.path.join(os.path.dirname(__file__), CSV_FILE),
                parse_dates=["Time(s)"],)

# Check if the DataFrame is empty
#time = [i * CYCLE_TIME for i in range(len(df))]

# read time as datetime
time = df["Time(s)"]
print(time)
start_time = time[0]
plot_idx = time < start_time + pd.Timedelta(seconds=5.0)

# apply EMA to estimated_analog_force
force_ema_filtered = df["Force(N)"].ewm(alpha=EMA_ALPHA, adjust=False).mean()
print(force_ema_filtered[plot_idx].max())


# Plotting the measured force
plt.figure(figsize=(10, 5))
if TARGET == "actual_position":
    plt.plot(time, df["actual_position"], label="Actual Position[mm]", color='green')
    plt.xlabel("Time (s)")
    plt.ylabel("Actual Position[mm]")
    plt.title("Actual Position Over Time")
elif TARGET == "measured_force":
    #plt.plot(time, df["estimated_analog_force"], label="Estimated Analog Force[N]", color='red')
    plt.plot(time[plot_idx], force_ema_filtered[plot_idx], label=f"Force EMA_alpha={EMA_ALPHA}", color='blue')
    plt.plot(time[plot_idx], df["Engage_flag"][plot_idx], label="Analog Voltage[V]", color='red')
    #plt.drawhline(y=0, color='red', linestyle='--')
    #plt.plot(time, df["measured_force"], label="Measured Force[N]", color='blue')
    plt.xlabel("Time (s)")
    plt.ylabel("Measured Force[N]")
    #plt.title("Measured Force Over Time")
    plt.title(TITLE)
elif TARGET == "analog_diff_voltage":
    plt.plot(time, df["analog_diff_voltage"], label="Analog Diff Voltage[V]", color='red')
    #plt.plot(time, df["analog_diff_voltage_filtered"], label="Analog Diff Voltage Filtered[V]", color='blue')
    plt.xlabel("Time (s)")
    plt.ylabel("Analog Diff Voltage[V]")
    plt.title("Analog Diff Voltage Over Time")

plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
