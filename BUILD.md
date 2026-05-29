# Build Instructions

## Wiring
MFRC522:
- SDA -> D10
- SCK -> D13
- MOSI -> D11
- MISO -> D12
- RST -> D9
- VCC -> 3.3V
- GND -> GND

LCD I2C:
- SDA -> A4
- SCL -> A5

## Steps
1. Install MFRC522 and LiquidCrystal_I2C libraries.
2. Upload the sketch.
3. Open Serial Monitor to see tag scans.
4. Modify code to map UID → book/user database.
