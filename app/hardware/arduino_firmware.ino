/*
 * ============================================================================
 *  Mobile Repair Tool  –  Hardware Auto-Detection Firmware
 * ============================================================================
 *  Board:   Arduino Mega 2560 (or compatible)
 *  Baud:    115200
 *  Purpose: Acts as a bridge between the PC-based repair tool and the phone
 *           under test.  It reads voltages, probes bus lines, and returns
 *           identification data over USB-serial.
 *
 *  WIRING GUIDE (adjust pins to your jig)
 *  ─────────────────────────────────────────────────
 *  A0  –  Battery rail sense (voltage divider: 10k / 10k for up to ~8 V)
 *  A1  –  3.3 V rail sense   (direct or 1:1 divider)
 *  A2  –  VDD_CORE sense     (direct, typically 0.6–1.0 V)
 *  A3  –  Boot-ROM ID line   (active-low detect straps)
 *  A4  –  RAM detect line
 *  A5  –  Storage detect line
 *
 *  D2  –  UART TX to phone   (Software Serial)
 *  D3  –  UART RX from phone (Software Serial)
 *  D4  –  USB D+ sense (digital read)
 *  D5  –  USB D- sense (digital read)
 *
 *  Upload this sketch to the board, then run the Python detector.
 * ============================================================================
 */

#include <SoftwareSerial.h>

// ── Pin definitions ────────────────────────────────────────────────────────
#define PIN_BATTERY_RAIL   A0
#define PIN_3V3_RAIL       A1
#define PIN_VDD_CORE       A2
#define PIN_BOOT_ROM       A3
#define PIN_RAM_DETECT     A4
#define PIN_STORAGE_DETECT A5

#define PIN_PHONE_TX       2    // our TX → phone RX
#define PIN_PHONE_RX       3    // our RX ← phone TX
#define PIN_USB_DP         4
#define PIN_USB_DM         5

// ── Constants ──────────────────────────────────────────────────────────────
#define SERIAL_BAUD        115200
#define PHONE_UART_BAUD    115200
#define ADC_REF_VOLTAGE    5.0
#define ADC_RESOLUTION     1023.0

// Voltage divider ratio for the battery rail (R1=R2=10k → ratio 2.0)
#define BATTERY_DIVIDER    2.0
// 3V3 and VDD_CORE are read directly (divider ratio = 1.0)
#define RAIL_3V3_DIVIDER   1.0
#define VDD_CORE_DIVIDER   1.0

// Averaging: number of ADC samples per reading
#define ADC_SAMPLES        16

// ── Software serial for UART handshake with the phone ──────────────────────
SoftwareSerial phoneSerial(PIN_PHONE_RX, PIN_PHONE_TX);

// ── Receive buffer ─────────────────────────────────────────────────────────
#define CMD_BUF_SIZE 64
char cmdBuffer[CMD_BUF_SIZE];
uint8_t cmdIndex = 0;

// ===========================================================================
//  SETUP
// ===========================================================================
void setup() {
    // USB-serial to the PC
    Serial.begin(SERIAL_BAUD);
    while (!Serial) { ; }  // wait for USB enumeration

    // Software serial to the phone
    phoneSerial.begin(PHONE_UART_BAUD);

    // Configure analog pins (input by default, but be explicit)
    pinMode(PIN_BATTERY_RAIL,   INPUT);
    pinMode(PIN_3V3_RAIL,       INPUT);
    pinMode(PIN_VDD_CORE,       INPUT);
    pinMode(PIN_BOOT_ROM,       INPUT);
    pinMode(PIN_RAM_DETECT,     INPUT);
    pinMode(PIN_STORAGE_DETECT, INPUT);

    // Digital pins for USB line sensing
    pinMode(PIN_USB_DP, INPUT);
    pinMode(PIN_USB_DM, INPUT);

    Serial.println("READY");
}

// ===========================================================================
//  MAIN LOOP  –  read a line from USB-serial and dispatch the command
// ===========================================================================
void loop() {
    while (Serial.available()) {
        char c = Serial.read();

        if (c == '\n' || c == '\r') {
            if (cmdIndex > 0) {
                cmdBuffer[cmdIndex] = '\0';   // null-terminate
                dispatchCommand(cmdBuffer);
                cmdIndex = 0;
            }
        } else if (cmdIndex < CMD_BUF_SIZE - 1) {
            cmdBuffer[cmdIndex++] = c;
        }
    }
}

