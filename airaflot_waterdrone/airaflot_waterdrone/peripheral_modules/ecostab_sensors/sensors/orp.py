from .sensor import Sensor

from airaflot_msgs.msg import EcostabSensors

from ....const_names import USE_ORP_RAPAM

ORP_SLAVE_ID = 6

ORP_REGISTER = 0x9008

class ORPSensor(Sensor):
    def __init__(self):
        super().__init__()
        self.name = "ORP"
        self.slave_id = ORP_SLAVE_ID
        self.registers = [ORP_REGISTER]
        self.use_param = USE_ORP_RAPAM
        
    def fetch(self, data: EcostabSensors) -> EcostabSensors:
        orp_res = self.client.read_holding_registers(ORP_REGISTER, 2, slave=ORP_SLAVE_ID)
        data.orp = self._unpack_float_registers(orp_res.registers)
        return data
