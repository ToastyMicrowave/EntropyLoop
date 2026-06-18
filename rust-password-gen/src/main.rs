//! Quantum password generator — desktop GUI.
//!
//! Reads the Entropy Loop's USB-serial output, pulls the hardware-random bytes
//! out of each batch, and stretches them with SHA-512 into a password. The
//! serial read runs on a background thread so the window stays responsive.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod app;
mod core;

use app::App;

fn main() -> eframe::Result<()> {
    let native_options = eframe::NativeOptions {
        viewport: eframe::egui::ViewportBuilder::default()
            .with_inner_size([540.0, 660.0])
            .with_min_inner_size([480.0, 580.0])
            .with_title("Quantum Password Generator"),
        ..Default::default()
    };

    eframe::run_native(
        "Quantum Password Generator",
        native_options,
        Box::new(|_cc| Ok(Box::new(App::new()))),
    )
}
