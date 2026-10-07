LOGGER_NAME = 'modbus'
MODBUS_EXCEPTIONS = {
    1: "Illegal Function (0x01) - The function code is not supported by the slave/device.",
    2: "Illegal Data Address (0x02) - The data address is not available or out of range.",
    3: "Illegal Data Value (0x03) - A value contained in the query data field is not allowable.",
    4: "Slave Device Failure (0x04) - An unrecoverable error occurred while processing the request.",
    5: "Acknowledge (0x05) - The slave accepted the request, but needs time to process it.",
    6: "Slave Device Busy (0x06) - Specialized message, device is engaged in a long process.",
    8: "Memory Parity Error (0x08) - Parity error in slave memory during operation.",
    10: "Gateway Path Unavailable (0x0A) - Gateway misconfigured or overloaded.",
    11: "Gateway Target Device Failed to Respond (0x0B) - Target device is offline or not responding."
}