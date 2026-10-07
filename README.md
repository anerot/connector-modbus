Modbus connector integrates the Python Library pymodbus.
With this connector you can interact with OT devices supporting Modbus.
It implements:
- READ_COILS (0x01)=Func01
- READ_DISCRETE_INPUTS (0x02)=Func02
- READ_HOLDING_REGISTERS (0x03)=Func03
- READ_INPUT_REGISTERS (0x04)=Func4
- WRITE_SINGLE_COIL (0x05)=Func05
- WRITE_SINGLE_REGISTER (0x06)=Func06
- WRITE_MULTIPLE_COILS (0x0F)=Func15
- WRITE_MULTIPLE_REGISTERS (0x10)=Func16
- WRITE_READ_MULTIPLE_REGISTERS (0x17)=Func23
- Read Device Information (0x2B/0x0E)=Func43

It includes some extra capabilities like:
- Scan a Modbus device for slave devices
- Convert registers to string
- Convert registers to int32
