class Parser():
    def __init__(self, filename="output.txt"):
        self.file = filename

    def hex_to_dec(self, hex_str):
        # Convert the entire hex string to a normalized float between 0 and 1.
        return int(hex_str, 16) / (16**len(hex_str)) # len(hex_str) will be 128 here
    
    def get_all_data(self):
        """Parses the file and returns indices, h_mins, r_values, and normalized random data."""
        indices, h_mins, r_values, random_nums = [], [], [], []
        
        with open(self.file, "r") as f:
            for line in f:
                if line.startswith("H_min:"):
                    try:
                        # Format: H_min: 5.9320 | R: 1100 | Data: <hex>
                        parts = line.split('|')
                        h = float(parts[0].split(':')[1].strip())
                        r = int(parts[1].split(':')[1].strip())
                        
                        # Extract the last 512 bits (128 hex characters) from the data field
                        d_hex = parts[2].split(':')[1].strip()[-128:] 
                        
                        h_mins.append(h)
                        r_values.append(r)
                        random_nums.append(self.hex_to_dec(d_hex))
                        indices.append(len(indices))
                    except (ValueError, IndexError):
                        continue
        return indices, h_mins, r_values, random_nums
