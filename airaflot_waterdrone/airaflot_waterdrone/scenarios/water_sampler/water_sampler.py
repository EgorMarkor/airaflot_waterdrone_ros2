import rclpy
import time
import json
import typing as tp
from threading import Event
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node, Client, Service
from rclpy.timer import Timer
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from sensor_msgs.msg import NavSatFix

from airaflot_msgs.msg import ScenarioStateMsg, DataToSend, NMEAGPGGA
from airaflot_msgs.srv import WaterSampler, WaterSamplerMotor
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn, LifecyclePublisher
from std_srvs.srv import Trigger

from ...mavros_helpers.service_client import ServiceClientHelper

from ...const_names import (
    RUN_WATER_SAMPLER_SERVICE_NAME,
    TRIGGER_RELE_SERVICE_NAME,
    DOWN_WATER_SAMPLER_MOTOR_SERVICE_NAME,
    UP_WATER_SAMPLER_MOTOR_SERVICE_NAME,
    SET_LOITER_MODE_SERVICE_NAME,
    SET_PREVIOUS_MODE_SERVICE_NAME,
    SCENARIO_STATE_TOPIC_NAME,
    DATA_TO_SEND_TOPIC_NAME,
    GPS_EXTERNAL_DATA_TOPIC_NAME,
    USE_EXTERNAL_GPS_PARAM,
    SAMPLING_DELAY_PARAM,
    DEFAULT_DEPTH_PARAM
)

DEFAULT_DEPTH = 30

NODE_NAME = "water_sampler"
GPS_INTERNAL_DATA_TOPIC_NAME = "/mavros/global_position/global"

GET_SAMPLE_DELAY = 30  # sec


