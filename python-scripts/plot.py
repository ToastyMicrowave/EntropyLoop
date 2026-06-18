import matplotlib.pyplot as plt


def generate_plot(x, h_min_data, r_data, rand_data):
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    
    # Graph 1: Min-Entropy
    ax1.plot(x, h_min_data, color='#1f77b4', linewidth=1)
    ax1.set_title('Entropy Source Metrics Analysis')
    ax1.set_ylabel('H_min')
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    # Graph 2: R Value (Dynamic Range)
    ax2.plot(x, r_data, color='#d62728', linewidth=1)
    ax2.set_ylabel('R Value')
    ax2.grid(True, linestyle='--', alpha=0.6)
    
    # Graph 3: Normalized Random Data
    ax3.plot(x, rand_data, color='#2ca02c', linewidth=0.5)
    ax3.set_ylabel('Data (Normalized 0-1)')
    ax3.set_xlabel('Sample Index')
    ax3.grid(True, linestyle='--', alpha=0.6)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    from parse import Parser # Import Parser here to avoid circular dependency if parse.py imports plot.py
    
    # Prompt user for filename
    input_filename = input("Enter the filename to plot (e.g., output.txt): ")
    
    p = Parser(filename=input_filename)
    x, h, r, rand = p.get_all_data()
    
    if x:
        generate_plot(x, h, r, rand)
    else:
        print(f"No data found in {input_filename}. Ensure the file exists and contains valid QRNG output.")
