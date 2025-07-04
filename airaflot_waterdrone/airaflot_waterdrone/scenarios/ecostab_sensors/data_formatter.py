import typing as tp
import time
import json
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Subscription, Timer, Service
from std_srvs.srv import Trigger

from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor

from sensor_msgs.msg import NavSatFix
from airaflot_msgs.msg import NMEAGPGGA, EcostabSensors, DataToSend, ScenarioStateMsg
from airaflot_msgs.srv import WaterSamplerMotor, WaterSampler
from airaflot_waterdrone.mavros_helpers.mission_listener import MissionListener
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn, LifecyclePublisher
from airaflot_waterdrone.mavros_helpers.rc_listener import RCListenerHelper
from airaflot_waterdrone.mavros_helpers.service_client import ServiceClientHelper

from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from ...const_names import (
    ECOSTAB_SENSORS_TOPIC_NAME,
    GPS_EXTERNAL_DATA_TOPIC_NAME,
    DATA_TO_SEND_TOPIC_NAME,
    DOWN_WATER_SAMPLER_MOTOR_SERVICE_NAME,
    UP_WATER_SAMPLER_MOTOR_SERVICE_NAME,
    SET_LOITER_MODE_SERVICE_NAME,
    SET_PREVIOUS_MODE_SERVICE_NAME,
    SCENARIO_STATE_TOPIC_NAME,
    USE_EXTERNAL_GPS_PARAM,
    MEASUREMENT_INTERVAL_PARAM,
    MEASUREMENT_DELAY_PARAM,
    DEFAULT_DEPTH_PARAM,
    START_MEASURE_SERVICE_NAME
)

NODE_NAME = "ecostab_sensors_scenario"
DEFAULT_DEPTH = 30

GPS_INTERNAL_DATA_TOPIC_NAME = "/mavros/global_position/global"

