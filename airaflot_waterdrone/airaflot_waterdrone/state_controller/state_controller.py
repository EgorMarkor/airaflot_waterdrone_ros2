import time
import rclpy
import queue
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from datetime import datetime, timedelta

from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor

from airaflot_msgs.msg import ScenarioStateMsg

import ros2lifecycle.api

from .node_info import NodeInfo
from .webserver import WebServer
from ..const_names import SCENARIO_STATE_TOPIC_NAME

NODE_NAME = "state_controller"


class StateControllerNode(Node):
    def __init__(self):
        super().__init__(NODE_NAME)
        self.water_sampler_nodes = [
            "/water_sampler_motor",
            "/water_sampler_rele",
            "/water_sampler",
            "/water_sampler_scenario"
        ]
        self.scenario_state = -1
        self.scenario_node_states: dict = {}
        self.nodes: dict[str, NodeInfo] = {}
        self.helper_node_fetch = rclpy.create_node("helper_fetch")
        self.helper_node_call = rclpy.create_node("helper_call")

        self.command_queue = queue.Queue()  # Queue for web commands

        self.timer_fetch_callback_group = MutuallyExclusiveCallbackGroup()
        self.timer_call_callback_group = MutuallyExclusiveCallbackGroup()
        self.timer_check_callback_group = MutuallyExclusiveCallbackGroup()
        self.subscriber_callback_group = MutuallyExclusiveCallbackGroup()
        self.nodes_callback_group = ReentrantCallbackGroup()

        self.last_node_fetch_time = datetime.now()

        self.timer_fetch = self.create_timer(2.0, self.timer_fetch_callback, callback_group=self.timer_fetch_callback_group)
        self.timer_call = self.create_timer(2.0, self.timer_call_callback, callback_group=self.timer_call_callback_group)
        self.timer_check = self.create_timer(2.0, self.timer_check_callback, callback_group=self.timer_check_callback_group)
        self.state_subscriber = self.create_subscription(ScenarioStateMsg, SCENARIO_STATE_TOPIC_NAME, self.state_callback, 10)

        # Start the web server in a separate class.
        self.webserver = WebServer(self.command_queue, self.get_logger().info)
        self.webserver.start()

        self.wait_for_nodes(self.water_sampler_nodes)

    def state_callback(self, data: ScenarioStateMsg) -> None:
        self.scenario_node_states[data.node_name] = data.state
        if self._all_nodes_active():
            self.scenario_state = min(list(self.scenario_node_states.values()))
        else:
            self.scenario_state = -1
        self.webserver.set_scenario_state(self.scenario_state)

    def wait_for_nodes(self, nodes_list: list[str]) -> None:
        nodes_ready = False
        while not nodes_ready:
            self.lifecycle_node_names = ros2lifecycle.api.get_node_names(
                node=self, include_hidden_nodes=True
            )
            self.lc_nodes = [n.full_name for n in self.lifecycle_node_names]
            for node in nodes_list:
                if node not in self.lc_nodes:
                    self.get_logger().info(f"Node is not ready: {node}")
                    break
                else:
                    self.get_logger().info(f"Node is ready: {node}")
            else:
                nodes_ready = True
            time.sleep(3)
        for node in nodes_list:
            self.nodes[node] = NodeInfo(node, self.helper_node_call, self.nodes_callback_group)

    def activate_nodes(self) -> None:
        for node in self.nodes.values():
            self.get_logger().info(f"Configuring {node.full_name}")
            if node.configure():
                self.get_logger().info(f"Activating {node.full_name}")
                node.activate()

    def deactivate_nodes(self) -> None:
        for node in self.nodes.values():
            self.get_logger().info(f"Deactivating {node.full_name}")
            if node.deactivate():
                self.get_logger().info(f"Cleaning up {node.full_name}")
                node.cleanup()
        self.scenario_state = -1
        self.webserver.set_scenario_state(self.scenario_state)

    def timer_check_callback(self):
        if (datetime.now() - self.last_node_fetch_time) > timedelta(seconds = 20):
            self.get_logger().warn("Restart fetch timer")
            self.last_node_fetch_time = datetime.now()
            self.destroy_timer(self.timer_fetch)
            self.timer_fetch = self.create_timer(2.0, self.timer_fetch_callback, callback_group=self.timer_fetch_callback_group)

    def timer_call_callback(self):
        self.get_logger().info("Timer callback: processing web commands.")
        while not self.command_queue.empty():
            command = self.command_queue.get()
            if command == "activate_all":
                self.activate_nodes()
            elif command == "deactivate_all":
                self.deactivate_nodes()
            elif command.startswith("activate:"):
                node_name = command.split(":", 1)[1]
                if node_name in self.nodes:
                    self.get_logger().info(f"Configuring {node_name}")
                    if self.nodes[node_name].configure():
                        self.get_logger().info(f"Activating {node_name}")
                        self.nodes[node_name].activate()
            elif command.startswith("deactivate:"):
                node_name = command.split(":", 1)[1]
                if node_name in self.nodes:
                    self.get_logger().info(f"Deactivationg {node_name}")
                    if self.nodes[node_name].deactivate():
                        self.get_logger().info(f"Cleaning up {node_name}")
                        self.nodes[node_name].cleanup()

    def timer_fetch_callback(self):
        self.get_logger().info("Timer callback: fetch nodes states.")
        self.last_node_fetch_time = datetime.now()
        try:
            self.lifecycle_node_names = ros2lifecycle.api.get_node_names(
                node=self.helper_node_fetch, include_hidden_nodes=True
            )
            self.lc_nodes = [n.full_name for n in self.lifecycle_node_names]
            lifecycle_node_states = ros2lifecycle.api.call_get_states(
                node=self.helper_node_fetch, node_names=self.lc_nodes
            )
            for node in self.nodes.values():
                if not node.update_state(lifecycle_node_states):
                    node.state = "dead"
                self.webserver.set_node_state(node.full_name, node.state)
                self.get_logger().info(f"{node.full_name}: {node.state}")
        except Exception as e:
            self.get_logger().error(f"Timer callback error: {e}")

    def _all_nodes_active(self) -> bool:
        for node in self.water_sampler_nodes:
            if node not in self.nodes or self.nodes[node].state != "active":
                return False
        return True


def main():
    try:
        rclpy.init()
        minimal_service = StateControllerNode()
        executor = MultiThreadedExecutor()
        executor.add_node(minimal_service)
        executor.spin()
        # rclpy.spin(minimal_service, executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
