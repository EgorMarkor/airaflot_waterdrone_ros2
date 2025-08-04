from rclpy.node import Node
import typing as tp
from mavros_msgs.msg import WaypointReached, State

WAYPINT_REACHED_TOPIC = "/mavros/mission/reached"
STATE_MAVROS_TOPIC_NAME = "/mavros/state"
AUTO_MODE_NAME = "AUTO"

class MissionListener:
    def __init__(self, parent_node: Node, waypoint_reched_callback: tp.Callable):
        self.parent_node = parent_node
        self._mavros_mode: str = ""
        self.waypoint_reched_callback = waypoint_reched_callback
        self.subscription = self.parent_node.create_subscription(WaypointReached, WAYPINT_REACHED_TOPIC, self._listener_callback, 10)
        self.subscription = self.parent_node.create_subscription(State, STATE_MAVROS_TOPIC_NAME, self._state_listener, 10)

    def destroy(self) -> None:
        self.parent_node.destroy_subscription(self.subscription)
    
    def _listener_callback(self, msg: WaypointReached) -> None:
        self.parent_node.get_logger().info(f"Reached waypoint number: {msg.wp_seq}, in mode: {self._mavros_mode}")
        if self._mavros_mode == AUTO_MODE_NAME:
            self.waypoint_reched_callback()

    def _state_listener(self, msg: State) -> None:
        self._mavros_mode = msg.mode
