import rclpy
import typing as tp
import time

from rclpy.node import Node
import board
import neopixel

from rclpy.executors import ExternalShutdownException
from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn
from airaflot_msgs.srv import LedStripMode
from rclpy.executors import MultiThreadedExecutor

from ...const_names import LED_STRIP_SET_MODE_SERVICE
from .led_modes import LedMode, LedColor

NODE_NAME = "led_strip"

PIXELS_COUNT = 40

TIMER_PERIOD = 2


class LedStripNode(Node):
    def __init__(self):
        super().__init__(NODE_NAME)
        self.timer_callback_group = ReentrantCallbackGroup()
        self.pixels = neopixel.NeoPixel(board.D18, PIXELS_COUNT)
        self.current_mode = LedMode.NOT_READY

        self.service = self.create_service(
            LedStripMode, LED_STRIP_SET_MODE_SERVICE, self.set_mode
        )
        self.timer = self.create_timer(TIMER_PERIOD, self.timer_callback, callback_group=self.timer_callback_group)
        self.get_logger().info("LED strip is configured")

    def timer_callback(self):
        if self.current_mode.is_blink:
            self._one_blink(self.current_mode.main_color, self.current_mode.secondary_color)
        else:
            self.pixels.fill(self.current_mode.main_color)

    def _one_blink(self, main_color: tuple, secondary_color: tuple):
        for i in range(1, PIXELS_COUNT - 6):
            self.pixels[i - 1] = main_color
            self.pixels[i] = secondary_color
            self.pixels[i + 1] = secondary_color
            self.pixels[i + 2] = secondary_color
            self.pixels[i + 3] = secondary_color
            self.pixels[i + 4] = secondary_color
            self.pixels[i + 5] = secondary_color
            time.sleep(0.1)
        self.pixels.fill(main_color)
    
    def set_mode(self, request: LedStripMode.Request, response: LedStripMode.Response):
        try:
            self.current_mode = LedMode.from_ros_srv(request)
            self.get_logger().info(f"Set new Led mode: {self.current_mode.name}")
            response.success = True
        except Exception as e:
            self.get_logger().error(f"Set new Led mode failed with error {e}")
            response.success = False
        finally:
            return response


def main():
    try:
        rclpy.init()
        minimal_service = LedStripNode()
        executor = MultiThreadedExecutor()
        executor.add_node(minimal_service)
        executor.spin()
        # rclpy.spin(minimal_service)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
