//! Core logic shared by the GUI: reading the Entropy Loop's serial output and
//! turning hardware-random bytes into passwords.
//!
//! Serial format (one batch), matching the firmware / capture.py:
//!
//!     H_min: 8.0000 | R: 4085 | Data:
//!     <hex>   <- hash of raw samples: the usable randomness
//!     <hex>   <- hash of that hash:   derived, ignored

use std::io::BufRead;

use sha2::{Digest, Sha512};

// ---------------------------------------------------------------------------
// CONFIG
// ---------------------------------------------------------------------------
pub const DEFAULT_PORT: &str = "/dev/tty.usbmodem3101";
pub const DEFAULT_BAUD: u32 = 115_200;

// Building blocks for the password charset. The GUI lets the user toggle these.
pub const UPPER: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ";
pub const LOWER: &[u8] = b"abcdefghijklmnopqrstuvwxyz";
pub const DIGITS: &[u8] = b"0123456789";
pub const SYMBOLS: &[u8] = b"!@#$%^&*()-_=+";

/// One good batch of entropy pulled off the serial port.
pub struct Batch {
    pub bytes: Vec<u8>,
    pub h_min: f64,
    pub r: i32,
}

// ---------------------------------------------------------------------------
// SERIAL PARSING
// ---------------------------------------------------------------------------

/// Parse "H_min: 8.0000 | R: 4085 | Data:" -> (h_min, r). None if it doesn't match.
fn parse_header(line: &str) -> Option<(f64, i32)> {
    let mut parts = line.split('|');
    let h_min = parts.next()?.split(':').nth(1)?.trim().parse().ok()?;
    let r = parts.next()?.split(':').nth(1)?.trim().parse().ok()?;
    Some((h_min, r))
}

fn is_hex_line(line: &str) -> bool {
    line.len() >= 64 && line.bytes().all(|c| c.is_ascii_hexdigit())
}

fn hex_to_bytes(hex: &str) -> Vec<u8> {
    (0..hex.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
        .collect()
}

/// Block until one good batch arrives, returning its raw random bytes + metrics.
pub fn next_entropy<R: BufRead>(reader: &mut R, min_hmin: f64) -> std::io::Result<Batch> {
    let mut header: Option<(f64, i32)> = None;
    let mut line = String::new();
    loop {
        line.clear();
        if reader.read_line(&mut line)? == 0 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::UnexpectedEof,
                "serial port closed",
            ));
        }
        let raw = line.trim();
        if raw.is_empty() {
            continue;
        }

        if raw.starts_with("H_min") {
            header = parse_header(raw);
            continue;
        }

        // A hex line only counts if it directly followed a valid header.
        if let Some((h_min, r)) = header {
            if is_hex_line(raw) {
                header = None; // ignore the firmware's second (derived) hash line
                if r >= 200 && h_min >= min_hmin {
                    return Ok(Batch {
                        bytes: hex_to_bytes(&raw.to_lowercase()),
                        h_min,
                        r,
                    });
                }
            }
        }
    }
}

/// List the serial ports currently visible to the OS.
pub fn list_ports() -> Vec<String> {
    serialport::available_ports()
        .map(|ports| ports.into_iter().map(|p| p.port_name).collect())
        .unwrap_or_default()
}

// ---------------------------------------------------------------------------
// PASSWORD GENERATION
// ---------------------------------------------------------------------------

/// Turn raw entropy into a password by stretching it with SHA-512 and mapping
/// each output byte onto the charset. Re-hashes if the seed runs short.
pub fn generate_password(seed: &[u8], len: usize, charset: &[u8]) -> String {
    if charset.is_empty() || len == 0 {
        return String::new();
    }
    let mut out = String::with_capacity(len);
    let mut counter: u64 = 0;
    while out.len() < len {
        let mut hasher = Sha512::new();
        hasher.update(seed);
        hasher.update(counter.to_le_bytes());
        let block = hasher.finalize();
        for &b in block.iter() {
            if out.len() >= len {
                break;
            }
            out.push(charset[b as usize % charset.len()] as char);
        }
        counter += 1;
    }
    out
}
