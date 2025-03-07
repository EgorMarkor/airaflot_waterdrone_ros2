import rclpy
from rclpy.node import Node
import typing as tp
import time
import pymodbus.client as ModbusClient

from airaflot_msgs.msg import EcostabSensors

from .sensors import Sensor, pHSensor, ConductivitySensor, ORPSensor, OxxygenSensor, EmulateSensor
from ...const_names import ECOSTAB_SENSORS_TOPIC_NAME
from ..config_wiring import ECOSTAB_SENSORS_PORT
from ..config import EMULATE_ECOSTAB_SENSORS

NODE_NAME = "ecostab_sensors"

class EcostabSensorsNode(Node):

    def __init__(self):
        super().__init__(NODE_NAME)
        if EMULATE_ECOSTAB_SENSORS:
            self.sensors: tp.List[Sensor] = [EmulateSensor()]
        else:
            modbus_client = ModbusClient.ModbusSerialClient(
                ECOSTAB_SENSORS_PORT, baudrate=9600, bytesize=8, stopbits=1
            )
            self.sensors: tp.List[Sensor] = [ConductivitySensor(modbus_client), ORPSensor(modbus_client), OxxygenSensor(modbus_client), pHSensor(modbus_client)]
        self.publisher_ = self.create_publisher(EcostabSensors, ECOSTAB_SENSORS_TOPIC_NAME, 10)
        timer_period = 1  # seconds
        self.timer = self.create_timer(timer_period, self.timer_callback)

    def timer_callback(self):
        msg = EcostabSensors()
        for sensor in self.sensors:
            msg = sensor.fetch(msg)
            time.sleep(0.1)
        self.publisher_.publish(msg)
        self.get_logger().info(f"Publishing: {msg}")


def main(args=None):
    rclpy.init(args=args)

    minimal_publisher = EcostabSensorsNode()

    rclpy.spin(minimal_publisher)

    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    minimal_publisher.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()