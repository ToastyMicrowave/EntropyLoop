import matplotlib.pyplot as plt


def generate_plot(x, raw_data):

    plt.figure(figsize=(14, 6))

    plt.plot(
        x,
        raw_data,
        linewidth=0.5
    )

    plt.title("RAW Entropy Source Output")
    plt.xlabel("Sample Index")
    plt.ylabel("ADC Value")

    plt.grid(True, linestyle="--", alpha=0.6)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":

    from parse_raw import RawParser

    filename = input(
        "Enter filename (e.g. output.txt): "
    )

    parser = RawParser(filename)

    x, raw = parser.get_raw_data()

    if len(raw) == 0:
        print("No RAW data found.")
    else:
        print(f"Loaded {len(raw)} samples.")
        generate_plot(x, raw)