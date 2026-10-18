# AI Traffic Signal System — Wokwi Project

This is a Wokwi-ready ESP32 Arduino simulation for a four-way traffic signal with 12 individual LEDs (Red, Yellow, Green for North, East, South, and West). It includes a web API and an automatic timed cycle.

## Live Wokwi Simulator

[![Open in Wokwi](https://img.shields.io/badge/Run%20Simulation-Wokwi-00A6A6?logo=wokwi&logoColor=white)](https://wokwi.com/projects/478226018620545025)

**[▶ Open the ESP32 Traffic Signal Simulator on Wokwi](https://wokwi.com/projects/478226018620545025)**

Use the online simulator to demonstrate the four-way traffic signal sequence (North, East, South, and West) without physical hardware. The project uses 12 LEDs, with red, yellow, and green indicators for each direction.

> **Note:** This link opens the shared Wokwi project. To load the exact firmware and wiring documented here, make sure its `sketch.ino` and `diagram.json` match the files in this repository.

## Project files
- `sketch.ino` — ESP32 firmware (Wokwi-GUEST Wi-Fi, automatic cycle, web server endpoints).
- `diagram.json` — ESP32, 12 LEDs, 12 current-limiting resistors, and all connections.

## Open it in your existing Wokwi project
1. Open https://wokwi.com/projects/478226018620545025.
2. Open the `sketch.ino` tab, select all, and replace it with the supplied `sketch.ino`.
3. Open the `diagram.json` tab, select all, and replace it with the supplied `diagram.json`.
4. Start the simulation and open the Serial Monitor.

If you prefer not to replace the existing wiring, save a copy of your Wokwi project before replacing `diagram.json`.

## Pin mapping
| Direction | Red GPIO | Yellow GPIO | Green GPIO |
|---|---:|---:|---:|
| North | 13 | 12 | 14 |
| East | 27 | 26 | 25 |
| South | 33 | 32 | 23 |
| West | 19 | 18 | 5 |

Each LED is wired GPIO -> 1 kΩ resistor -> LED anode (A), with the LED cathode (C) connected to ESP32 GND.

## Automatic timing
- Green: 8 seconds
- Yellow: 2 seconds
- All-red safety interval between directions: 1 second

## HTTP endpoints
- `/` — dashboard with manual controls
- `/status` — direction, phase, remaining time, mode
- `/ping` and `/verify` — connection check
- `/yellow?direction=NORTH` — change selected direction to yellow
- `/set?direction=NORTH&seconds=8` — selected direction green for a specified duration (1–300 seconds)
- `/stop` — stop automatic cycling and set all lights red
- `/auto` — resume automatic cycling

## Wi-Fi / IoT notes
The simulation uses Wokwi's public `Wokwi-GUEST` access point, which requires no password. Wokwi's public IoT gateway supports outbound connections but does not accept incoming connections to a simulated ESP32 web server. Accessing this server from a browser or local Python controller may require Wokwi's Private IoT Gateway. The LED automatic cycle works without Wi-Fi.

This is a simulator demonstration, not a certified real-world traffic controller.
