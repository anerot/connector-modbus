import requests
from connectors.core.connector import get_logger, ConnectorError
from .constants import LOGGER_NAME, MODBUS_EXCEPTIONS
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
from pymodbus.pdu import ExceptionResponse
import struct
import time
logger = get_logger(LOGGER_NAME)

class ModbusNotConnectedError(ConnectorError):
    """Custom exception raised when connection fails or a Modbus Gateway exception occurs."""
    pass

def _execute_modbus_action(params, action_func):
    """Manage TCP connection, execute the Modbus command, and handle graceful closure."""
    host = params.get("host")
    port = int(params.get("port", 502))
    timeout = int(params.get("timeout", 10))

    client = ModbusTcpClient(host=host, port=port, timeout=timeout)

    if not client.connect():
        raise ConnectorError(f"Failed to connect to Modbus TCP server at {host}:{port}")

    try:
        result = action_func(client)
        if result.isError():
            if isinstance(result, ExceptionResponse):
                # Calculate the original Modbus function (Function Code - 128)
                original_fc = result.function_code - 128 if result.function_code > 128 else result.function_code
                exc_code = result.exception_code
                
                # Error code translation
                exc_reason = MODBUS_EXCEPTIONS.get(
                    exc_code, f"Unknown Modbus Exception Code ({exc_code})"
                )

                error_msg = (
                    f"Modbus Error on Device ID {result.dev_id}: "
                    f"Original FC={original_fc} (Response FC={result.function_code}). "
                    f"Reason: {exc_reason}"
                )

                # Raise connection-specific exception for Gateway errors (10 and 11)
                if exc_code in (10, 11):
                    raise ModbusNotConnectedError(error_msg)

                raise ConnectorError(error_msg)
            
            raise ConnectorError(f"Modbus Error: {result}")      

        return result
    except ModbusException as err:
        raise ConnectorError(f"Modbus exception during execution: {str(err)}")
    finally:
        client.close()

def scan_units(config, params):
    """
    Scan a Modbus TCP gateway to discover active slave/device Unit IDs.
    Returns a list of detected device IDs.
    """
    host = params.get("host")
    port = int(params.get("port", 502))
    timeout = float(params.get("timeout", 1))
    if params.get("scan_type") == "Gateway":
        start_id = int(params.get("startId", 1))
        end_id = int(params.get("endId", 247))
        # Basic range validation
        if start_id < 1 or end_id > 247 or start_id > end_id:
            return {
                "status": "failed",
                "message": f"Invalid Unit ID range: startId={start_id}, endId={end_id}. Must be between 1 and 247."
            }
    else:
        unique_id=int(params.get("unitId", 255))
        if unique_id < 1 or unique_id > 255:
            return {
                "status": "failed",
                "message": f"Invalid Unit ID: unitId={unique_id}. Must be between 1 and 255."
            }
        start_id = unique_id
        end_id = unique_id
    
    test_address = int(params.get("testAddress", 0))

    

    client = ModbusTcpClient(host=host, port=port, timeout=timeout)

    # 1. Verify TCP connection to the gateway
    if not client.connect():
        return {
            "status": "notconnected",
            "message": f"Failed to connect to Modbus TCP server/gateway at {host}:{port}"
        }

    active_units = []
    
    try:
        # 2. Iterate through requested Unit ID range
        for unit_id in range(start_id, end_id + 1):
            try:
                # Read 1 Holding Register to probe device presence
                response = client.read_holding_registers(
                    address=test_address, 
                    count=1, 
                    device_id=unit_id
                )

                if response.isError():
                    if isinstance(response, ExceptionResponse):
                        exc_code = response.exception_code
                        # Gateway Exceptions 10 (0x0A) and 11 (0x0B) indicate target offline/unreachable
                        if exc_code not in (10, 11):
                            # Standard Modbus Exception (0x01, 0x02, etc.) confirms device IS PRESENT
                            active_units.append(unit_id)
                else:
                    # Successful register read confirms device presence
                    active_units.append(unit_id)

            except ModbusException:
                # Skip on unexpected protocol/communication errors for a single unit
                pass

            # Small delay to prevent RS485 bus saturation behind the gateway
            time.sleep(0.02)

        return {
            "status": "success",
            "ip": host,
            "port": port,
            "scannedRange": f"{start_id}-{end_id}",
            "count": len(active_units),
            "activeUnits": active_units
        }

    except Exception as err:
        return {
            "status": "failed",
            "message": f"Unexpected error during Unit ID scan: {str(err)}"
        }
    finally:
        client.close()


def read_holding(config, params):
    """Read Holding Registers (FC03)."""
    address = int(params.get("address"))
    count = int(params.get("registerCount", 1))
    unit = int(params.get("unitId", 1))

    def action(client):
        return client.read_holding_registers(address=address, count=count, device_id=unit)

    try:
        res = _execute_modbus_action(params, action)
        return {
            "status": "success",
            "unitId": unit,
            "address": address,
            "registers": res.registers
        }
    except ModbusNotConnectedError as err:
        return {
            "status": "notconnected",
            "message": str(err)
        }
    except ConnectorError as err:
        return {
            "status": "failed",
            "message": str(err)
        }
    except Exception as err:
        return {
            "status": "failed",
            "message": f"Unexpected error: {str(err)}"
        }


