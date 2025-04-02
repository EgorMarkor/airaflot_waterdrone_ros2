import typing as tp
import rclpy
from enum import Enum
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node, Subscription, Client

from mavros_msgs.msg import RCIn
from rclpy.timer import Timer
from airaflot_msgs.srv import WaterSampler
from airaflot_msgs.msg import ScenarioStateMsg
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn, LifecyclePublisher

from .config_channels import WATER_SAMPLER_CHANNEL_NUMBER, TASK_1_CHANNEL, TASK_2_CHANNEL, TASK_3_CHANNEL, TASK_4_CHANNEL, CHANNELS_DIFF
from ...const_names import RUN_WATER_SAMPLER_SERVICE_NAME, SCENARIO_STATE_TOPIC_NAME

NODE_NAME = "water_sampler_scenario"
RC_IN_TOPIC_NAME = "/mavros/rc/in"
WATER_SAMPLER_CHANNEL_INDEX = WATER_SAMPLER_CHANNEL_NUMBER - 1

class RCCommandsController(LifecycleNode):

    def __init__(self):
        super().__init__(NODE_NAME)
        self.subscription: tp.Optional[Subscription] = None
        self.timer: tp.Optional[Timer] = None
        self.water_sampler_service_client: tp.Optional[Client] = None
        self.state_publisher: tp.Optional[LifecyclePublisher] = None
        self.current_channel_value = 1000
        self._state: int = ScenarioStateMsg.WAIT_FOR_COMMAND
        self.get_logger().info("Water Sampler Scenario is unconfigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.subscription = self.create_subscription(
            RCIn,
            RC_IN_TOPIC_NAME,
            self.listener_callback,
            10)
        self.water_sampler_service_client = self.create_client(
            WaterSampler, RUN_WATER_SAMPLER_SERVICE_NAME
        )
        self.state_publisher = self.create_lifecycle_publisher(ScenarioStateMsg, SCENARIO_STATE_TOPIC_NAME, 10)
        self.subscription
        timer_period = 1  # seconds
        self.timer = self.create_timer(timer_period, self.timer_callback)
        self.get_logger().info("Water Sampler Scenario is configured")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_client(self.water_sampler_service_client)
        self.destroy_subscription(self.subscription)
        self.destroy_lifecycle_publisher(self.state_publisher)
        self.destroy_timer(self.timer)
        self.current_channel_value = 1000

        self.get_logger().info("Water Sampler Scenario cleanup")
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_client(self.water_sampler_service_client)
        self.destroy_subscription(self.subscription)
        self.destroy_lifecycle_publisher(self.state_publisher)
        self.destroy_timer(self.timer)
        self.current_channel_value = 1000

        self.get_logger().info("Water Sampler Scenario shutdown")
        return TransitionCallbackReturn.SUCCESS

    def timer_callback(self) -> None:
        msg = ScenarioStateMsg()
        if self.state_publisher is not None and self.state_publisher.is_activated:
            msg.node_name = NODE_NAME
            msg.state = self._state
            self.state_publisher.publish(msg)

    def listener_callback(self, msg: RCIn):
        self.get_logger().debug(f"Channels: {msg.channels}")
        if len(msg.channels) > 0:
            self.get_logger().debug(f"Channel 9: {msg.channels[WATER_SAMPLER_CHANNEL_INDEX]}")
            if abs(msg.channels[WATER_SAMPLER_CHANNEL_INDEX] - self.current_channel_value) > CHANNELS_DIFF:
                task_mode = self._get_task_mode(msg.channels[WATER_SAMPLER_CHANNEL_INDEX])
                if task_mode is not None:
                    self.get_logger().info(f"Got command to run Water Sampler service with mode {task_mode}")
                    request = WaterSampler.Request()
                    request.mode = task_mode
                    self.water_sampler_service_client.call_async(request)
            self.current_channel_value = msg.channels[WATER_SAMPLER_CHANNEL_INDEX]

    def _get_task_mode(self, channel_value: int) -> tp.Optional[int]:
        if abs(channel_value - TASK_1_CHANNEL) < 10:
            return 1
        if abs(channel_value - TASK_2_CHANNEL) < 10:
            return 2
        if abs(channel_value - TASK_3_CHANNEL) < 10:
            return 3
        if abs(channel_value - TASK_4_CHANNEL) < 10:
            return 4
        return None


def main(args=None):
    try:
        rclpy.init(args=args)
        minimal_subscriber = RCCommandsController()

        rclpy.spin(minimal_subscriber)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == '__main__':
    main()