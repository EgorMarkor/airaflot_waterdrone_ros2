import rclpy
import typing as tp
import time
import pymodbus.client as ModbusClient

from rclpy.lifecycle import LifecycleNode, LifecyclePublisher, LifecycleState, TransitionCallbackReturn
from rclpy.timer import Timer

from airaflot_msgs.msg import EcostabSensors

from .sensors import Sensor, pHSensor, ConductivitySensor, ORPSensor, OxxygenSensor, EmulateSensor
from ...const_names import ECOSTAB_SENSORS_TOPIC_NAME
from ..config_wiring import ECOSTAB_SENSORS_PORT
from ..config import EMULATE_ECOSTAB_SENSORS

NODE_NAME = "ecostab_sensors"

class EcostabSensorsNode(LifecycleNode):

    def __init__(self, **kwargs):
        self.sensors: list = []
        self.publisher: tp.Optional[LifecyclePublisher] = None
        self.timer: tp.Optional[Timer] = None
        self.modbus_client: tp.Optional[ModbusClient.ModbusSerialClient] = None
        super().__init__(NODE_NAME, **kwargs)
        self.declare_parameter("emulate_sensors", False)

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        emulate_sensors = self.get_parameter('emulate_sensors').get_parameter_value().bool_value
        if emulate_sensors:
            self.sensors: tp.List[Sensor] = [EmulateSensor()]
        else:
            self.modbus_client = ModbusClient.ModbusSerialClient(
                ECOSTAB_SENSORS_PORT, baudrate=9600, bytesize=8, stopbits=1
            )
            self.sensors: tp.List[Sensor] = [
                ConductivitySensor(self.modbus_client), 
                ORPSensor(self.modbus_client), 
                OxxygenSensor(self.modbus_client), 
                pHSensor(self.modbus_client)
            ]
        try:
            for sensor in self.sensors:
                sensor.fetch(EcostabSensors())
        except Exception as e:
            self.get_logger().error(f"Exception in configure: {e}")
            return TransitionCallbackReturn.FAILURE
        self.publisher = self.create_lifecycle_publisher(EcostabSensors, ECOSTAB_SENSORS_TOPIC_NAME, 10)
        timer_period = 1  # seconds
        self.timer = self.create_timer(timer_period, self.timer_callback)
        return TransitionCallbackReturn.SUCCESS
    
    
    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_timer(self.timer)
        self.destroy_publisher(self.publisher)
        if self.modbus_client:
            self.modbus_client.close()
        self.sensors.clear()

        self.get_logger().info('on_cleanup() is called.')
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_timer(self.timer)
        self.destroy_publisher(self.publisher)
        if self.modbus_client:
            self.modbus_client.close()
        self.sensors.clear()

        self.get_logger().info('on_shutdown() is called.')
        return TransitionCallbackReturn.SUCCESS

    def timer_callback(self):
        msg = EcostabSensors()
        if self.publisher is not None and self.publisher.is_activated:
            for sensor in self.sensors:
                msg = sensor.fetch(msg)
                time.sleep(0.1)
            self.publisher.publish(msg)
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