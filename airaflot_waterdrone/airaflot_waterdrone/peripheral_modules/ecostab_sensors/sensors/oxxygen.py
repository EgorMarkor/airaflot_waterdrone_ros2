from .sensor import Sensor

from airaflot_msgs.msg import EcostabSensors

OXXYGEN_SLAVE_ID = 10

OXXYGEN_REGISTER = 0
SATURATION_REGISTER = 2

class OxxygenSensor(Sensor):
    def fetch(self, data: EcostabSensors) -> EcostabSensors:
        oxxygen_res = self.client.read_holding_registers(OXXYGEN_REGISTER, 2, slave=OXXYGEN_SLAVE_ID)
        saturation_res = self.client.read_holding_registers(SATURATION_REGISTER, 2, slave=OXXYGEN_SLAVE_ID)
        data.oxxygen = self._unpack_float_registers(oxxygen_res.registers)
        data.oxxygen_saturation = self._unpack_float_registers(saturation_res.registers)
        return data