class WaterSamplerNode(LifecycleNode):
    def __init__(self):
        super().__init__(NODE_NAME)
        self.callback_group = ReentrantCallbackGroup()
        self.service: tp.Optional[Service] = None
        self.trigger_servo_service_client: tp.Optional[ServiceClientHelper] = None
        self.down_motor_service_client: tp.Optional[ServiceClientHelper] = None
        self.up_motor_service_client: tp.Optional[ServiceClientHelper] = None
        self.set_loiter_mode_client: tp.Optional[ServiceClientHelper] = None
        self.set_previous_mode_client: tp.Optional[ServiceClientHelper] = None
        self.state_publisher: tp.Optional[LifecyclePublisher] = None
        self.sample_point_publisher: tp.Optional[LifecyclePublisher] = None
        self.timer: tp.Optional[Timer] = None
        self._gps_location: dict = {"latitude": 0, "longitude": 0}
        self.declare_parameter(USE_EXTERNAL_GPS_PARAM, False)
        self.declare_parameter(SAMPLING_DELAY_PARAM, 30)
        self.declare_parameter(DEFAULT_DEPTH_PARAM, DEFAULT_DEPTH)
        self.sampling_delay = 30
        self.default_depth = DEFAULT_DEPTH
        self._state: int = ScenarioStateMsg.WAIT_FOR_COMMAND

        self.get_logger().info("Water sampler is unconfigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.default_depth = self.get_parameter(DEFAULT_DEPTH_PARAM).get_parameter_value().integer_value
        self.trigger_servo_service_client = ServiceClientHelper(
            self, Trigger, TRIGGER_RELE_SERVICE_NAME
        )
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
        self.sampling_delay = self.get_parameter(SAMPLING_DELAY_PARAM).get_parameter_value().integer_value
        self.sample_point_publisher = self.create_lifecycle_publisher(DataToSend, DATA_TO_SEND_TOPIC_NAME, 10)
        self.state_publisher = self.create_lifecycle_publisher(ScenarioStateMsg, SCENARIO_STATE_TOPIC_NAME, 10)
        timer_period = 1  # seconds
        self.timer = self.create_timer(timer_period, self.timer_callback)

        use_external_gps = self.get_parameter('use_external_gps').get_parameter_value().bool_value

        if use_external_gps:
            self.gps_subscription = self.create_subscription(
                NMEAGPGGA, GPS_EXTERNAL_DATA_TOPIC_NAME, self.gps_listener, 10
            )
        else:
            qos_profile = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
                depth=10
            )
            self.gps_subscription = self.create_subscription(
                NavSatFix, GPS_INTERNAL_DATA_TOPIC_NAME, self.gps_listener, qos_profile
            )

        self.service = self.create_service(
            WaterSampler,
            RUN_WATER_SAMPLER_SERVICE_NAME,
            self.run_water_sampler,
            callback_group=self.callback_group,
        )
        self.get_logger().info("Water sampler is configured")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.get_logger().info('Water Sampler clean up')
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.get_logger().info('Water Sampler shutdown')
        return TransitionCallbackReturn.SUCCESS

    def gps_listener(self, msg: tp.Union[NavSatFix, NMEAGPGGA]) -> None:
        if msg is not None:
            self._gps_location["latitude"] = msg.latitude
            self._gps_location["longitude"] = msg.longitude

    def timer_callback(self) -> None:
        msg = ScenarioStateMsg()
        if self.state_publisher is not None and self.state_publisher.is_activated:
            msg.node_name = NODE_NAME
            msg.state = self._state
            self.state_publisher.publish(msg)

    def run_water_sampler(self, request: WaterSampler.Request, response: WaterSampler.Response):
        depth = request.depth if request.depth else self.default_depth
        self.get_logger().info(f"Run water sampler with depth: {depth}")
        self._state = ScenarioStateMsg.WORK
        self._send_sample_point_info(depth)
        try:
            self.set_loiter_mode_client.call_from_callback(Trigger.Request())
            distance = depth
            motor_request = self._create_motor_service_request(distance)
            self.down_motor_service_client.call_from_callback(motor_request)
            self.get_logger().info(f"Wait for delay: {self.sampling_delay}")
            time.sleep(self.sampling_delay)
            self.trigger_servo_service_client.call_from_callback(Trigger.Request())
            self.up_motor_service_client.call_from_callback(motor_request)
            self.get_logger().info("Water sampler service finished")
            response.success = True
        except Exception as e:
            self.get_logger().error(f"Run water sample service faild with error {e}")
            response.success = False
        finally:
            self.set_previous_mode_client.call_from_callback(Trigger.Request())
            self._state = ScenarioStateMsg.WAIT_FOR_COMMAND
            return response

    def _create_motor_service_request(self, distance: int) -> WaterSamplerMotor.Request:
        request = WaterSamplerMotor.Request()
        request.distance_cm = distance
        return request

    def _send_sample_point_info(self, depth: int) -> None:
        message = DataToSend()
        message.latitude = self._gps_location["latitude"]
        message.longitude = self._gps_location["longitude"]
        message.timestamp = time.time()
        message.sensors_data = json.dumps({"sampling_depth": depth})
        self.get_logger().info(f"Sending sample depth info: {message}")
        self.sample_point_publisher.publish(message)

    def _cleanup(self) -> None:
        self.destroy_service(self.service)
        self.trigger_servo_service_client.destroy()
        self.down_motor_service_client.destroy()
        self.up_motor_service_client.destroy()
        self.set_loiter_mode_client.destroy()
        self.set_previous_mode_client.destroy()
        self.destroy_lifecycle_publisher(self.state_publisher)
        self.destroy_timer(self.timer)
        self.trigger_servo_service_client = None
        self.down_motor_service_client = None
        self.up_motor_service_client = None
        self.set_loiter_mode_client = None
        self.set_previous_mode_client = None
        self.destroy_subscription(self.gps_subscription)
        self.destroy_lifecycle_publisher(self.sample_point_publisher)
        self._gps_location: dict = {"latitude": 0, "longitude": 0}



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
