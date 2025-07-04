import time
import rclpy
import queue
import threading
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from datetime import datetime, timedelta
from contextlib import contextmanager

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
        
        # Initialize core components
        self.log_saver = LogSaver(self, LOG_DIR)
        self.current_scenario: ScenarioInfo = current_scenario if current_scenario else SUPPORTED_SCENARIOS[0]
        
        # State management with thread-safe access
        self._state_lock = threading.RLock()  # Reentrant lock for nested access
        self.scenario_state = -1
        self.prev_scenario_state = -1
        self.scenario_node_states: dict = {}
        self.nodes: dict[str, NodeInfo] = {}
        
        # Create helper nodes with error handling
        self.helper_node_fetch = None
        self.helper_node_call = None
        self._create_helper_nodes()
        
        # Command queue for web interface
        self.command_queue = queue.Queue()
        
        # Callback groups - use ReentrantCallbackGroup for most operations to reduce deadlock risk
        self.timer_fetch_callback_group = ReentrantCallbackGroup()
        self.timer_call_callback_group = ReentrantCallbackGroup()
        self.timer_check_callback_group = ReentrantCallbackGroup()
        self.subscriber_callback_group = ReentrantCallbackGroup()
        self.led_strip_callback_group = ReentrantCallbackGroup()
        
        # Timing control
        self.last_node_fetch_time = datetime.now()
        self._fetch_in_progress = threading.Lock()  # Prevent overlapping fetch operations
        
        # Create timers with shorter intervals but protection against overlap
        self.timer_fetch = self.create_timer(1.0, self.timer_fetch_callback, 
                                           callback_group=self.timer_fetch_callback_group)
        self.timer_call = self.create_timer(0.5, self.timer_call_callback, 
                                          callback_group=self.timer_call_callback_group)
        self.timer_check = self.create_timer(5.0, self.timer_check_callback, 
                                           callback_group=self.timer_check_callback_group)
        
        # Subscriber and service client
        self.state_subscriber = self.create_subscription(
            ScenarioStateMsg, SCENARIO_STATE_TOPIC_NAME, self.state_callback, 10, 
            callback_group=self.subscriber_callback_group)
        self.led_strip_mode_client = None
        
        # Web server initialization
        self.webserver = WebServer(self.command_queue, self.get_logger().info, self.log_saver)
        self.webserver.set_current_scenario(self.current_scenario)
        self.webserver.start()
        
        # Initialize nodes for current scenario
        self.wait_for_nodes(self.current_scenario.node_list)

    def _create_helper_nodes(self):
        """Create helper nodes with error handling"""
        try:
            if self.helper_node_fetch:
                self.helper_node_fetch.destroy_node()
            if self.helper_node_call:
                self.helper_node_call.destroy_node()
                
            self.helper_node_fetch = rclpy.create_node("helper_fetch")
            self.helper_node_call = rclpy.create_node("helper_call")
        except Exception as e:
            self.get_logger().error(f"Failed to create helper nodes: {e}")
            raise

    @contextmanager
    def _state_context(self):
        """Context manager for thread-safe state access"""
        self._state_lock.acquire()
        try:
            yield
        finally:
            self._state_lock.release()

    def set_scenario(self, scenario_name: str) -> None:
        """Thread-safe scenario switching"""
        with self._state_context():
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
        """Handle scenario state updates with thread safety"""
        with self._state_context():
            self.scenario_node_states[data.node_name] = data.state
            self.prev_scenario_state = self.scenario_state
            
            if self._all_nodes_active():
                self.scenario_state = min(list(self.scenario_node_states.values()))
            else:
                self.scenario_state = -1
                
            state_changed = self.prev_scenario_state != self.scenario_state
            
        # Log outside of lock to prevent potential deadlock
        self.get_logger().info(f"Scenario states: {self.scenario_node_states}")
        
        if state_changed:
            self._set_led_mode_from_scenario_state()
            
        self.webserver.set_scenario_state(self.scenario_state)

    def wait_for_nodes(self, nodes_list: list[str]) -> None:
        """Initialize nodes list with thread safety"""
        with self._state_context():
            self.nodes.clear()
            for node in nodes_list:
                try:
                    self.nodes[node] = NodeInfo(node, self.helper_node_call)
                except Exception as e:
                    self.get_logger().error(f"Failed to create NodeInfo for {node}: {e}")
                    
        self.get_logger().info(f"New nodes list: {list(self.nodes.keys())}")

    def activate_nodes(self) -> None:
        """Activate all nodes with improved error handling"""
        nodes_to_activate = {}
        with self._state_context():
            nodes_to_activate = dict(self.nodes)
            
        for node_name, node in nodes_to_activate.items():
            try:
                if node.full_name in self.current_scenario.parameters:
                    self.get_logger().info(f"Set parameters for {node.full_name}: {self.current_scenario.parameters[node.full_name]}")
                    node.set_parameters(self.current_scenario.parameters[node.full_name])
                    
                self.get_logger().info(f"Configuring {node.full_name}")
                if node.configure():
                    self.get_logger().info(f"Activating {node.full_name}")
                    node.activate()
                else:
                    self.get_logger().error(f"Failed to configure {node.full_name}")
            except Exception as e:
                self.get_logger().error(f"Error activating {node_name}: {e}")

    def deactivate_nodes(self) -> None:
        """Deactivate all nodes with improved error handling"""
        nodes_to_deactivate = {}
        with self._state_context():
            nodes_to_deactivate = dict(self.nodes)
            
        for node_name, node in nodes_to_deactivate.items():
            try:
                self.get_logger().info(f"Deactivating {node.full_name}")
                if node.deactivate():
                    self.get_logger().info(f"Cleaning up {node.full_name}")
                    node.cleanup()
                else:
                    self.get_logger().error(f"Failed to deactivate {node.full_name}")
            except Exception as e:
                self.get_logger().error(f"Error deactivating {node_name}: {e}")
                
        with self._state_context():
            self.scenario_state = -1
            
        self._set_led_mode_from_scenario_state()
        self.webserver.set_scenario_state(self.scenario_state)

    def timer_check_callback(self):
        """Monitor fetch timer health with better recovery"""
        time_since_fetch = datetime.now() - self.last_node_fetch_time
        if time_since_fetch > timedelta(seconds=15):  # Increased threshold
            self.get_logger().error(f"Fetch timer blocked for {time_since_fetch}")
            # Instead of restarting everything, try to recover more gracefully
            try:
                self._recover_fetch_timer()
            except Exception as e:
                self.get_logger().error(f"Recovery failed: {e}")

    def _recover_fetch_timer(self):
        """Attempt to recover from fetch timer blocking"""
        self.get_logger().warn("Attempting to recover fetch timer")
        
        # Cancel and recreate the fetch timer
        if self.timer_fetch:
            self.destroy_timer(self.timer_fetch)
            
        # Reset fetch time
        self.last_node_fetch_time = datetime.now()
        
        # Recreate timer
        self.timer_fetch = self.create_timer(1.0, self.timer_fetch_callback, 
                                           callback_group=self.timer_fetch_callback_group)
        
        self.get_logger().info("Fetch timer recovery completed")

    def timer_call_callback(self):
        """Process web commands with better error handling"""
        processed_commands = 0
        max_commands_per_cycle = 5  # Prevent blocking
        
        while not self.command_queue.empty() and processed_commands < max_commands_per_cycle:
            try:
                command: str = self.command_queue.get_nowait()
                self._process_command(command)
                processed_commands += 1
            except queue.Empty:
                break
            except Exception as e:
                self.get_logger().error(f"Error processing command: {e}")
                
        if processed_commands > 0:
            self.get_logger().info(f"Processed {processed_commands} web commands")

    def _process_command(self, command: str):
        """Process individual command with error handling"""
        try:
            if command == "activate_all":
                self.activate_nodes()
            elif command == "deactivate_all":
                self.deactivate_nodes()
            elif command.startswith("set_scenario:"):
                self.set_scenario(command.split(":", 1)[1])
            elif command.startswith("activate:"):
                self._activate_single_node(command.split(":", 1)[1])
            elif command.startswith("deactivate:"):
                self._deactivate_single_node(command.split(":", 1)[1])
            elif command.startswith("run_main_service"):
                self._run_main_service()
            elif command.startswith("set_parameters"):
                for node in self.current_scenario.node_list:
                    self.nodes[node].set_parameters(self.current_scenario.parameters[node])
        except Exception as e:
            self.get_logger().error(f"Error processing command '{command}': {e}")

    def _activate_single_node(self, node_name: str):
        """Activate a single node safely"""
        with self._state_context():
            if node_name not in self.nodes:
                self.get_logger().error(f"Node {node_name} not found")
                return
            node = self.nodes[node_name]
            
        try:
            if node.full_name in self.current_scenario.parameters:
                self.get_logger().info(f"Set parameters for {node.full_name}: {self.current_scenario.parameters[node.full_name]}")
                node.set_parameters(self.current_scenario.parameters[node.full_name])
                
            self.get_logger().info(f"Configuring {node_name}")
            if node.configure():
                self.get_logger().info(f"Activating {node_name}")
                node.activate()
        except Exception as e:
            self.get_logger().error(f"Error activating {node_name}: {e}")

    def _deactivate_single_node(self, node_name: str):
        """Deactivate a single node safely"""
        with self._state_context():
            if node_name not in self.nodes:
                self.get_logger().error(f"Node {node_name} not found")
                return
            node = self.nodes[node_name]
            
        try:
            self.get_logger().info(f"Deactivating {node_name}")
            if node.deactivate():
                self.get_logger().info(f"Cleaning up {node_name}")
                node.cleanup()
        except Exception as e:
            self.get_logger().error(f"Error deactivating {node_name}: {e}")

    def _run_main_service(self):
        """Run main service with error handling"""
        try:
            service_client = ServiceClientHelper(
                self, 
                self.current_scenario.main_service_info.type, 
                self.current_scenario.main_service_info.name
            )
            service_client.call_from_callback(self.current_scenario.main_service_info.request)
        except Exception as e:
            self.get_logger().error(f"Error running main service: {e}")

    def timer_fetch_callback(self):
        """Fetch node states with overlap prevention"""
        # Use non-blocking lock to prevent overlapping fetch operations
        if not self._fetch_in_progress.acquire(blocking=False):
            self.get_logger().debug("Fetch operation already in progress, skipping")
            return
            
        try:
            self.last_node_fetch_time = datetime.now()
            self.get_logger().debug("Timer callback: fetch nodes states")
            
            # Get nodes snapshot to avoid holding lock too long
            nodes_snapshot = {}
            with self._state_context():
                nodes_snapshot = dict(self.nodes)
                
            # Fetch states outside of lock
            for node_name, node in nodes_snapshot.items():
                try:
                    node.request_state()
                    self.webserver.set_node_state(node.full_name, node.state)
                    self.get_logger().debug(f"{node.full_name}: {node.state}")
                except Exception as e:
                    self.get_logger().error(f"Error fetching state for {node_name}: {e}")
                    
        except Exception as e:
            self.get_logger().error(f"Timer fetch callback error: {e}")
        finally:
            self._fetch_in_progress.release()

    def _all_nodes_active(self) -> bool:
        """Check if all nodes are active (called within state context)"""
        for node_name in self.current_scenario.node_list:
            if node_name not in self.nodes or self.nodes[node_name].state != "active":
                return False
        return True

    def _set_led_mode_from_scenario_state(self) -> None:
        """Set LED mode based on scenario state with error handling"""
        try:
            self.get_logger().info(f"Setting LED mode for scenario state: {self.scenario_state}")
            
            if not self.led_strip_mode_client:
                self.led_strip_mode_client = ServiceClientHelper(
                    self, LedStripMode, LED_STRIP_SET_MODE_SERVICE
                )
                
            request = LedStripMode.Request()
            if self.scenario_state == -1:
                request.mode = LedStripMode.Request.NOT_READY
            elif self.scenario_state == ScenarioStateMsg.WORK:
                request.mode = LedStripMode.Request.PROCESS
            elif self.scenario_state == ScenarioStateMsg.WAIT_FOR_COMMAND:
                request.mode = LedStripMode.Request.NORMAL
                
            self.led_strip_mode_client.call_from_callback(request)
        except Exception as e:
            self.get_logger().error(f"Error setting LED mode: {e}")

    def cleanup(self):
        """Clean shutdown of the node"""
        self.get_logger().info("Starting cleanup")
        
        try:
            # Stop web server
            if hasattr(self, 'webserver'):
                self.webserver.stop()
                
            # Cleanup helper nodes
            if self.helper_node_call:
                self.helper_node_call.destroy_node()
            if self.helper_node_fetch:
                self.helper_node_fetch.destroy_node()
                
        except Exception as e:
            self.get_logger().error(f"Error during cleanup: {e}")


def main():
    """Main function with improved error handling and recovery"""
    rclpy.init()
    node = None
    executor = None
    
    try:
        node = StateControllerNode()
        executor = MultiThreadedExecutor(num_threads=4)  # Limit thread count
        
        executor.add_node(node)
        executor.add_node(node.helper_node_fetch)
        executor.add_node(node.helper_node_call)
        
        # Use spin instead of manual loop for better stability
        executor.spin()
        
    except (KeyboardInterrupt, ExternalShutdownException):
        node.get_logger().info("Shutdown requested")
    except Exception as e:
        if node:
            node.get_logger().error(f"Unexpected error: {e}")
    finally:
        # Cleanup
        if node:
            node.cleanup()
        if executor:
            executor.shutdown()
        rclpy.shutdown()


if __name__ == "__main__":
    main()