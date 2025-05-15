from rclpy.node import Node
import typing as tp
from mavros_msgs.msg import RCIn

TASK_1_CHANNEL = 1200
TASK_2_CHANNEL = 1400
TASK_3_CHANNEL = 1600
TASK_4_CHANNEL = 1790

WATER_SAMPLER_CHANNEL_NUMBER = 9
# WATER_SAMPLER_RUN_CHANNEL = 7
WATER_SAMPLER_RUN_CHANNEL = 5
CHANNELS_DIFF = 100
RC_IN_TOPIC_NAME = "/mavros/rc/in"
WATER_SAMPLER_CHANNEL_INDEX = WATER_SAMPLER_CHANNEL_NUMBER - 1
WATER_SAMPLER_RUN_CHANNEL = WATER_SAMPLER_RUN_CHANNEL - 1
DEFAUIL_CHANNEL_VALUE = 1000

class RCListenerHelper:
    def __init__(self, parent_node: Node, command_callback: tp.Callable):
        self.parent_node = parent_node
        self.command_callback = command_callback
        self.subscription = self.parent_node.create_subscription(
            RCIn,
            RC_IN_TOPIC_NAME,
            self._listener_callback,
            10)
        
    def destroy(self) -> None:
        self.parent_node.destroy_subscription(self.subscription)
    
    def _listener_callback(self, msg: RCIn):
        self.parent_node.get_logger().debug(f"Channels: {msg.channels}")
        if len(msg.channels) > 0:
            # self.parent_node.get_logger().debug(f"Channel {WATER_SAMPLER_RUN_CHANNEL}: {msg.channels[WATER_SAMPLER_RUN_CHANNEL]}, Channel {WATER_SAMPLER_CHANNEL_INDEX}: {msg.channels[WATER_SAMPLER_CHANNEL_INDEX]}")
            if abs(msg.channels[WATER_SAMPLER_RUN_CHANNEL] - DEFAUIL_CHANNEL_VALUE) > CHANNELS_DIFF:
                if WATER_SAMPLER_CHANNEL_INDEX < len(msg.channels):
                    depth = self._get_depth(msg.channels[WATER_SAMPLER_CHANNEL_INDEX])
                else:
                    depth = 0
                self.command_callback(depth)

    def _get_depth(self, channel_value: int) -> tp.Optional[int]:
        if abs(channel_value - TASK_1_CHANNEL) < 40:
            return 30
        if abs(channel_value - TASK_2_CHANNEL) < 40:
            return 100
        if abs(channel_value - TASK_3_CHANNEL) < 40:
            return 200
        if abs(channel_value - TASK_4_CHANNEL) < 40:
            return 300
        return None
