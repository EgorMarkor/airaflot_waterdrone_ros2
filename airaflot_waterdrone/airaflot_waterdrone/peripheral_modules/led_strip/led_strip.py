import rclpy
import time

from rclpy.node import Node
import board
import neopixel

from std_srvs.srv import Trigger
from rclpy.executors import ExternalShutdownException

from ...const_names import TRIGGER_RELE_SERVICE_NAME

NODE_NAME = "led_strip"

PIXELS_COUNT = 40

TIMER_PERIOD = 1


class WaterSamplerReleNode(Node):
    def __init__(self):
        super().__init__(NODE_NAME)
        self.pixels = neopixel.NeoPixel(board.D18, PIXELS_COUNT)

        self.is_blink = True
        self.main_color = WHITE_COLOR
        self.secondary_color = ORANGE_COLOR

        self.service = self.create_service(
            Trigger, TRIGGER_RELE_SERVICE_NAME, self.trigger_rele
        )
        self.timer = self.create_timer(TIMER_PERIOD, self.timer_callback)
        self.get_logger().info("LED strip is ready")

    def timer_callback(self):
        for pixel in self.pixels:
            pixel = WHITE_COLOR

    def _blink(self, main_color: tuple, secondary_color: tuple):
        for i in range(1, PIXELS_COUNT - 3):
            self.pixels[i - 1] = main_color
            self.pixels[i] = secondary_color
            self.pixels[i + 1] = secondary_color
            self.pixels[i + 2] = secondary_color
            time.sleep(0.3)
        self.pixels.fill(main_color)
    
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
