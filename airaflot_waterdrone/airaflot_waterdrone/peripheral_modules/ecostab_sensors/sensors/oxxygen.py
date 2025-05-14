from .sensor import Sensor

from airaflot_msgs.msg import EcostabSensors

from ....const_names import USE_OXXYGEN_RAPAM

OXXYGEN_SLAVE_ID = 10

OXXYGEN_REGISTER = 0
SATURATION_REGISTER = 2

class OxxygenSensor(Sensor):
    def __init__(self):
        super().__init__()
        self.name = "Oxxygen"
        self.slave_is = OXXYGEN_SLAVE_ID
        self.registers = [OXXYGEN_REGISTER, SATURATION_REGISTER]
        self.use_param = USE_OXXYGEN_RAPAM
        
    def fetch(self, data: EcostabSensors) -> EcostabSensors:
        oxxygen_res = self.client.read_holding_registers(OXXYGEN_REGISTER, 2, slave=OXXYGEN_SLAVE_ID)
        saturation_res = self.client.read_holding_registers(SATURATION_REGISTER, 2, slave=OXXYGEN_SLAVE_ID)
        data.oxxygen = self._unpack_float_registers(oxxygen_res.registers)
        data.oxxygen_saturation = self._unpack_float_registers(saturation_res.registers)
        return data
