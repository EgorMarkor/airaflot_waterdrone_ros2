import rclpy
from rclpy.node import Node

from rclpy.callback_groups import ReentrantCallbackGroup
from lifecycle_msgs.srv import ChangeState, GetState
from lifecycle_msgs.msg import Transition
from airaflot_waterdrone.mavros_helpers.service_client import ServiceClientHelper
from rcl_interfaces.srv import SetParameters
from rcl_interfaces.msg import Parameter


NODE_NAME = "state_controller"

class NodeInfo:
    def __init__(self, full_name: str, helper_node: Node) -> None:
        self.full_name = full_name
        self.helper_node = helper_node
        self.state: str = "unconfigured"
        self._change_state_callback_group = ReentrantCallbackGroup()
        self._get_state_callback_group = ReentrantCallbackGroup()
        self._change_state_client = ServiceClientHelper(self.helper_node, ChangeState, f"{self.full_name}/change_state")
        self._get_state_client = ServiceClientHelper(self.helper_node, GetState, f"{self.full_name}/get_state")
        self._set_param_client = ServiceClientHelper(self.helper_node, SetParameters, f"{self.full_name}/set_parameters")

    def configure(self) -> bool:
        if self.state == "unconfigured":
            res = self._change_state(Transition.TRANSITION_CONFIGURE)
            if res:
                self.state = "inactive"
            return res
        elif self.state == "inactive":
            return True
        else:
            self.helper_node.get_logger().error(f"Error in change state: wrong current state")
            return False

    def activate(self) -> bool:
        if self.state == "inactive":
            res = self._change_state(Transition.TRANSITION_ACTIVATE)
            if res:
                self.state = "active"
            return res
        elif self.state == "active":
            return True
        else:
            self.helper_node.get_logger().error(f"Error in change state: wrong current state")
            return False
    
    def deactivate(self) -> bool:
        if self.state == "active":
            res = self._change_state(Transition.TRANSITION_DEACTIVATE)
            if res:
                self.state = "inactive"
            return res
        elif self.state == "inactive":
            return True
        else:
            self.helper_node.get_logger().error(f"Error in change state: wrong current state")
            return False
    
    def cleanup(self) -> bool:
        if self.state == "inactive":
            res = self._change_state(Transition.TRANSITION_CLEANUP)
            if res:
                self.state = "unconfigured"
            return res
        elif self.state == "unconfigured":
            return True
        else:
            self.helper_node.get_logger().error(f"Error in change state: wrong current state")
            return False

    def request_state(self) -> str:
        if not self._get_state_client.wait_for_service():
            self.helper_node.get_logger().error(f"Error in get state: no service exists")
            self.state = "dead"
            return "dead"
        request = GetState.Request()
        try:
            result = self._get_state_client.call_from_callback(request)
        except Exception as e:
            self.helper_node.get_logger().error(f"Error in get state: {e}")
            self.state = "dead"
            return "dead"
        self.helper_node.get_logger().info(f"GetState Response for {self.full_name}: {result.current_state.label}")
        self.state = result.current_state.label
        return result.current_state.label

    def set_parameters(self, parameters: list[Parameter]) -> bool:
        if not self._set_param_client.wait_for_service():
            self.helper_node.get_logger().error(f"Error in set parameters {parameters}: no service exists")
            return False
        try:
            request = SetParameters.Request()
            request.parameters = parameters
            result: SetParameters.Response = self._set_param_client.call_from_callback(request)
        except Exception as e:
            self.helper_node.get_logger().error(f"Error in set parameters {parameters}: {e}")
            return False
        return True


    def update_state(self, states: dict) -> bool:
        if self.full_name in states:
            self.state = states[self.full_name].label
            return True
        else:
            return False
        
    def _change_state(self, state_id: int) -> bool:
        if not self._change_state_client.wait_for_service():
            self.helper_node.get_logger().error(f"Error in change state: no service exists")
            return False
        request = ChangeState.Request()
        request.transition.id = state_id
        try:
            result = self._change_state_client.call_from_callback(request)
        except Exception as e:
            self.helper_node.get_logger().error(f"Error in change state: {e}")
            return False
        self.helper_node.get_logger().info(f"ChangeState Response for {self.full_name} to {state_id}: {result.success}")
        return result.success