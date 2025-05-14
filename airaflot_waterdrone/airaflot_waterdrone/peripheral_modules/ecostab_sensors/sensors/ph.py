from .sensor import Sensor

from airaflot_msgs.msg import EcostabSensors

from ....const_names import USE_PH_RAPAM

PH_SLAVE_ID = 0

PH_REGISTER = 0
TEMPERATURE_REGISTER = 2

class pHSensor(Sensor):
    def __init__(self):
        super().__init__()
        self.name = "pH"
        self.slave_id = PH_SLAVE_ID
        self.registers = [PH_REGISTER, TEMPERATURE_REGISTER]
        self.use_param = USE_PH_RAPAM
        
    def fetch(self, data: EcostabSensors) -> EcostabSensors:
        ph_res = self.client.read_holding_registers(PH_REGISTER, 2, slave=PH_SLAVE_ID)
        temperature_res = self.client.read_holding_registers(TEMPERATURE_REGISTER, 2, slave=PH_SLAVE_ID)
        data.ph = self._unpack_float_registers(ph_res.registers)
        data.temperature = self._unpack_float_registers(temperature_res.registers)
        return data
