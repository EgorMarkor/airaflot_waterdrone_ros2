from abc import ABC, abstractmethod
import struct
import pymodbus.client as ModbusClient

from airaflot_msgs.msg import EcostabSensors

class Sensor(ABC):
    def __init__(self) -> None:
        self.client: ModbusClient.ModbusSerialClient | None = None
        self.name: str | None = None
        self.slave_id: int | None = None
        self.registers: list = []
        self.use_param: str | None = None

    def activate(self, modbus_client: ModbusClient.ModbusSerialClient) -> None:
        self.client = modbus_client

    @abstractmethod
    def fetch(self, data: EcostabSensors) -> EcostabSensors:
        pass 

    def _unpack_float_registers(self, registers: list):
        t = (registers[0], registers[1])
        packed_string = struct.pack("HH", *t)
        unpacked_float = struct.unpack("f", packed_string)[0]
        return unpacked_float