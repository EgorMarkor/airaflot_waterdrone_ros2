import rclpy
import time
from threading import Event
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node, Client

from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

from airaflot_msgs.srv import WaterSampler, WaterSamplerMotor
from std_srvs.srv import Trigger

from ...mavros_helpers.service_client import ServiceClientHelper

from ...const_names import (
    RUN_WATER_SAMPLER_SERVICE_NAME,
    TRIGGER_RELE_SERVICE_NAME,
    DOWN_WATER_SAMPLER_MOTOR_SERVICE_NAME,
    UP_WATER_SAMPLER_MOTOR_SERVICE_NAME,
    SET_LOITER_MODE_SERVICE_NAME,
    SET_PREVIOUS_MODE_SERVICE_NAME,
)

NODE_NAME = "water_sampler"

GET_SAMPLE_DELAY = 30  # sec


class WaterSamplerNode(Node):
    def __init__(self):
        super().__init__(NODE_NAME)
        self.callback_group = ReentrantCallbackGroup()

        ### Service Clients ###

        self.trigger_servo_service_client = ServiceClientHelper(
            self, Trigger, TRIGGER_RELE_SERVICE_NAME
        )
        # self.open_servo_service_client = ServiceClientHelper(
        #     self, Trigger, OPEN_RELE_SERVICE_NAME
        # )
        self.down_motor_service_client = ServiceClientHelper(
            self, WaterSamplerMotor, DOWN_WATER_SAMPLER_MOTOR_SERVICE_NAME
        )
        self.up_motor_service_client = ServiceClientHelper(
            self, WaterSamplerMotor, UP_WATER_SAMPLER_MOTOR_SERVICE_NAME
        )
        self.set_loiter_mode_client = ServiceClientHelper(
            self, Trigger, SET_LOITER_MODE_SERVICE_NAME
        )
        self.set_previous_mode_client = ServiceClientHelper(
            self, Trigger, SET_PREVIOUS_MODE_SERVICE_NAME
        )

        ### Service Servers ###

        self.service = self.create_service(
            WaterSampler,
            RUN_WATER_SAMPLER_SERVICE_NAME,
            self.run_water_sampler,
            callback_group=self.callback_group,
        )

        ### Other Setup ###

        # self._run_service(self.close_servo_service_client, Trigger.Request())
        # self.close_servo_service_client.call(Trigger.Request())
        self.get_logger().info("Water sampler is ready")

    def run_water_sampler(self, request: WaterSampler.Request, response: WaterSampler.Response):
        self.get_logger().info(f"Run water sampler with mode: {request.mode}")
        try:
            self.set_loiter_mode_client.call_from_callback(Trigger.Request())
            distance = self._get_distance(request.mode)
            motor_request = self._create_motor_service_request(distance)
            self.down_motor_service_client.call_from_callback(motor_request)
            self.get_logger().info(f"Wait for delay: {GET_SAMPLE_DELAY}")
            time.sleep(GET_SAMPLE_DELAY)
            self.trigger_servo_service_client.call_from_callback(Trigger.Request())
            self.up_motor_service_client.call_from_callback(motor_request)
            self.get_logger().info("Water sampler service finished")
            response.success = True
        except Exception as e:
            self.get_logger().error(f"Run water sample service faild with error {e}")
            response.success = False
        finally:
            self.set_previous_mode_client.call_from_callback(Trigger.Request())
            return response

    def _get_distance(self, mode: int) -> int:
        if mode == 1:
            return 30
        elif mode == 2:
            return 100
        elif mode == 3:
            return 200
        elif mode == 4:
            return 300

    def _create_motor_service_request(self, distance: int) -> WaterSamplerMotor.Request:
        request = WaterSamplerMotor.Request()
        request.distance_cm = distance
        return request

    # def _run_service(self, service_client: Client, request):
    #     future = service_client.call_async(request)
    #     rclpy.spin_until_future_complete(self, future)
    #     return future.result()

    # def _run_service_from_callback(self, service_client: Client, request):
    #     self.service_done_event.clear()
    #     event = Event()
    #     def done_callback(future):
    #         nonlocal event
    #         event.set()
    #     future = service_client.call_async(request)
    #     future.add_done_callback(done_callback)
    #     event.wait()
    #     return future.result()



def main():
    try:
        rclpy.init()
        minimal_service = WaterSamplerNode()
        executor = MultiThreadedExecutor()
        rclpy.spin(minimal_service, executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
