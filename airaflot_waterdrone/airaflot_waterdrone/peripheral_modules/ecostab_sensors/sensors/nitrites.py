from .sensor import Sensor

from airaflot_msgs.msg import EcostabSensors

from ....const_names import USE_NITRITE_RAPAM

NITRITE_SLAVE_ID = 5

NO2_REGISTER = 0x900A
NO3_REGISTER = 0x9008
TEMP_REGISTER = 0x9006

class NitriteSensor(Sensor):
    def __init__(self):
        super().__init__()
        self.name = "Nitrite"
        self.slave_id = NITRITE_SLAVE_ID
        self.registers = [NO2_REGISTER, NO3_REGISTER, TEMP_REGISTER]
        self.use_param = USE_NITRITE_RAPAM
        
    def fetch(self, data: EcostabSensors) -> EcostabSensors:
        no2_res = self.client.read_holding_registers(NO2_REGISTER, 2, slave=NITRITE_SLAVE_ID)
        no3_res = self.client.read_holding_registers(NO3_REGISTER, 2, slave=NITRITE_SLAVE_ID)
        temp_res = self.client.read_holding_registers(TEMP_REGISTER, 2, slave=NITRITE_SLAVE_ID)
        data.no2 = self._unpack_float_registers(no2_res.registers)
        data.no3 = self._unpack_float_registers(no3_res.registers)
        data.temperature = self._unpack_float_registers(temp_res.registers)
        return data