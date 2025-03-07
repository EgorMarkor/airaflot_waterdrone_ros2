from .sensor import Sensor

from airaflot_msgs.msg import EcostabSensors

PH_SLAVE_ID = 0

PH_REGISTER = 0
TEMPERATURE_REGISTER = 2

class pHSensor(Sensor):
    def fetch(self, data: EcostabSensors) -> EcostabSensors:
        ph_res = self.client.read_holding_registers(PH_REGISTER, 2, slave=PH_SLAVE_ID)
        # temperature_res = self.client.read_holding_registers(TEMPERATURE_REGISTER, 2, slave=PH_SLAVE_ID)
        data.ph = self._unpack_float_registers(ph_res.registers)
        # data.temperature = self._unpack_float_registers(temperature_res.registers)
        return data