class SensorsDataFormatter(LifecycleNode):
    def __init__(self):
        super().__init__(NODE_NAME)

        self.send_data_callback_group = ReentrantCallbackGroup()
        self.send_state_callback_group = ReentrantCallbackGroup()
        self.service_callback_group = ReentrantCallbackGroup()

        self.start_measure_service: tp.Optional[Service] = None
        self.sensors_subscription: tp.Optional[Subscription] = None
        self.gps_subscription: tp.Optional[Subscription] = None
        self.rc_listener: tp.Optional[RCListenerHelper] = None
        self.mission_listener: tp.Optional[MissionListener] = None
        self.down_motor_service_client: tp.Optional[ServiceClientHelper] = None
        self.up_motor_service_client: tp.Optional[ServiceClientHelper] = None
        self.set_loiter_mode_client: tp.Optional[ServiceClientHelper] = None
        self.set_previous_mode_client: tp.Optional[ServiceClientHelper] = None

        self.state_publisher: tp.Optional[LifecyclePublisher] = None

        self.publisher: tp.Optional[LifecyclePublisher] = None
        self.timer: tp.Optional[Timer] = None
        self.state_timer: tp.Optional[Timer] = None

        self.is_measure: bool = False
        self.message_position: int | None = None

        ### Other Setup ###
        self._state = ScenarioStateMsg.WAIT_FOR_COMMAND
        self.declare_parameter(USE_EXTERNAL_GPS_PARAM, False)
        self.declare_parameter(MEASUREMENT_INTERVAL_PARAM, 5)
        self.declare_parameter(MEASUREMENT_DELAY_PARAM, 30)
        self.measurement_delay = 30
        self.last_sensors_data: tp.Dict = self._format_sensors_data()
        self.last_gps_data: tp.Dict = self._format_gps_data()
        self.default_depth = DEFAULT_DEPTH
        self.declare_parameter(DEFAULT_DEPTH_PARAM, DEFAULT_DEPTH)
        self.get_logger().info("Ecostab Sensors Scenario is unconfigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.default_depth = self.get_parameter(DEFAULT_DEPTH_PARAM).get_parameter_value().integer_value
        self.sensors_subscription = self.create_subscription(
            EcostabSensors, ECOSTAB_SENSORS_TOPIC_NAME, self.sensors_listener, 10, callback_group=self.send_data_callback_group
        )
        self.measurement_delay = self.get_parameter(MEASUREMENT_DELAY_PARAM).get_parameter_value().integer_value
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
        self.rc_listener = RCListenerHelper(self, self._start_measure)
        self.mission_listener = MissionListener(self, self._start_measure)
        self.publisher = self.create_lifecycle_publisher(DataToSend, DATA_TO_SEND_TOPIC_NAME, 10)

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

        self.start_measure_service = self.create_service(
            WaterSampler,
            START_MEASURE_SERVICE_NAME,
            self._service_callback,
            callback_group=self.service_callback_group,
        )

        self.start_measure_client = ServiceClientHelper(self, WaterSampler, START_MEASURE_SERVICE_NAME)

        self.state_publisher = self.create_lifecycle_publisher(ScenarioStateMsg, SCENARIO_STATE_TOPIC_NAME, 10)
        self.state_timer = self.create_timer(1, self.state_timer_callback, callback_group=self.send_state_callback_group)
        
        timer_period = self.get_parameter(MEASUREMENT_INTERVAL_PARAM).get_parameter_value().integer_value
        self.timer = self.create_timer(timer_period, self.timer_callback, callback_group=self.send_data_callback_group)
        self.get_logger().info("Ecostab Sensors Scenario is configured")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.get_logger().info("Ecostab Sensors Scenario cleanup")
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.get_logger().info("Ecostab Sensors Scenario shutdown")
        return TransitionCallbackReturn.SUCCESS
    
    def start_measure(self, depth: tp.Optional[int] = None) -> None:
        depth = depth if depth else self.default_depth
        self.get_logger().info(f"Start measure with depth: {depth}")
        self._state = ScenarioStateMsg.WORK
        try:
            self.set_loiter_mode_client.call_from_callback(Trigger.Request())
            distance = depth
            self.get_logger().info(f"")
            motor_request = self._create_motor_service_request(distance)
            self.down_motor_service_client.call_from_callback(motor_request)
            # self.is_measure = True
            self.message_position = DataToSend.MESSAGE_POS_START
            self.get_logger().info(f"Wait for delay: {self.measurement_delay}")
            time.sleep(self.measurement_delay)
            # self.is_measure = False
            self.message_position = DataToSend.MESSAGE_POS_LAST
            self.up_motor_service_client.call_from_callback(motor_request)
            self.get_logger().info("Measurement finished")
        except Exception as e:
            self.get_logger().error(f"Measurement failed with error {e}")
        finally:
            self.set_previous_mode_client.call_from_callback(Trigger.Request())
            self._state = ScenarioStateMsg.WAIT_FOR_COMMAND

    def _start_measure(self, depth: tp.Optional[int] = None) -> None:
        if self._state == ScenarioStateMsg.WAIT_FOR_COMMAND:
            request = WaterSampler.Request()
            request.depth = depth if depth else self.default_depth
            self.start_measure_client._client.call_async(request)

    def sensors_listener(self, msg: EcostabSensors) -> None:
        self.last_sensors_data = self._format_sensors_data(msg)

    def gps_listener(self, msg: tp.Union[NavSatFix, NMEAGPGGA]) -> None:
        self.last_gps_data = self._format_gps_data(msg)

    def state_timer_callback(self) -> None:
        msg = ScenarioStateMsg()
        if self.state_publisher is not None and self.state_publisher.is_activated:
            msg.node_name = NODE_NAME
            msg.state = self._state
            self.state_publisher.publish(msg)

    def timer_callback(self) -> None:
        if self.publisher and self.publisher.is_activated and self.message_position is not None:
            self.get_logger().info(f"Send data to data_to_send, message pos: {self.message_position}")
            data_to_send = self._create_data_to_send_msg(self.message_position)
            self.publisher.publish(data_to_send)
            if self.message_position == DataToSend.MESSAGE_POS_START:
                self.message_position = DataToSend.MESSAGE_POS_CONTINUE
            elif self.message_position == DataToSend.MESSAGE_POS_LAST:
                self.message_position = None

    def _service_callback(self, request: WaterSampler.Request, response: WaterSampler.Response):
        self.get_logger().info(f"Run start_measure service with depth {request.depth}")
        self.start_measure(request.depth)
        response.success = True
        return response

    def _format_sensors_data(
        self, sensors_msg: tp.Optional[EcostabSensors] = None
    ) -> tp.Dict:
        data = {"temperature": 0.0, "ph": 0.0, "conductivity": 0.0, "orp": 0.0, "oxxygen": 0.0, "oxxygen_saturation": 0.0, "salinity": 0.0, "salinity_tds": 0.0, "no2": 0.0, "no3": 0.0}
        if sensors_msg is not None:
            data["temperature"] = sensors_msg.temperature
            data["conductivity"] = sensors_msg.conductivity
            data["orp"] = sensors_msg.orp
            data["ph"] = sensors_msg.ph
            data["oxxygen"] = sensors_msg.oxxygen
            data["oxxygen_saturation"] = sensors_msg.oxxygen_saturation
            data["salinity"] = sensors_msg.salinity
            data["salinity_tds"] = sensors_msg.salinity_tds
            data["no2"] = sensors_msg.no2
            data["no3"] = sensors_msg.no3
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

    def _create_data_to_send_msg(self, message_position: int = DataToSend.MESSAGE_POS_CONTINUE) -> DataToSend:
        data_to_send = DataToSend()
        data_to_send.timestamp = time.time()
        data_to_send.longitude = self.last_gps_data["longitude"]
        data_to_send.latitude = self.last_gps_data["latitude"]
        data_to_send.altitude = self.last_gps_data["altitude"]
        data_to_send.message_position = message_position
        data_to_send.sensors_data = json.dumps(self.last_sensors_data)
        return data_to_send
    
    def _create_motor_service_request(self, distance: int) -> WaterSamplerMotor.Request:
        request = WaterSamplerMotor.Request()
        request.distance_cm = distance
        return request
    
    def _cleanup(self) -> None:
        self.destroy_lifecycle_publisher(self.publisher)
        self.destroy_subscription(self.gps_subscription)
        self.destroy_subscription(self.sensors_subscription)
        self.destroy_timer(self.timer)
        self.destroy_timer(self.state_timer)
        self.destroy_lifecycle_publisher(self.state_publisher)
        self.destroy_service(self.start_measure_service)
        self.down_motor_service_client.destroy()
        self.up_motor_service_client.destroy()
        self.set_loiter_mode_client.destroy()
        self.set_previous_mode_client.destroy()
        self.rc_listener.destroy()
        self.mission_listener.destroy()
        self.start_measure_client.destroy()
        self.is_measure: bool = False
        self.last_sensors_data: tp.Dict = self._format_sensors_data()
        self.last_gps_data: tp.Dict = self._format_gps_data()



def main(args=None):
    try:
        rclpy.init(args=args)
        minimal_subscriber = SensorsDataFormatter()

        executor = MultiThreadedExecutor()
        rclpy.spin(minimal_subscriber, executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
