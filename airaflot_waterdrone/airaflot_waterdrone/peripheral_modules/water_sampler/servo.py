import rclpy
import time

from rclpy.node import Node
import RPi.GPIO as GPIO
import pymodbus.client as ModbusClient

from std_srvs.srv import Trigger

from ..config_wiring import WATER_SAMPLER_RELE_PORT
from ...const_names import TRIGGER_RELE_SERVICE_NAME

NODE_NAME = "water_sampler_rele"

CLOSE_POSITION = 10
OPEN_POSITION = 6
OPEN_RELE_DELAY = 1


class WaterSamplerReleNode(Node):
    def __init__(self):
        super().__init__(NODE_NAME)
        # self.rate = self.create_rate(OPEN_RELE_DELAY)
        # self.pwm = self._setup_gpio()
        self.modbus_client = ModbusClient.ModbusSerialClient(
                WATER_SAMPLER_RELE_PORT, baudrate=9600, bytesize=8, stopbits=1
            )
        self.service = self.create_service(
            Trigger, TRIGGER_RELE_SERVICE_NAME, self.trigger_rele
        )
        # self.service = self.create_service(
        #     Trigger, OPEN_RELE_SERVICE_NAME, self.open_rele
        # )
        self.get_logger().info("Water Sampler Servo is ready")

    def trigger_rele(self, request: Trigger.Request, response: Trigger.Response):
        self.get_logger().info("Start trigger rele")
        try:
            self.modbus_client.write_register(112,1,1)
            time.sleep(OPEN_RELE_DELAY)
            self.modbus_client.write_register(112,0,1)
            response.success = True
            response.message = "ok"
        except Exception as e:
            self.get_logger().error(f"Open servo service failed with error {e}")
            response.success = False
            response.message = f"Open servo service failed with error {e}"
        finally:
            return response


def main():
    try:
        rclpy.init()
        minimal_service = WaterSamplerReleNode()
        rclpy.spin(minimal_service)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
