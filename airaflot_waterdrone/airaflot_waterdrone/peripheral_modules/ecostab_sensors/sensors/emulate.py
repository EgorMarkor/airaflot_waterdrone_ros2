import random

from airaflot_msgs.msg import EcostabSensors
from .sensor import Sensor

class EmulateSensor(Sensor):
    def __init__(self):
        super().__init__()
        self.name = "Emulate"
        
    def fetch(self, data: EcostabSensors) -> EcostabSensors:
        data.orp = random.uniform(0,20)
        data.temperature = random.uniform(0,20)
        data.ph = random.uniform(0,20)
        data.oxxygen = random.uniform(0,20)
        data.conductivity = random.uniform(0,20)
        return data