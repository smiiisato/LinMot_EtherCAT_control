import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

########## CHANGE HERE ###########
CSV_FILE = "./Data_analysis/release_time_summary.csv"  # Path to the CSV file4
##################################


# Load the CSV file
df = pd.read_csv(CSV_FILE)

# Check if the DataFrame is empty
df = df.dropna(subset=["Release time[s]"])

# Define the column to group by
group_by_var = "Flipping period[s]"

# Define the fixed conditions
fixed_conditions = {
    "Decaying flipping period[s]": 0,
    "Decaying duration[s]": 0,
    "Decaying alpha": 0,
}

# filter the DataFrame based on fixed conditions
for col, val in fixed_conditions.items():
    df = df[df[col] == val]

# Group by the specified variable and calculate mean and SEM
grouped = df.groupby(["Decaying alpha", "Flipping period[s]", "Voltage[V]"])["Release time[s]"].agg(['mean', 'sem']).reset_index()

alpha_values = sorted(grouped["Decaying alpha"].unique())
num_alphas = len(alpha_values)

# Plotting
fig, axes = plt.subplots(nrows=1, ncols=num_alphas, figsize=(5 * num_alphas, 5), sharey=True)

if num_alphas == 1:
    axes = [axes]  # in case of a single subplot, ensure axes is iterable

for ax, alpha in zip(axes, alpha_values):
    alpha_group = grouped[grouped["Decaying alpha"] == alpha]

    # Plotting the data
    for flipping_period, group in alpha_group.groupby("Flipping period[s]"):
        ax.errorbar(
            group["Voltage[V]"],
            group["mean"],
            yerr=group["sem"],
            marker='o',
            linestyle='-',
            label=f'Flipping = {flipping_period}s'
        )

    ax.set_title(f"Decaying Alpha = {alpha}")
    ax.set_xlabel("Voltage [V]")
    ax.grid(True)
    ax.legend()

axes[0].set_ylabel("Release time [s]")

plt.tight_layout()
plt.show()