// ===========================================================================
//  COMMAND DISPATCHER
// ===========================================================================
void dispatchCommand(const char* cmd) {
    if (strcmp(cmd, "READ_BOOT_ROM") == 0) {
        cmdReadBootRom();
    }
    else if (strcmp(cmd, "DETECT_RAM") == 0) {
        cmdDetectRam();
    }
    else if (strcmp(cmd, "DETECT_STORAGE") == 0) {
        cmdDetectStorage();
    }
    else if (strcmp(cmd, "READ_POWER_RAILS") == 0) {
        cmdReadPowerRails();
    }
    else if (strcmp(cmd, "UART_HANDSHAKE") == 0) {
        cmdUartHandshake();
    }
    else if (strcmp(cmd, "READ_USB_DESC") == 0) {
        cmdReadUsbDescriptor();
    }
    else if (strcmp(cmd, "READ_SERIAL") == 0) {
        cmdReadSerial();
    }
    else if (strcmp(cmd, "PING") == 0) {
        Serial.println("PONG");
    }
    else {
        Serial.print("ERR:UNKNOWN_CMD:");
        Serial.println(cmd);
    }
}

// ===========================================================================
//  HELPER  –  averaged analog read
// ===========================================================================
float readAnalogAveraged(int pin) {
    unsigned long sum = 0;
    for (int i = 0; i < ADC_SAMPLES; i++) {
        sum += analogRead(pin);
        delayMicroseconds(200);
    }
    float avg = (float)sum / ADC_SAMPLES;
    return (avg / ADC_RESOLUTION) * ADC_REF_VOLTAGE;
}

// ===========================================================================
//  CMD: READ_BOOT_ROM
//  Reads the analog voltage on the boot-ROM strap pin and maps it to a known
//  identifier range.  In a real jig the phone's boot-ROM ID lines are active
//  and produce a characteristic voltage or digital pattern.
// ===========================================================================
void cmdReadBootRom() {
    float voltage = readAnalogAveraged(PIN_BOOT_ROM);

    // Map the measured voltage to a hex-style ID that the PC database uses.
    // Each phone SoC family pulls the strap line to a different level.
    // Ranges here are illustrative – calibrate for your jig.
    char id[32];
    if (voltage < 0.5) {
        snprintf(id, sizeof(id), "NO_DEVICE");
    } else if (voltage < 1.0) {
        // Apple A-series range
        int raw = analogRead(PIN_BOOT_ROM);
        snprintf(id, sizeof(id), "APPLE_ROM_0x%04X", raw);
    } else if (voltage < 2.0) {
        // Qualcomm PBL range
        int raw = analogRead(PIN_BOOT_ROM);
        snprintf(id, sizeof(id), "QCOM_PBL_0x%04X", raw);
    } else if (voltage < 3.0) {
        // Samsung Exynos / MediaTek range
        int raw = analogRead(PIN_BOOT_ROM);
        snprintf(id, sizeof(id), "SLSI_MTK_0x%04X", raw);
    } else if (voltage < 4.0) {
        // Google Tensor
        int raw = analogRead(PIN_BOOT_ROM);
        snprintf(id, sizeof(id), "GOOG_BL1_0x%04X", raw);
    } else {
        snprintf(id, sizeof(id), "UNKNOWN_0x%04X", analogRead(PIN_BOOT_ROM));
    }
    Serial.println(id);
}

// ===========================================================================
//  CMD: DETECT_RAM
//  Reads the RAM-detect strap pin.  Many test jigs use resistor networks on
//  the phone's RAM chip-select lines to determine installed capacity.
// ===========================================================================
void cmdDetectRam() {
    float voltage = readAnalogAveraged(PIN_RAM_DETECT);

    // Map voltage thresholds to common RAM configurations
    const char* result;
    if (voltage < 0.3) {
        result = "NO_DEVICE";
    } else if (voltage < 0.8) {
        result = "4GB_LPDDR4X";
    } else if (voltage < 1.5) {
        result = "6GB_LPDDR5";
    } else if (voltage < 2.2) {
        result = "8GB_LPDDR5";
    } else if (voltage < 3.0) {
        result = "8GB_LPDDR5X";
    } else if (voltage < 3.8) {
        result = "12GB_LPDDR5X";
    } else {
        result = "16GB_LPDDR5X";
    }
    Serial.println(result);
}

