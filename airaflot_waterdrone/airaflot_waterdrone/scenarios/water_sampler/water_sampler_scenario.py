import typing as tp
import rclpy
from enum import Enum
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node, Subscription, Client

from mavros_msgs.msg import RCIn
from rclpy.timer import Timer
from airaflot_msgs.srv import WaterSampler
from airaflot_msgs.msg import ScenarioStateMsg, NMEAGPGGA
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn, LifecyclePublisher
from sensor_msgs.msg import NavSatFix

from airaflot_waterdrone.mavros_helpers.rc_listener import RCListenerHelper
from airaflot_waterdrone.mavros_helpers.mission_listener import MissionListener
from ...const_names import RUN_WATER_SAMPLER_SERVICE_NAME, SCENARIO_STATE_TOPIC_NAME, DEFAULT_DEPTH_PARAM

NODE_NAME = "water_sampler_scenario"
RC_IN_TOPIC_NAME = "/mavros/rc/in"
DEFAULT_DEPTH = 30

class RCCommandsController(LifecycleNode):

    def __init__(self):
        super().__init__(NODE_NAME)
        self.rc_listener: tp.Optional[RCListenerHelper] = None
        self.mission_listener: tp.Optional[MissionListener] = None
        self.state_subscription: tp.Optional[Subscription] = None
        self.timer: tp.Optional[Timer] = None
        self.water_sampler_service_client: tp.Optional[Client] = None
        self.state_publisher: tp.Optional[LifecyclePublisher] = None
        self._state: int = ScenarioStateMsg.WAIT_FOR_COMMAND
        self._water_sampler_state: int = ScenarioStateMsg.WAIT_FOR_COMMAND
        self.default_depth = DEFAULT_DEPTH
        self.declare_parameter(DEFAULT_DEPTH_PARAM, DEFAULT_DEPTH)
        self.get_logger().info("Water Sampler Scenario is unconfigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.default_depth = self.get_parameter(DEFAULT_DEPTH_PARAM).get_parameter_value().integer_value
        self.rc_listener = RCListenerHelper(self, self.run_service)
        self.mission_listener = MissionListener(self, self.run_service)
        self.state_subscription = self.create_subscription(ScenarioStateMsg, SCENARIO_STATE_TOPIC_NAME, self.state_callback, 10)
        self.water_sampler_service_client = self.create_client(
            WaterSampler, RUN_WATER_SAMPLER_SERVICE_NAME
        )
        self.state_publisher = self.create_lifecycle_publisher(ScenarioStateMsg, SCENARIO_STATE_TOPIC_NAME, 10)
        timer_period = 1  # seconds
        self.timer = self.create_timer(timer_period, self.timer_callback)
        self.get_logger().info("Water Sampler Scenario is configured")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_client(self.water_sampler_service_client)
        self.rc_listener.destroy()
        self.destroy_lifecycle_publisher(self.state_publisher)
        self.destroy_timer(self.timer)

        self.get_logger().info("Water Sampler Scenario cleanup")
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_client(self.water_sampler_service_client)
        self.rc_listener.destroy()
        self.mission_listener.destroy()
        self.destroy_lifecycle_publisher(self.state_publisher)
        self.destroy_timer(self.timer)

        self.get_logger().info("Water Sampler Scenario shutdown")
        return TransitionCallbackReturn.SUCCESS

    def state_callback(self, data: ScenarioStateMsg) -> None:
        if data.node_name == "water_sampler":
            self._water_sampler_state = data.state
            self._state = self._water_sampler_state

    def timer_callback(self) -> None:
        msg = ScenarioStateMsg()
        if self.state_publisher is not None and self.state_publisher.is_activated:
            msg.node_name = NODE_NAME
            msg.state = self._state
            self.state_publisher.publish(msg)

    def run_service(self, depth: tp.Optional[int] = None):
        if self._water_sampler_state == ScenarioStateMsg.WAIT_FOR_COMMAND:
            depth = depth if depth else self.default_depth
            self.get_logger().info(f"Got command to run Water Sampler service with depth {depth}")
            request = WaterSampler.Request()
            request.depth = depth
            self.water_sampler_service_client.call_async(request)
            self._water_sampler_state = ScenarioStateMsg.WORK



def main(args=None):
    try:
        rclpy.init(args=args)
        minimal_subscriber = RCCommandsController()

        rclpy.spin(minimal_subscriber)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == '__main__':
    main()