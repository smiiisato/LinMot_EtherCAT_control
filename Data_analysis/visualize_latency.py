import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("latency_log.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"])

plt.figure(figsize=(12, 6))
plt.plot(df["timestamp"], df["latency"], label="Comm Latency")
""" plt.plot(df["timestamp"], df["comm_latency"], label="Comm Latency")
plt.plot(df["timestamp"], df["data_lock_latency"], label="Data Lock Latency")
plt.plot(df["timestamp"], df["update_latency"], label="Update Latency")
plt.plot(df["timestamp"], df["cycle_time"], label="Total Cycle Time") """
plt.xlabel("Time")
plt.ylabel("Seconds")
plt.legend()
plt.title("EtherCAT Communication Latency Over Time")
plt.grid(True)
plt.tight_layout()
plt.show()
