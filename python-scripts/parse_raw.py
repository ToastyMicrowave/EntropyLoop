class RawParser:
    def __init__(self, filename="raw_h0.txt"):
        self.file = filename

    def get_raw_data(self):
        """
        Extract all RAW samples from the file.

        Returns:
            x : sample indices
            y : raw ADC/sample values
        """

        samples = []

        with open(self.file, "r") as f:
            for line in f:
                line = line.strip()

                if not line.startswith("RAW:"):
                    continue

                raw_hex = line[4:].strip()

                # Remove whitespace just in case
                raw_hex = raw_hex.replace(" ", "")

                # Parse every 4 hex characters as a 16-bit value
                for i in range(0, len(raw_hex), 4):
                    chunk = raw_hex[i:i + 4]

                    if len(chunk) != 4:
                        continue

                    try:
                        value = int(chunk, 16)

                        # Convert little-endian if required
                        value = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)

                        samples.append(value)

                    except ValueError:
                        pass

        x = list(range(len(samples)))

        return x, samples