def read_input(config, params):
    """Read Input Registers (FC04)."""
    address = int(params.get("address"))
    count = int(params.get("registerCount", 1))
    unit = int(params.get("unitId", 1))

    def action(client):
        return client.read_input_registers(address=address, count=count, device_id=unit)

    try:
        res = _execute_modbus_action(params, action)
        return {
            "status": "success",
            "unitId": unit,
            "address": address,
            "registers": res.registers
        }
    except ConnectorError as err:
        return {
            "status": "failed",
            "message": str(err)
        }
    except Exception as err:
        return {
            "status": "failed",
            "message": f"Unexpected error: {str(err)}"
        }


def write_register(config, params):
    """Write Single or Multiple Holding Registers (FC06 / FC16)."""
    address = int(params.get("address"))
    value = params.get("value")
    unit = int(params.get("unitId", 1))

    try:
        # 1. Parse input value safely (handles list, comma-separated string, or single integer)
        if isinstance(value, list):
            parsed_values = [int(v) for v in value]
        elif isinstance(value, str) and "," in value:
            parsed_values = [int(v.strip()) for v in value.split(",")]
        else:
            parsed_values = int(value)

        # 2. Define the Modbus TCP action
        def action(client):
            # Multiple registers -> FC16 (write_registers)
            if isinstance(parsed_values, list):
                return client.write_registers(
                    address=address,
                    values=parsed_values,
                    device_id=unit,
                )
            
            # Single register -> FC06 (write_register)
            return client.write_register(
                address=address,
                value=parsed_values,
                device_id=unit,
            )

        # 3. Execute action with managed TCP life-cycle
        res = _execute_modbus_action(params, action)

        return {
            "status": "success",
            "unitId": unit,
            "address": address,
            "value": parsed_values,
            "count": len(parsed_values) if isinstance(parsed_values, list) else 1
        }

    except ConnectorError as err:
        return {
            "status": "failed",
            "message": str(err)
        }
    except (ValueError, TypeError) as err:
        return {
            "status": "failed",
            "message": f"Invalid input value format: {str(err)}"
        }
    except Exception as err:
        return {
            "status": "failed",
            "message": f"Unexpected error: {str(err)}"
        }


def write_read(config, params):
    """Read and Write Holding Registers simultaneously (FC23)."""
    read_address = int(params.get("readAddress"))
    read_count = int(params.get("readNb", 1))
    write_address = int(params.get("writeAddress"))
    write_values = params.get("writeValues")
    unit = int(params.get("unitId", 1))

    try:
        # 1. Parse write values safely (handles list, comma-separated string, or single integer)
        if isinstance(write_values, list):
            parsed_values = [int(v) for v in write_values]
        elif isinstance(write_values, str) and "," in write_values:
            parsed_values = [int(v.strip()) for v in write_values.split(",")]
        else:
            parsed_values = [int(write_values)]

        # 2. Define the Modbus TCP action (FC23)
        def action(client):
            return client.readwrite_registers(
                read_address=read_address,
                read_count=read_count,
                write_address=write_address,
                values=parsed_values,
                device_id=unit
            )

        # 3. Execute action with managed TCP lifecycle
        res = _execute_modbus_action(params, action)

        return {
            "status": "success",
            "unitId": unit,
            "readAddress": read_address,
            "readCount": read_count,
            "writeAddress": write_address,
            "writeValues": parsed_values,
            "registers": res.registers
        }

    except ConnectorError as err:
        return {
            "status": "failed",
            "message": str(err)
        }
    except (ValueError, TypeError) as err:
        return {
            "status": "failed",
            "message": f"Invalid writeValues format: {str(err)}"
        }
    except Exception as err:
        return {
            "status": "failed",
            "message": f"Unexpected error: {str(err)}"
        }


def read_device_information(config, params):
    """Read Device Identification (FC43 / MEI 14)."""
    read_code = int(params.get("readCode", 1))
    object_id = int(params.get("objectId", 0))
    unit = int(params.get("unitId", 1))

    try:
        # 1. Define the Modbus TCP action (FC43 / MEI 14)
        def action(client):
            return client.read_device_information(
                read_code=read_code, 
                object_id=object_id, 
                device_id=unit
            )

        # 2. Execute action with managed TCP lifecycle
        res = _execute_modbus_action(params, action)

        # 3. Parse decoded information objects
        information = {}
        if hasattr(res, 'information') and isinstance(res.information, dict):
            for key, val in res.information.items():
                information[key] = val.split(b"\x00")[0].decode('utf-8', errors='ignore').strip() if isinstance(val, bytes) else str(val)


        return {
            "status": "success",
            "unitId": unit,
            "readCode": read_code,
            "objectId": object_id,
            "information": information
        }

    except ConnectorError as err:
        return {
            "status": "failed",
            "message": str(err)
        }
    except Exception as err:
        return {
            "status": "failed",
            "message": f"Unexpected error: {str(err)}"
        }


