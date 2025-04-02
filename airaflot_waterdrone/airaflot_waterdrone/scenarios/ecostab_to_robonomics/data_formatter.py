import typing as tp
import time
import json
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile

from sensor_msgs.msg import NavSatFix
from airaflot_msgs.msg import NMEAGPGGA, EcostabSensors, DataToSend

from ...const_names import (
    ECOSTAB_SENSORS_TOPIC_NAME,
    GPS_EXTERNAL_DATA_TOPIC_NAME,
    DATA_TO_SEND_TOPIC_NAME,
)
from .config import USE_EXTERNAL_GPS, NEW_DATA_INTERVAL

NODE_NAME = "ecostab_to_robonomics_scenario"

GPS_INTERNAL_DATA_TOPIC_NAME = "/mavros/global_position/global"

class SensorsDataFormatter(Node):
    def __init__(self):
        super().__init__(NODE_NAME)

        ### Topic Subscribers ###

        self.sensors_subscription = self.create_subscription(
            EcostabSensors, ECOSTAB_SENSORS_TOPIC_NAME, self.sensors_listener, 10
        )
        self.sensors_subscription  # prevent unused variable warning
        if USE_EXTERNAL_GPS:
            self.gps_subscription = self.create_subscription(
                NMEAGPGGA, GPS_EXTERNAL_DATA_TOPIC_NAME, self.gps_listener, 10
            )
        else:
            self.gps_subscription = self.create_subscription(
                NavSatFix, GPS_INTERNAL_DATA_TOPIC_NAME, self.gps_listener, 10
            )
        self.gps_subscription  # prevent unused variable warning

        ### Topic Publishers ###

        self.publisher = self.create_publisher(DataToSend, DATA_TO_SEND_TOPIC_NAME, 10)
        timer_period = NEW_DATA_INTERVAL  # seconds
        self.timer = self.create_timer(timer_period, self.timer_callback)

        ### Other Setup ###

        self.last_sensors_data: tp.Dict = self._format_sensors_data()
        self.last_gps_data: tp.Dict = self._format_gps_data()

    def sensors_listener(self, msg: EcostabSensors) -> None:
        self.last_sensors_data = self._format_sensors_data(msg)

    def gps_listener(self, msg: tp.Union[NavSatFix, NMEAGPGGA]) -> None:
        self.last_gps_data = self._format_gps_data(msg)

    def timer_callback(self) -> None:
        data_to_send = self._create_data_to_send_msg()
        self.publisher.publish(data_to_send)

    def _format_sensors_data(
        self, sensors_msg: tp.Optional[EcostabSensors] = None
    ) -> tp.Dict:
        data = {"temperature": 0.0, "ph": 0.0, "conductivity": 0.0, "orp": 0.0, "oxxygen": 0.0}
        if sensors_msg is not None:
            data["temperature"] = sensors_msg.temperature
            data["conductivity"] = sensors_msg.conductivity
            data["orp"] = sensors_msg.orp
            data["ph"] = sensors_msg.ph
            data["oxxygen"] = sensors_msg.oxxygen
        return data

    def _format_gps_data(
        self, gps_msg: tp.Union[NavSatFix, NMEAGPGGA] = None
    ) -> tp.Dict:
        data = {"latitude": 0.0, "longitude": 0.0}
        if gps_msg is not None:
            data["latitude"] = gps_msg.latitude
            data["longitude"] = gps_msg.longitude
        return data

    def _create_data_to_send_msg(self) -> DataToSend:
        data_to_send = DataToSend()
        data_to_send.timestamp = time.time()
        data_to_send.longitude = self.last_gps_data["longitude"]
        data_to_send.latitude = self.last_gps_data["latitude"]
        data_to_send.sensors_data = json.dumps(self.last_sensors_data)
        return data_to_send


def main(args=None):
    try:
        rclpy.init(args=args)
        minimal_subscriber = SensorsDataFormatter()

        rclpy.spin(minimal_subscriber)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
