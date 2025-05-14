from .sensor import Sensor

from airaflot_msgs.msg import EcostabSensors

from ....const_names import USE_CONDUCTIVITY_RAPAM

COND_SLAVE_ID = 3

TEMP_REGISTER = 0x9004
COND_REGISTER = 0x9006
TDS_REGISTER = 0x9008
SALINITY_REGISTER = 0x900A

class ConductivitySensor(Sensor):
    def __init__(self):
        super().__init__()
        self.name = "Conductivity"
        self.slave_id = COND_SLAVE_ID
        self.registers = [TEMP_REGISTER, COND_REGISTER, TDS_REGISTER, SALINITY_REGISTER]
        self.use_param = USE_CONDUCTIVITY_RAPAM
        
    def fetch(self, data: EcostabSensors) -> EcostabSensors:
        conductivity_res = self.client.read_holding_registers(COND_REGISTER, 2, slave=COND_SLAVE_ID)
        temp_res = self.client.read_holding_registers(TEMP_REGISTER, 2, slave=COND_SLAVE_ID)
        tds_res = self.client.read_holding_registers(TDS_REGISTER, 2, slave=COND_SLAVE_ID)
        salinity_res = self.client.read_holding_registers(SALINITY_REGISTER, 2, slave=COND_SLAVE_ID)
        data.conductivity = self._unpack_float_registers(conductivity_res.registers)
        data.temperature = self._unpack_float_registers(temp_res.registers)
        data.salinity_tds = self._unpack_float_registers(tds_res.registers)
        data.salinity = self._unpack_float_registers(salinity_res.registers)
        return data
