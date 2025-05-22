import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

########## CHANGE HERE ###########
CSV_FILE = "./Data_analysis/engage_time_summary.csv"  # Path to the CSV file4
##################################


# Load the CSV file
df = pd.read_csv(CSV_FILE)

# Check if the DataFrame is empty
df = df.dropna(subset=["Engage time[s]"])

# Define the fixed conditions
fixed_conditions = {
    #"Decaying flipping period[s]": 0,
    #"Speed[mm/min]": 100,
    #"Decaying alpha": 0,
}

# filter the DataFrame based on fixed conditions
for col, val in fixed_conditions.items():
    df = df[df[col] == val]

# Group by the specified variable and calculate mean and SEM
grouped = df.groupby(["Voltage[V]", "Flipping period[s]"])["Engage time[s]"].agg(['mean', 'sem']).reset_index()
num_plots = 1

# Plotting
#fig, axes = plt.subplots(nrows=1, ncols=num_alphas, figsize=(5 * num_alphas, 5), sharey=True)
fig, axes = plt.subplots(nrows=1, ncols=num_plots, figsize=(5 * num_plots, 5), sharey=True)

if num_plots == 1:
    axes = [axes]  # in case of a single subplot, ensure axes is iterable

flip_values = sorted(grouped["Flipping period[s]"].unique())

# Loop through each flipping period
for flip in flip_values:
    # Filter the DataFrame for the current voltage
    flip_group = grouped[grouped["Flipping period[s]"] == flip]

    # Plotting the data
    for flipping_period, group in flip_group.groupby("Flipping period[s]"):
        axes[0].errorbar(
            group["Voltage[V]"],
            group["mean"],
            yerr=group["sem"],
            marker='o',
            linestyle='-',
            label=f'Flipping = {flipping_period}s'
        )

axes[0].set_title("Engage time")
axes[0].set_xlabel("Voltage [V]")
axes[0].grid(True)
axes[0].legend()
axes[0].set_ylabel("Engage time [s]")

plt.tight_layout()
plt.show()