def read_coils(config, params):
    """Read Coils (FC01)."""
    address = int(params.get("address"))
    count = int(params.get("count", 1))
    unit = int(params.get("unitId", 1))

    def action(client):
        return client.read_coils(address=address, count=count, device_id=unit)

    res = _execute_modbus_action(params, action)
    return {"bits": res.bits[:count]}


def read_discrete_inputs(config, params):
    """Read Discrete Inputs (FC02)."""
    address = int(params.get("address"))
    count = int(params.get("count", 1))
    unit = int(params.get("unitId", 1))

    def action(client):
        return client.read_discrete_inputs(address=address, count=count, device_id=unit)

    res = _execute_modbus_action(params, action)
    return {"bits": res.bits[:count]}


def write_coils(config, params):
    """Write Single Coil (FC05)."""
    address = int(params.get("address"))
    value = bool(params.get("value"))
    unit = int(params.get("unitId", 1))

    def action(client):
        return client.write_coil(address=address, value=value, device_id=unit)

    res = _execute_modbus_action(params, action)
    return {"status": "success", "address": address, "value": value}


def write_multiple_coils(config, params):
    """Write Multiple Coils (FC15)."""
    address = int(params.get("address"))
    values = params.get("values")
    unit = int(params.get("unitId", 1))

    if not isinstance(values, list):
        raise ConnectorError("Parameter 'values' must be a list of boolean values.")

    bool_values = [bool(v) for v in values]

    def action(client):
        return client.write_coils(address=address, values=bool_values, device_id=unit)

    res = _execute_modbus_action(params, action)
    return {"status": "success", "address": address, "count": len(bool_values)}
    
def convert_to_string(config, params):
    """
    Convert a list of 16-bit Modbus registers into a clean ASCII string.
    Stops reading at the first null byte (\\x00) to strip memory padding.
    """
    registers = params.get("registers")

    try:
        # 1. Parse input format (handles list or comma-separated string)
        if isinstance(registers, str) and "," in registers:
            parsed_regs = [int(r.strip()) for r in registers.split(",")]
        elif isinstance(registers, list):
            parsed_regs = [int(r) for r in registers]
        else:
            raise ValueError("Input 'registers' must be a list or a comma-separated string.")

        if not parsed_regs:
            raise ValueError("The 'registers' input cannot be empty.")

        # 2. Pack as 16-bit unsigned integers (Big-Endian)
        raw_bytes = struct.pack(f">{len(parsed_regs)}H", *parsed_regs)

        # 3. Truncate at the first null byte (\\x00) and decode as ASCII
        decoded = raw_bytes.split(b"\x00")[0].decode("ascii", errors="ignore").strip()

        return {
            "status": "success",
            "registers": parsed_regs,
            "value": decoded
        }

    except (ValueError, TypeError) as err:
        return {
            "status": "failed",
            "message": f"Invalid register input: {str(err)}"
        }
    except Exception as err:
        return {
            "status": "failed",
            "message": f"Unexpected conversion error: {str(err)}"
        }

def convert_to_int32(config, params):
    """
    Convert two 16-bit Modbus registers into a signed 32-bit integer (int32).
    Expects Big-Endian register ordering (MSW, LSW).
    """
    registers = params.get("registers")

    try:
        # 1. Parse input format (handles list or comma-separated string)
        if isinstance(registers, str) and "," in registers:
            parsed_regs = [int(r.strip()) for r in registers.split(",")]
        elif isinstance(registers, list):
            parsed_regs = [int(r) for r in registers]
        else:
            raise ValueError("Input 'registers' must be a list or a comma-separated string containing at least 2 values.")

        # 2. Validate register count
        if len(parsed_regs) < 2:
            raise ValueError(f"At least 2 registers are required, got {len(parsed_regs)}.")

        msw, lsw = parsed_regs[0], parsed_regs[1]

        # 3. Pack as two 16-bit unsigned shorts and unpack as one signed 32-bit int (Big-Endian)
        raw_bytes = struct.pack(">HH", msw, lsw)
        value = struct.unpack(">i", raw_bytes)[0]

        return {
            "status": "success",
            "value": value
        }

    except (ValueError, TypeError) as err:
        return {
            "status": "failed",
            "message": f"Invalid register input: {str(err)}"
        }
    except Exception as err:
        return {
            "status": "failed",
            "message": f"Unexpected conversion error: {str(err)}"
        }

def check_health(self, config=None, *args, **kwargs):
        pass

# Mapping FortiSOAR operations to Python functions
operations = {
    'readholding': read_holding,
    'readinput': read_input,
    'writeregister': write_register,
    'writeread': write_read,
    'read_device_information': read_device_information,
    'readcoils': read_coils,
    'readdiscreteinputs': read_discrete_inputs,
    'writecoils': write_coils,
    'writemultiplecoils': write_multiple_coils,
    'scan_units': scan_units,
    'convert_to_string': convert_to_string,
    'convert_to_int32': convert_to_int32
}