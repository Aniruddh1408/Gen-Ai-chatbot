# Device Alerts And Troubleshooting Manual

## Rapid Blinking Red Light

When an IoT monitoring device begins flashing a rapid red light, it usually indicates that the battery management firmware is outdated or that the device is preparing for an over-the-air firmware update. During this state, the device may temporarily suspend non-essential operations while it prepares to receive or install the update package.

What to do:

1. Keep the device connected to stable power.
2. Keep the device within range of the configured WiFi gateway.
3. Check the companion app or operations console for firmware update status.
4. Wait up to 10 minutes for the update preparation or installation stage to complete.
5. If the red light continues beyond 10 minutes, create a technical support ticket with device ID, location, timestamp, and current network status.

What not to do:

1. Do not manually power cycle the device during a rapid red flashing sequence.
2. Do not remove the battery or disconnect the power adapter during a firmware update.
3. Do not factory reset the device unless a technical operator has confirmed that the update process has failed.

Escalate when:

1. The red light continues beyond 10 minutes.
2. The device disappears from the operations console.
3. The firmware status remains stuck in preparing, downloading, or installing.
4. The device repeatedly restarts after the update attempt.

## Error Code E-404

Error code E-404 is generated when the device is unable to establish a connection with the central WiFi router or gateway. This may occur because of weak signal strength, an incorrect SSID or password, blocked network access, gateway downtime, excessive distance from the router, or physical obstacles between the device and the gateway.

What to do:

1. Confirm that the gateway or router is powered on.
2. Confirm that the configured SSID and password are correct.
3. Move the device closer to the gateway and retry synchronization.
4. Check whether other devices on the same network are connected.
5. Inspect firewall, captive portal, or MAC filtering rules if the network recently changed.

What not to do:

1. Do not assume E-404 is a web page not found error in the device context.
2. Do not replace the device before checking router status and credentials.
3. Do not reset resident data or clinical records because of this device connectivity error.

Escalate when:

1. The gateway is online but the device cannot connect after credential verification.
2. Multiple devices in the same ward report E-404.
3. The device has weak signal strength even when placed near the router.

## Sleep Mode Indicator

A slow pulsing green light indicates that the device is in sleep mode. In sleep mode, the device reduces power consumption while preserving scheduled monitoring functions. The device should wake automatically for configured measurement windows or synchronization intervals.

What to do:

1. Verify that the next scheduled measurement time is configured correctly.
2. Confirm that sleep mode is expected for the device profile.
3. Wake the device from the companion app only if an immediate reading is required.

Escalate when the device does not wake during scheduled measurement windows or remains in sleep mode after a manual wake request.

## Temperature Protection Mode

The device includes internal temperature monitoring to prevent overheating and hardware degradation. If internal temperature rises above the configured threshold, the device may enter protection mode and pause non-essential operations.

What to do:

1. Move the device away from direct sunlight, enclosed cabinets, heaters, or hot equipment.
2. Ensure airflow around the enclosure.
3. Wait for the device to cool before restarting non-critical operations.
4. Check whether nearby devices are reporting similar temperature alerts.

Escalate when temperature protection mode repeats in the same location or when the enclosure feels physically hot.

## Moisture Sensor Recalibration

To recalibrate the moisture sensor on an agricultural or environmental IoT node, press and hold the reset or calibration button for approximately 10 seconds. The status light should blink amber during calibration. Release the button when the indicator turns steady blue. Keep the sensor probe exposed to the required reference condition during calibration.

Do not recalibrate while the sensor is actively transmitting data. Do not remove power during calibration. If calibration fails twice, open a technical support ticket and include the device ID and calibration timestamp.

## General Maintenance

Keep firmware updated, avoid extreme environmental exposure, verify gateway placement, and inspect power connections during routine maintenance. For healthcare deployments, any maintenance that may interrupt resident monitoring should be scheduled during an approved maintenance window and communicated to the care team.