// ===========================================================================
//  CMD: DETECT_STORAGE
//  Similar strap-pin approach for identifying the storage IC.
// ===========================================================================
void cmdDetectStorage() {
    float voltage = readAnalogAveraged(PIN_STORAGE_DETECT);

    const char* result;
    if (voltage < 0.3) {
        result = "NO_DEVICE";
    } else if (voltage < 0.8) {
        result = "eMMC_5.1_64";
    } else if (voltage < 1.3) {
        result = "UFS_2.2_64";
    } else if (voltage < 1.8) {
        result = "UFS_2.2_128";
    } else if (voltage < 2.3) {
        result = "UFS_3.1_128";
    } else if (voltage < 2.8) {
        result = "UFS_3.1_256";
    } else if (voltage < 3.5) {
        result = "UFS_4.0_128";
    } else if (voltage < 4.2) {
        result = "UFS_4.0_256";
    } else {
        result = "NAND_NVME_256";
    }
    Serial.println(result);
}

// ===========================================================================
//  CMD: READ_POWER_RAILS
//  Reads the three power rail voltages and returns them in key=value format.
// ===========================================================================
void cmdReadPowerRails() {
    float battery = readAnalogAveraged(PIN_BATTERY_RAIL) * BATTERY_DIVIDER;
    float rail3v3 = readAnalogAveraged(PIN_3V3_RAIL)     * RAIL_3V3_DIVIDER;
    float vddCore = readAnalogAveraged(PIN_VDD_CORE)      * VDD_CORE_DIVIDER;

    // Format:  battery_rail=X.XX,3v3_rail=X.XX,vdd_core=X.XX
    Serial.print("battery_rail=");
    Serial.print(battery, 2);
    Serial.print(",3v3_rail=");
    Serial.print(rail3v3, 2);
    Serial.print(",vdd_core=");
    Serial.println(vddCore, 2);
}

// ===========================================================================
//  CMD: UART_HANDSHAKE
//  Sends a probe byte sequence over Software Serial to the phone and listens
//  for a boot-loader banner (e.g. "iBoot-…" or "QCOM_SAHARA_…").
// ===========================================================================
void cmdUartHandshake() {
    // Flush any stale data in the phone UART buffer
    while (phoneSerial.available()) {
        phoneSerial.read();
    }

    // Send a generic handshake sequence.
    // Many boot loaders respond to 0x7E or a simple "AT" probe.
    phoneSerial.write(0x7E);
    phoneSerial.write(0x55);
    phoneSerial.write('\r');
    phoneSerial.write('\n');

    // Wait up to 500 ms for a response
    unsigned long start = millis();
    char response[128];
    uint8_t rIdx = 0;

    while (millis() - start < 500) {
        if (phoneSerial.available()) {
            char c = phoneSerial.read();
            if (c == '\n' || c == '\r') {
                if (rIdx > 0) break;          // got a full line
            } else if (rIdx < sizeof(response) - 1) {
                response[rIdx++] = c;
            }
        }
    }
    response[rIdx] = '\0';

    if (rIdx > 0) {
        Serial.println(response);
    } else {
        Serial.println("NO_UART_RESPONSE");
    }
}

// ===========================================================================
//  CMD: READ_USB_DESC
//  Reads the state of the USB D+/D- lines to determine if a device is
//  connected and infer its speed.  For full PID/VID enumeration the host
//  PC should use libusb; this gives a quick presence check.
// ===========================================================================
void cmdReadUsbDescriptor() {
    int dp = digitalRead(PIN_USB_DP);
    int dm = digitalRead(PIN_USB_DM);

    if (dp == LOW && dm == LOW) {
        Serial.println("NO_USB_DEVICE");
    } else if (dp == HIGH && dm == LOW) {
        // Full-speed device pulls D+ high
        Serial.println("USB_FS_DETECTED");
    } else if (dp == LOW && dm == HIGH) {
        // Low-speed device pulls D- high
        Serial.println("USB_LS_DETECTED");
    } else {
        // Both high – high-speed negotiation happening or SE1 state
        Serial.println("USB_HS_DETECTED");
    }
}

// ===========================================================================
//  CMD: READ_SERIAL
//  Attempts to read a serial-number string from the phone via UART.
//  Many devices expose this during early boot or in download mode.
// ===========================================================================
void cmdReadSerial() {
    // Flush the buffer
    while (phoneSerial.available()) {
        phoneSerial.read();
    }

    // Send a "serial number request" command (manufacturer-specific)
    phoneSerial.print("AT+GSN\r\n");

    unsigned long start = millis();
    char response[64];
    uint8_t rIdx = 0;

    while (millis() - start < 500) {
        if (phoneSerial.available()) {
            char c = phoneSerial.read();
            if (c == '\n' || c == '\r') {
                if (rIdx > 0) break;
            } else if (rIdx < sizeof(response) - 1) {
                response[rIdx++] = c;
            }
        }
    }
    response[rIdx] = '\0';

    if (rIdx > 0) {
        Serial.println(response);
    } else {
        Serial.println("NO_SERIAL");
    }
}
