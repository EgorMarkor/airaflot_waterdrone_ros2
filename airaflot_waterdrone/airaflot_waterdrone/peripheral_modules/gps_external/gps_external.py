import rclpy
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.lifecycle import (
    LifecycleNode,
    LifecyclePublisher,
    LifecycleState,
    TransitionCallbackReturn,
)
from rclpy.subscription import Subscription

from sensor_msgs.msg import NavSatFix

from airaflot_msgs.msg import NMEAGPGGA

from ...const_names import GPS_EXTERNAL_DATA_TOPIC_NAME

NODE_NAME = "gps_external"

# Topic published by mavros with GPS data from Pixhawk
GPS_INTERNAL_DATA_TOPIC_NAME = "/mavros/global_position/global"


class GPSExternalNode(LifecycleNode):
    """Republish Pixhawk GPS data as external GPS."""

    def __init__(self) -> None:
        super().__init__(NODE_NAME)
        self.publisher: LifecyclePublisher | None = None
        self.subscription: Subscription | None = None
        self.get_logger().info("External GPS is unconfigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        try:
            self.publisher = self.create_lifecycle_publisher(
                NMEAGPGGA, GPS_EXTERNAL_DATA_TOPIC_NAME, 10
            )
            self.subscription = self.create_subscription(
                NavSatFix, GPS_INTERNAL_DATA_TOPIC_NAME, self.gps_listener, 10
            )
            self.get_logger().info(
                "External GPS configured to use Pixhawk coordinates"
            )
        except Exception as e:  # pragma: no cover - defensive programming
            self.get_logger().error(f"Exception in configure: {e}")
            return TransitionCallbackReturn.FAILURE
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_lifecycle_publisher(self.publisher)
        self.destroy_subscription(self.subscription)
        self.get_logger().info("External GPS on_cleanup()")
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_lifecycle_publisher(self.publisher)
        self.destroy_subscription(self.subscription)
        self.get_logger().info("External GPS on_shutdown()")
        return TransitionCallbackReturn.SUCCESS

    def gps_listener(self, msg: NavSatFix) -> None:
        """Convert NavSatFix to NMEAGPGGA and publish."""

        if self.publisher is None:  # pragma: no cover - defensive programming
            return

        nmea_msg = NMEAGPGGA()
        nmea_msg.timestamp = self.get_clock().now().nanoseconds / 1e9
        nmea_msg.latitude = msg.latitude
        nmea_msg.latitude_dir = "N" if msg.latitude >= 0 else "S"
        nmea_msg.longitude = msg.longitude
        nmea_msg.longitude_dir = "E" if msg.longitude >= 0 else "W"
        nmea_msg.altitude = msg.altitude
        self.publisher.publish(nmea_msg)


def main() -> None:
    try:
        rclpy.init()
        minimal_service = GPSExternalNode()
        executor = MultiThreadedExecutor()
        rclpy.spin(minimal_service, executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()

