//! egui front-end for the quantum password generator.
//!
//! The serial read blocks until a good batch of entropy arrives, so it runs on
//! a background thread and reports back to the UI over a channel. The UI thread
//! stays responsive the whole time.

use std::io::BufReader;
use std::sync::mpsc::{channel, Receiver};
use std::thread;
use std::time::Duration;

use eframe::egui;

use crate::core::{
    generate_password, list_ports, next_entropy, Batch, DEFAULT_BAUD, DEFAULT_PORT, DIGITS, LOWER,
    SYMBOLS, UPPER,
};

/// Messages sent from the worker thread back to the UI.
enum Job {
    Status(String),
    Done { batch: Batch, password: String },
    Error(String),
}

pub struct App {
    // Connection settings.
    port: String,
    ports: Vec<String>,
    baud: u32,
    min_hmin: f64,

    // Password settings.
    len: usize,
    use_upper: bool,
    use_lower: bool,
    use_digits: bool,
    use_symbols: bool,

    // Results / live state.
    password: String,
    status: String,
    last_h_min: Option<f64>,
    last_r: Option<i32>,
    error: Option<String>,
    working: bool,
    rx: Option<Receiver<Job>>,
    copied_flash: f32,
}

impl App {
    pub fn new() -> Self {
        let ports = list_ports();
        // Prefer a Pico-looking port if one is plugged in.
        let port = ports
            .iter()
            .find(|p| p.contains("usbmodem") || p.contains("usbserial") || p.contains("ACM"))
            .cloned()
            .unwrap_or_else(|| DEFAULT_PORT.to_string());

        Self {
            port,
            ports,
            baud: DEFAULT_BAUD,
            min_hmin: 6.0,
            len: 24,
            use_upper: true,
            use_lower: true,
            use_digits: true,
            use_symbols: true,
            password: String::new(),
            status: "Ready.".to_string(),
            last_h_min: None,
            last_r: None,
            error: None,
            working: false,
            rx: None,
            copied_flash: 0.0,
        }
    }

    /// Assemble the charset from the toggled categories.
    fn charset(&self) -> Vec<u8> {
        let mut cs = Vec::new();
        if self.use_upper {
            cs.extend_from_slice(UPPER);
        }
        if self.use_lower {
            cs.extend_from_slice(LOWER);
        }
        if self.use_digits {
            cs.extend_from_slice(DIGITS);
        }
        if self.use_symbols {
            cs.extend_from_slice(SYMBOLS);
        }
        cs
    }

    /// Shannon entropy of the password assuming a uniform draw over the charset.
    fn strength_bits(&self) -> f64 {
        let n = self.charset().len();
        if n < 2 {
            return 0.0;
        }
        self.len as f64 * (n as f64).log2()
    }

    /// Kick off a background entropy read + password generation.
    fn start(&mut self, ctx: &egui::Context) {
        let charset = self.charset();
        if charset.is_empty() {
            self.error = Some("Select at least one character set.".to_string());
            return;
        }

        self.working = true;
        self.error = None;
        self.password.clear();
        self.status = "Opening serial port…".to_string();

        let (tx, rx) = channel();
        self.rx = Some(rx);

        let ctx = ctx.clone();
        let port = self.port.clone();
        let baud = self.baud;
        let len = self.len;
        let min_hmin = self.min_hmin;

        thread::spawn(move || {
            let send = |msg: Job| {
                let _ = tx.send(msg);
                ctx.request_repaint();
            };

            let sp = match serialport::new(&port, baud)
                .timeout(Duration::from_secs(15))
                .open()
            {
                Ok(sp) => sp,
                Err(e) => {
                    send(Job::Error(format!(
                        "Could not open {port}: {e}\nIs the Entropy Loop plugged in?"
                    )));
                    return;
                }
            };

            send(Job::Status(format!(
                "Waiting for entropy (H_min ≥ {min_hmin})…"
            )));

            let mut reader = BufReader::new(sp);
            match next_entropy(&mut reader, min_hmin) {
                Ok(batch) => {
                    let password = generate_password(&batch.bytes, len, &charset);
                    send(Job::Done { batch, password });
                }
                Err(e) => send(Job::Error(format!("Serial read failed: {e}"))),
            }
        });
    }

    /// Drain any messages the worker has produced.
    fn poll_worker(&mut self) {
        let Some(rx) = self.rx.take() else { return };
        let mut keep = true;
        loop {
            match rx.try_recv() {
                Ok(Job::Status(s)) => self.status = s,
                Ok(Job::Done { batch, password }) => {
                    self.password = password;
                    self.last_h_min = Some(batch.h_min);
                    self.last_r = Some(batch.r);
                    self.status = "Done — generated from a fresh quantum batch.".to_string();
                    self.working = false;
                    keep = false;
                }
                Ok(Job::Error(e)) => {
                    self.error = Some(e);
                    self.status = "Failed.".to_string();
                    self.working = false;
                    keep = false;
                }
                Err(_) => break,
            }
        }
        if keep {
            self.rx = Some(rx);
        }
    }
}

impl Default for App {
    fn default() -> Self {
        Self::new()
    }
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        self.poll_worker();
        if self.copied_flash > 0.0 {
            self.copied_flash = (self.copied_flash - ctx.input(|i| i.stable_dt)).max(0.0);
            ctx.request_repaint();
        }

