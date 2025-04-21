import pysoem
import tkinter as tk
from tkinter import messagebox
import sys  # Import sys for exiting

def adapter_list():
    return pysoem.find_adapters()

def on_select():
    global selected_adapter_details
    if selected_adapter.get():
        selected_name = selected_adapter.get()
        selected_desc = adapter_dict[selected_name]
        selected_adapter_details = (selected_name, selected_desc)
        root.destroy()  # Close the window

def on_cancel():
    global selected_adapter_details
    selected_adapter_details = None
    root.destroy()  # Close the window

def create_window(adapters):
    global root, selected_adapter, adapter_dict
    root = tk.Tk()
    root.title("EtherCAT Master")

    selected_adapter = tk.StringVar(value=None)
    adapter_dict = {adapter.name: adapter.desc.decode('utf-8') for adapter in adapters}

    # Adapter selection frame
    frame = tk.Frame(root, bd=2, relief="solid")
    frame.pack(padx=10, pady=10, fill="both", expand=True)

    # Instruction label
    instruction_label = tk.Label(frame, text="Select your EtherCAT Master")
    instruction_label.pack(pady=5)

    for adapter in adapters:
        adapter_name = adapter.name
        adapter_desc = adapter.desc.decode('utf-8')
        radio_button = tk.Radiobutton(frame, text=adapter_desc, variable=selected_adapter, value=adapter_name, anchor="w")
        radio_button.pack(fill="x", padx=5, pady=2)

    # Button frame
    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)

    select_button = tk.Button(button_frame, text="Select", command=on_select)
    select_button.pack(side="left", padx=5)

    cancel_button = tk.Button(button_frame, text="Cancel", command=on_cancel)
    cancel_button.pack(side="right", padx=5)

    root.mainloop()

def main():
    adapters = adapter_list()
    create_window(adapters)
    
    return selected_adapter_details

if __name__ == "__main__":
    selected_adapter_details = main()
    if selected_adapter_details:
        adapter_name, adapter_desc = selected_adapter_details
        print(f"{adapter_name}||{adapter_desc}")  # Output both name and description, separated by || for parsing
    else:
        print("None")
    
    sys.exit(0)  # Ensure the script terminates properly

