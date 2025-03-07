import rclpy
import time
from threading import Event
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node, Client

from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

from airaflot_msgs.srv import WaterSampler, WaterSamplerMotor
from mavros_msgs.srv import SetMode
from mavros_msgs.msg import State
from std_srvs.srv import Trigger

from ..const_names import SET_LOITER_MODE_SERVICE_NAME, SET_PREVIOUS_MODE_SERVICE_NAME

NODE_NAME = "mavros_mode_controller"

SET_MODE_MAVROS_SERVICE_NAME = "/mavros/set_mode"
STATE_MAVROS_TOPIC_NAME = "/mavros/state"
LOITER_MODE = "LOITER"


class ModeControllerNode(Node):
    def __init__(self):
        super().__init__(NODE_NAME)
        self.service_done_event = Event()
        self.callback_group = ReentrantCallbackGroup()

        ### Service Clients ####

        self.set_mode_service_client = self.create_client(
            SetMode, SET_MODE_MAVROS_SERVICE_NAME
        )
        while not self.set_mode_service_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("Wait for set mode mavros service")

        ### Service Servers ###

        self.service = self.create_service(
            Trigger,
            SET_LOITER_MODE_SERVICE_NAME,
            self.set_loiter_mode,
            callback_group=self.callback_group,
        )
        self.service = self.create_service(
            Trigger,
            SET_PREVIOUS_MODE_SERVICE_NAME,
            self.set_previous_mode,
            callback_group=self.callback_group,
        )

        ### Topic Subscribers ###

        self.subscription = self.create_subscription(
            State,
            STATE_MAVROS_TOPIC_NAME,
            self.state_callback,
            10)
        self.subscription

        ### Other Setup ###

        self._previous_mode = None
        self._mode = None
        self.get_logger().info("Mode Controller Helper is ready")

    def set_loiter_mode(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        self.get_logger().info("Start setting LOITER mode")
        self._previous_mode = self._mode
        return self._set_mode(response, LOITER_MODE)
    
    def set_previous_mode(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        self.get_logger().info(f"Start setting previous mode {self._previous_mode}")
        if self._previous_mode is not None:
            res = self._set_mode(response, self._previous_mode)
            self._previous_mode = None
            return res
        else:
            response.success = False
            return response
        
    def state_callback(self, msg: State) -> None:
        self._mode = msg.mode

    def _set_mode(self, response: Trigger.Response, mode: str) -> Trigger.Response:
        try:
            setmode_request = SetMode.Request()
            setmode_request.custom_mode = mode
            self._run_service_from_callback(self.set_mode_service_client, setmode_request)
            response.success = True
        except Exception as e:
            self.get_logger().error(f"Setting LOITER mode service faild with error {e}")
            response.success = False
        finally:
            return response

    def _run_service_from_callback(self, service_client: Client, request):
        self.service_done_event.clear()
        event = Event()

        def done_callback(future):
            nonlocal event
            event.set()

        future = service_client.call_async(request)
        future.add_done_callback(done_callback)
        event.wait()
        return future.result()



def main():
    try:
        rclpy.init()
        minimal_service = ModeControllerNode()
        executor = MultiThreadedExecutor()
        rclpy.spin(minimal_service, executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