        egui::CentralPanel::default().show_inside(ui, |ui| {
            ui.add_space(4.0);
            ui.vertical_centered(|ui| {
                ui.heading("⚛  Quantum Password Generator");
                ui.label(
                    egui::RichText::new("Entropy sourced live from the Entropy Loop hardware RNG")
                        .small()
                        .weak(),
                );
            });
            ui.add_space(8.0);
            ui.separator();
            ui.add_space(8.0);

            // ----- Connection -----
            ui.group(|ui| {
                ui.label(egui::RichText::new("Hardware").strong());
                ui.add_space(4.0);

                ui.horizontal(|ui| {
                    ui.label("Serial port:");
                    let ports = self.ports.clone();
                    egui::ComboBox::from_id_salt("port")
                        .selected_text(if self.port.is_empty() {
                            "<none>".to_string()
                        } else {
                            self.port.clone()
                        })
                        .show_ui(ui, |ui| {
                            for p in &ports {
                                ui.selectable_value(&mut self.port, p.clone(), p);
                            }
                        });
                    if ui.button("⟳ Refresh").clicked() {
                        self.ports = list_ports();
                    }
                });

                ui.horizontal(|ui| {
                    ui.label("Baud:");
                    ui.add(egui::DragValue::new(&mut self.baud).range(1200..=2_000_000));
                    ui.add_space(12.0);
                    ui.label("Min H_min:");
                    ui.add(
                        egui::DragValue::new(&mut self.min_hmin)
                            .speed(0.1)
                            .range(0.0..=8.0),
                    );
                });
            });

            ui.add_space(8.0);

            // ----- Password options -----
            ui.group(|ui| {
                ui.label(egui::RichText::new("Password").strong());
                ui.add_space(4.0);

                ui.horizontal(|ui| {
                    ui.label("Length:");
                    ui.add(egui::Slider::new(&mut self.len, 4..=128).text("chars"));
                });

                ui.horizontal_wrapped(|ui| {
                    ui.checkbox(&mut self.use_upper, "A–Z");
                    ui.checkbox(&mut self.use_lower, "a–z");
                    ui.checkbox(&mut self.use_digits, "0–9");
                    ui.checkbox(&mut self.use_symbols, "!@#$…");
                });

                let bits = self.strength_bits();
                let (label, color) = match bits {
                    b if b < 60.0 => ("weak", egui::Color32::from_rgb(220, 80, 80)),
                    b if b < 100.0 => ("fair", egui::Color32::from_rgb(220, 180, 70)),
                    b if b < 150.0 => ("strong", egui::Color32::from_rgb(90, 200, 120)),
                    _ => ("very strong", egui::Color32::from_rgb(70, 200, 200)),
                };
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new(format!("≈ {bits:.0} bits of entropy")).small(),
                    );
                    ui.label(egui::RichText::new(format!("({label})")).small().color(color));
                });
            });

            ui.add_space(10.0);

            // ----- Generate button -----
            ui.vertical_centered_justified(|ui| {
                let enabled = !self.working && !self.charset().is_empty();
                let btn = egui::Button::new(
                    egui::RichText::new(if self.working {
                        "Generating…"
                    } else {
                        "⚛  Generate Password"
                    })
                    .size(16.0),
                );
                if ui.add_enabled(enabled, btn).clicked() {
                    self.start(&ctx);
                }
            });

            if self.working {
                ui.add_space(6.0);
                ui.horizontal(|ui| {
                    ui.spinner();
                    ui.label(&self.status);
                });
                ctx.request_repaint();
            }

            // ----- Result -----
            if !self.password.is_empty() {
                ui.add_space(10.0);
                ui.group(|ui| {
                    ui.label(egui::RichText::new("Generated password").strong());
                    ui.add_space(4.0);

                    let mut shown = self.password.clone();
                    ui.add(
                        egui::TextEdit::multiline(&mut shown)
                            .font(egui::TextStyle::Monospace)
                            .desired_width(f32::INFINITY)
                            .desired_rows(2)
                            .interactive(false),
                    );

                    ui.add_space(4.0);
                    ui.horizontal(|ui| {
                        if ui.button("📋 Copy").clicked() {
                            ctx.copy_text(self.password.clone());
                            self.copied_flash = 1.5;
                        }
                        if self.copied_flash > 0.0 {
                            ui.label(
                                egui::RichText::new("copied!")
                                    .color(egui::Color32::from_rgb(90, 200, 120)),
                            );
                        }
                        if let (Some(h), Some(r)) = (self.last_h_min, self.last_r) {
                            ui.with_layout(
                                egui::Layout::right_to_left(egui::Align::Center),
                                |ui| {
                                    ui.label(
                                        egui::RichText::new(format!("H_min {h:.3} · R {r}"))
                                            .small()
                                            .weak(),
                                    );
                                },
                            );
                        }
                    });
                });
            }

            // ----- Error -----
            if let Some(err) = &self.error {
                ui.add_space(10.0);
                ui.colored_label(egui::Color32::from_rgb(220, 90, 90), format!("⚠ {err}"));
            }

            // ----- Footer -----
            ui.with_layout(egui::Layout::bottom_up(egui::Align::Center), |ui| {
                ui.add_space(4.0);
                ui.label(egui::RichText::new(self.status.clone()).small().weak());
            });
        });
    }
}
