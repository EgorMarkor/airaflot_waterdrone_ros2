import typing as tp
import time
import json
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Subscription, Timer, Service
from std_srvs.srv import Trigger

from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from airaflot_msgs.msg import NMEADBT

from sensor_msgs.msg import NavSatFix
from airaflot_msgs.msg import NMEAGPGGA, EcostabSensors, DataToSend, ScenarioStateMsg
from airaflot_msgs.srv import WaterSamplerMotor, WaterSampler
from airaflot_waterdrone.mavros_helpers.mission_listener import MissionListener
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn, LifecyclePublisher
from airaflot_waterdrone.mavros_helpers.rc_listener import RCListenerHelper
from airaflot_waterdrone.mavros_helpers.service_client import ServiceClientHelper

from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from ...const_names import (
    ECHOSOUNDER_DATA_TOPIC,
    GPS_EXTERNAL_DATA_TOPIC_NAME,
    DATA_TO_SEND_TOPIC_NAME,
    SCENARIO_STATE_TOPIC_NAME,
    USE_EXTERNAL_GPS_PARAM,
)

NODE_NAME = "echo_sounder_scenario"

GPS_INTERNAL_DATA_TOPIC_NAME = "/mavros/global_position/global"

class EchoSounderScenarioNode(LifecycleNode):
    def __init__(self):
        super().__init__(NODE_NAME)

        self.send_data_callback_group = ReentrantCallbackGroup()
        self.send_state_callback_group = ReentrantCallbackGroup()

        self.echosounder_subscription: tp.Optional[Subscription] = None
        self.gps_subscription: tp.Optional[Subscription] = None

        self.state_publisher: tp.Optional[LifecyclePublisher] = None

        self.data_publisher: tp.Optional[LifecyclePublisher] = None
        self.timer: tp.Optional[Timer] = None
        self.state_timer: tp.Optional[Timer] = None

        ### Other Setup ###
        self._state = ScenarioStateMsg.WORK
        self.declare_parameter(USE_EXTERNAL_GPS_PARAM, False)
        self.last_echosounder_data: tp.Dict = self._format_echosounder_data()
        self.last_gps_data: tp.Dict = self._format_gps_data()
        self.get_logger().info("Echo Sounder Scenario is unconfigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        try:
            use_external_gps = self.get_parameter(USE_EXTERNAL_GPS_PARAM).get_parameter_value().bool_value
            if use_external_gps:
                self.gps_subscription = self.create_subscription(
                    NMEAGPGGA, GPS_EXTERNAL_DATA_TOPIC_NAME, self.gps_listener, 10, callback_group=self.send_data_callback_group
                )
            else:
                qos_profile = QoSProfile(
                    reliability=ReliabilityPolicy.BEST_EFFORT,
                    durability=DurabilityPolicy.VOLATILE,
                    depth=10
                )
                self.gps_subscription = self.create_subscription(
                    NavSatFix, GPS_INTERNAL_DATA_TOPIC_NAME, self.gps_listener, qos_profile, callback_group=self.send_data_callback_group
                )
            self.echosounder_subscription = self.create_subscription(NMEADBT, ECHOSOUNDER_DATA_TOPIC, self.echosounder_listener, 10)
            self.data_publisher = self.create_lifecycle_publisher(DataToSend, DATA_TO_SEND_TOPIC_NAME, 10)

            self.state_publisher = self.create_lifecycle_publisher(ScenarioStateMsg, SCENARIO_STATE_TOPIC_NAME, 10)
            self.state_timer = self.create_timer(1, self.state_timer_callback, callback_group=self.send_state_callback_group)
            
            timer_period = 0.5
            self.timer = self.create_timer(timer_period, self.timer_callback, callback_group=self.send_data_callback_group)
            self.get_logger().info("Echo Sounder Scenario is configured")
        except Exception as e:
            self.get_logger().error(f'Exception in configure Echo Sounder Scenario: {e}')
            return TransitionCallbackReturn.FAILURE
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.get_logger().info("Echo Sounder Scenario cleanup")
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.get_logger().info("Echo Sounder Scenario shutdown")
        return TransitionCallbackReturn.SUCCESS


    def echosounder_listener(self, msg: EcostabSensors) -> None:
        self.last_echosounder_data = self._format_echosounder_data(msg)

    def gps_listener(self, msg: tp.Union[NavSatFix, NMEAGPGGA]) -> None:
        self.last_gps_data = self._format_gps_data(msg)

    def state_timer_callback(self) -> None:
        msg = ScenarioStateMsg()
        if self.state_publisher is not None and self.state_publisher.is_activated:
            msg.node_name = NODE_NAME
            msg.state = self._state
            self.state_publisher.publish(msg)

    def timer_callback(self) -> None:
        data_to_send = self._create_data_to_send_msg()
        if self.data_publisher and self.data_publisher.is_activated:
            self.data_publisher.publish(data_to_send)

    def _format_echosounder_data(
        self, echosounder_msg: tp.Optional[NMEADBT] = None
    ) -> tp.Dict:
        data = {"depth": 0.0}
        if echosounder_msg is not None:
            data["depth"] = echosounder_msg.meters
        return data

    def _format_gps_data(
        self, gps_msg: tp.Union[NavSatFix, NMEAGPGGA] = None
    ) -> tp.Dict:
        data = {"latitude": 0.0, "longitude": 0.0, "altitude": 0.0}
        if gps_msg is not None:
            data["latitude"] = gps_msg.latitude
            data["longitude"] = gps_msg.longitude
            data["altitude"] = gps_msg.altitude
        return data

    def _create_data_to_send_msg(self) -> DataToSend:
        data_to_send = DataToSend()
        data_to_send.timestamp = time.time()
        data_to_send.longitude = self.last_gps_data["longitude"]
        data_to_send.latitude = self.last_gps_data["latitude"]
        data_to_send.altitude = self.last_gps_data["altitude"]
        data_to_send.sensors_data = json.dumps(self.last_echosounder_data)
        return data_to_send
    
    def _create_motor_service_request(self, distance: int) -> WaterSamplerMotor.Request:
        request = WaterSamplerMotor.Request()
        request.distance_cm = distance
        return request
    
    def _cleanup(self) -> None:
        self.destroy_lifecycle_publisher(self.data_publisher)
        self.destroy_subscription(self.gps_subscription)
        self.destroy_subscription(self.echosounder_subscription)
        self.destroy_timer(self.timer)
        self.destroy_timer(self.state_timer)
        self.destroy_lifecycle_publisher(self.state_publisher)
        self.destroy_lifecycle_publisher(self.data_publisher)
        self.last_echosounder_data: tp.Dict = self._format_echosounder_data()
        self.last_gps_data: tp.Dict = self._format_gps_data()



def main(args=None):
    try:
        rclpy.init(args=args)
        minimal_subscriber = EchoSounderScenarioNode()

        executor = MultiThreadedExecutor()
        rclpy.spin(minimal_subscriber, executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
