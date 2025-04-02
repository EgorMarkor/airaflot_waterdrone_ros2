import rclpy
from rclpy.node import Node

from rclpy.callback_groups import ReentrantCallbackGroup
from lifecycle_msgs.srv import ChangeState
from lifecycle_msgs.msg import Transition

NODE_NAME = "state_controller"

class NodeInfo:
    def __init__(self, full_name: str, helper_node: Node, callback_group: ReentrantCallbackGroup) -> None:
        self.full_name = full_name
        self.helper_node = helper_node
        self.state: str = "unconfigured"
        self._change_state_client = self.helper_node.create_client(ChangeState, f"{self.full_name}/change_state", callback_group=callback_group)

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

    def update_state(self, states: dict) -> bool:
        if self.full_name in states:
            self.state = states[self.full_name].label
            return True
        else:
            return False
        
    def _change_state(self, state_id: int) -> bool:
        counter = 0
        while not self._change_state_client.wait_for_service(timeout_sec=1.0):
            self.helper_node.get_logger().warn(f'Waiting for {self.full_name} service...')
            counter += 1
            if counter > 10:
                self.helper_node.get_logger().error(f"Error in change state: no service exists")
                return False
        request = ChangeState.Request()
        request.transition.id = state_id
        future = self._change_state_client.call_async(request)
        try:
            rclpy.spin_until_future_complete(self.helper_node, future)
        except Exception as e:
            self.helper_node.get_logger().error(f"Error in change state: {e}")
            return False
        if future.result():
            self.helper_node.get_logger().info(f"ChangeState Response for {self.full_name} to {state_id}: {future.result().success}")
            return future.result().success
        else:
            self.helper_node.get_logger().error(f"Service call for {self.full_name} to {state_id} failed.")
            return False