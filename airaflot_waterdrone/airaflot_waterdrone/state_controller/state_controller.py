import time
import rclpy
import queue
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from datetime import datetime, timedelta

from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor

from airaflot_msgs.msg import ScenarioStateMsg
from airaflot_msgs.srv import LedStripMode

from airaflot_waterdrone.mavros_helpers.service_client import ServiceClientHelper

from .node_info import NodeInfo
from .webserver import WebServer
from .scenario_info import ScenarioInfo, WaterSamplerScenario, EcostabSensorsScenario, EchoSounderScenario, SUPPORTED_SCENARIOS
from .log_saver import LogSaver
from ..const_names import SCENARIO_STATE_TOPIC_NAME, LED_STRIP_SET_MODE_SERVICE

NODE_NAME = "state_controller"

LOG_DIR = "/home/airaflot/ros_logs"


class StateControllerNode(Node):
    def __init__(self, current_scenario: ScenarioInfo | None = None):
        super().__init__(NODE_NAME)
        self.log_saver = LogSaver(self, LOG_DIR)
        self.current_scenario: ScenarioInfo = current_scenario if current_scenario else SUPPORTED_SCENARIOS[0]
        self.scenario_state = -1
        self.prev_scenario_state = -1
        self.scenario_node_states: dict = {}
        self.nodes: dict[str, NodeInfo] = {}
        self.helper_node_fetch = rclpy.create_node("helper_fetch")
        self.helper_node_call = rclpy.create_node("helper_call")

        self.command_queue = queue.Queue()  # Queue for web commands

        self.timer_fetch_callback_group = MutuallyExclusiveCallbackGroup()
        self.timer_call_callback_group = MutuallyExclusiveCallbackGroup()
        self.timer_check_callback_group = MutuallyExclusiveCallbackGroup()
        self.subscriber_callback_group = MutuallyExclusiveCallbackGroup()
        self.led_strip_callback_group = MutuallyExclusiveCallbackGroup()
        self.nodes_callback_group = ReentrantCallbackGroup()

        self.last_node_fetch_time = datetime.now()

        self.timer_fetch = self.create_timer(2.0, self.timer_fetch_callback, callback_group=self.timer_fetch_callback_group)
        self.timer_call = self.create_timer(2.0, self.timer_call_callback, callback_group=self.timer_call_callback_group)
        self.timer_check = self.create_timer(2.0, self.timer_check_callback, callback_group=self.timer_check_callback_group)
        self.state_subscriber = self.create_subscription(ScenarioStateMsg, SCENARIO_STATE_TOPIC_NAME, self.state_callback, 10, callback_group=self.led_strip_callback_group)
        self.led_strip_mode_client = None

        # Start the web server in a separate class.
        self.webserver = WebServer(self.command_queue, self.get_logger().info, self.log_saver)
        self.webserver.set_current_scenario(self.current_scenario)
        self.webserver.start()

        self.wait_for_nodes(self.current_scenario.node_list)


    def set_scenario(self, scenario_name: str) -> None:
        for scenario in SUPPORTED_SCENARIOS:
            if scenario.name == scenario_name:
                self.current_scenario = scenario
                break
        else:
            self.get_logger().error(f"Unsupported scenario: {scenario_name}")
            return
        self.webserver.clear_nodes_list()
        self.webserver.set_current_scenario(self.current_scenario)
        self.wait_for_nodes(self.current_scenario.node_list)

    def state_callback(self, data: ScenarioStateMsg) -> None:
        self.scenario_node_states[data.node_name] = data.state
        self.prev_scenario_state = self.scenario_state
        self.get_logger().info(f"Scenario states: {self.scenario_node_states}")
        if self._all_nodes_active():
            self.scenario_state = min(list(self.scenario_node_states.values()))
        else:
            self.scenario_state = -1
        if self.prev_scenario_state != self.scenario_state:
            self._set_led_mode_from_scenario_state()
        self.webserver.set_scenario_state(self.scenario_state)

    def wait_for_nodes(self, nodes_list: list[str]) -> None:
        self.nodes.clear()
        for node in nodes_list:
            self.nodes[node] = NodeInfo(node, self.helper_node_call)
        self.get_logger().info(f"New nodes list; {self.nodes}")

    def activate_nodes(self) -> None:
        for node in self.nodes.values():
            if node.full_name in self.current_scenario.parameters:
                node.set_parameters(self.current_scenario.parameters[node.full_name])
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
        self._set_led_mode_from_scenario_state()
        self.webserver.set_scenario_state(self.scenario_state)

    def timer_check_callback(self):
        self.get_logger().error(f"Fetch timer call: {datetime.now() - self.last_node_fetch_time}")
        if (datetime.now() - self.last_node_fetch_time) > timedelta(seconds = 10):
            self.get_logger().error("Fetch timer blocker")
            # # self.helper_node_fetch.
            # self.webserver.stop()
            # self.helper_node_call.destroy_node()
            # self.helper_node_fetch.destroy_node()
            # # self.destroy_node()
            # # self.executor.shutdown()
            # # self.webserver.stop()
            # raise Exception("Can't restart timer")
            # self.get_logger().warn("Restart fetch timer")
            # self.last_node_fetch_time = datetime.now()
            # self.destroy_timer(self.timer_fetch)
            # self.timer_fetch_callback_group = MutuallyExclusiveCallbackGroup()
            # self.helper_node_fetch.destroy_node()
            # time.sleep(1)
            # self.helper_node_fetch = rclpy.create_node("helper_fetch")
            # self.executor.add_node(self.helper_node_fetch)
            # self.timer_fetch = self.create_timer(2.0, self.timer_fetch_callback, callback_group=self.timer_fetch_callback_group)

    def timer_call_callback(self):
        self.get_logger().info("Timer callback: processing web commands.")
        while not self.command_queue.empty():
            command: str = self.command_queue.get()
            if command == "activate_all":
                self.activate_nodes()
            elif command == "deactivate_all":
                self.deactivate_nodes()
            elif command.startswith("set_scenario:"):
                self.set_scenario(command.split(":")[1])
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
            elif command.startswith("run_main_service"):
                service_client = ServiceClientHelper(self, self.current_scenario.main_service_info.type, self.current_scenario.main_service_info.name)
                service_client.call_from_callback(self.current_scenario.main_service_info.request)

    def timer_fetch_callback(self):
        self.get_logger().info("Timer callback: fetch nodes states.")
        self.last_node_fetch_time = datetime.now()
        try:
            for node in self.nodes.values():
                node.request_state()
                self.webserver.set_node_state(node.full_name, node.state)
                self.get_logger().info(f"{node.full_name}: {node.state}")
        except Exception as e:
            self.get_logger().error(f"Timer callback error: {e}")

    def _all_nodes_active(self) -> bool:
        for node in self.current_scenario.node_list:
            if node not in self.nodes or self.nodes[node].state != "active":
                return False
        return True

    def _set_led_mode_from_scenario_state(self) -> None:
        self.get_logger().info(f"Start setting new led mode for {self.scenario_state}")
        if not self.led_strip_mode_client:
            self.led_strip_mode_client = ServiceClientHelper(self, LedStripMode, LED_STRIP_SET_MODE_SERVICE)
        request = LedStripMode.Request()
        if self.scenario_state == -1:
            request.mode = LedStripMode.Request.NOT_READY
        elif self.scenario_state == ScenarioStateMsg.WORK:
            request.mode = LedStripMode.Request.PROCESS
        elif self.scenario_state == ScenarioStateMsg.WAIT_FOR_COMMAND:
            request.mode = LedStripMode.Request.NORMAL
        self.led_strip_mode_client.call_from_callback(request)


def main():
    try:
        rclpy.init()
        minimal_service = StateControllerNode()
        executor = MultiThreadedExecutor()
        executor.add_node(minimal_service)
        # for node in minimal_service.nodes.values():
        executor.add_node(minimal_service.helper_node_fetch)
        executor.add_node(minimal_service.helper_node_call)
        # executor.add_node(minimal_service.helper_node_call)
        # executor.spin()
        while True:
            executor.spin_once()
            if (datetime.now() - minimal_service.last_node_fetch_time) > timedelta(seconds = 10):
                minimal_service.get_logger().info("Restart Webserver node!")
                minimal_service.webserver.stop()
                minimal_service.helper_node_call.destroy_node()
                minimal_service.helper_node_fetch.destroy_node()
                minimal_service.destroy_node()
                current_scenario = minimal_service.current_scenario
                time.sleep(2)
                minimal_service = StateControllerNode(current_scenario)
                executor.add_node(minimal_service)
                executor.add_node(minimal_service.helper_node_fetch)
                executor.add_node(minimal_service.helper_node_call)
        # rclpy.spin(minimal_service, executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
