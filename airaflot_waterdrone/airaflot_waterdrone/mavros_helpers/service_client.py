from rclpy.node import Node, Client
import rclpy
import typing as tp
from threading import Event

class NoServiceProvided(Exception):
    """Exception raised when a required service is not available."""
    
    def __init__(self, service_name: str, message: str = "No service provided"):
        self.service_name = service_name
        self.message = f"{message}: {service_name}"
        super().__init__(self.message)

class ServiceClientHelper:
    def __init__(self, parent_node: Node, service_msg_type: tp.Any, service_name: str) -> None:
        self.service_done_event = Event()
        self.service_name = service_name
        self._parent_node = parent_node
        self._client: Client = parent_node.create_client(service_msg_type, service_name)
        counter = 0
        while not self._client.wait_for_service(timeout_sec=1.0):
            parent_node.get_logger().info(f"Wait for {service_name} service")
            counter += 1
            if counter > 15:
                raise NoServiceProvided(service_name)
        
    def call(self, request: tp.Any) -> tp.Any:
        self._parent_node.get_logger().info(f"Call {self.service_name}")
        future = self._client.call_async(request)
        rclpy.spin_until_future_complete(self._parent_node, future)
        return future.result()

    def call_from_callback(self, request: tp.Any) -> tp.Any:
        self._parent_node.get_logger().info(f"Call from callback {self.service_name}")
        self.service_done_event.clear()
        self.service_done_event = Event()
        future = self._client.call_async(request)
        future.add_done_callback(self.done_callback)
        self.service_done_event.wait()
        return future.result()

    def destroy(self) -> None:
        self._parent_node.destroy_client(self._client)

    def wait_for_service(self, delay: int = 10) -> bool:
        return self._client.wait_for_service(timeout_sec=delay)

    def done_callback(self, future):
        self.service_done_event.set()