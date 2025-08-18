import serial
import rclpy
import time
from datetime import datetime, date

from rclpy.lifecycle import LifecycleNode, LifecyclePublisher, LifecycleState, TransitionCallbackReturn

from rclpy.executors import MultiThreadedExecutor
from rclpy.timer import Timer
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException

from airaflot_msgs.msg import NMEAGPGGA
import serial.tools.list_ports

from ...const_names import GPS_EXTERNAL_DATA_TOPIC_NAME

NODE_NAME = "gps_external"

START_COMMAND = "log com1 gpgga ontime 0.1\r\n".encode("ascii")
TIMER_PERIOD = 0.1


class GPSExternalNode(LifecycleNode):
    def __init__(self) -> None:
        super().__init__(NODE_NAME)
        self.serial : serial.Serial | None = None
        self.publisher: LifecyclePublisher | None = None
        self.timer: Timer | None = None
        self.logger = self.get_logger()
        self.get_logger().info("External GPS is unconfigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        try:
            port = self._find_port()
            self.logger.info(f"Found port for external GPS: {port}")
            if port is None:
                return TransitionCallbackReturn.FAILURE

            self.serial : serial.Serial | None = serial.Serial(port, 115200, timeout=0.1)
            self.publisher = self.create_lifecycle_publisher(
                NMEAGPGGA, GPS_EXTERNAL_DATA_TOPIC_NAME, 10
            )

            self._send_start_request()
            self.timer = self.create_timer(TIMER_PERIOD, self.publish_data)
            
            self.get_logger().info("External GPS is configured")
        except Exception as e:
            self.logger.error(f"Exception in configure: {e}")
        return TransitionCallbackReturn.SUCCESS
    
    
    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.get_logger().info('External GPS on_cleanup()')
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.get_logger().info('External GPS on_shutdown()')
        return TransitionCallbackReturn.SUCCESS

    def publish_data(self) -> None:
        self.get_logger().debug(f"In waiting: {self.serial.in_waiting}")
        if self.serial.in_waiting > 7:
            nmea_string = self.serial.readline().decode()
            self.get_logger().debug(f"New string: {nmea_string}")
            if nmea_string.startswith("$GPGGA"):
                nmea_message = self._parse_nmea_string(nmea_string)
                self.publisher.publish(nmea_message)

    def _parse_nmea_string(self, nmea_string: str) -> NMEAGPGGA:
        nmea_string = nmea_string.split(",")
        nmea_message = NMEAGPGGA()
        nmea_message.timestamp = self._get_timestamp(nmea_string[1])
        nmea_message.latitude = (float(nmea_string[2]) / 100) if nmea_string[2] else 0.0
        nmea_message.latitude_dir = nmea_string[3]
        nmea_message.longitude = (float(nmea_string[4]) / 100) if nmea_string[4] else 0.0
        nmea_message.longitude_dir = nmea_string[5]
        nmea_message.altitude = float(nmea_string[9]) if nmea_string[9] else 0.0
        return nmea_message

    def _get_timestamp(self, utc_time_string: str) -> float:
        today = date.today()
        gps_datetime = datetime(
            today.year,
            today.month,
            today.day,
            int(utc_time_string[0:2]),
            int(utc_time_string[2:4]),
            int(utc_time_string[4:6]),
            int(utc_time_string[7:9]),
        )
        return gps_datetime.timestamp()

    def _send_start_request(self) -> None:
        try:
            self.serial.write(START_COMMAND)
        except Exception as e:
            self.get_logger().error(f"Exception in sending message: {e}")

    def _find_port(self) -> str:
        ports = serial.tools.list_ports.comports()
        port_names = [port.device for port in ports if "USB" in port.device]
        self.logger.info(f"Available ports: {port_names}")
        for port in port_names:
            self.logger.info(f"Check port: {port}")
            ser = serial.Serial(port, 115200, timeout=0.1)
            time.sleep(0.5)
            ser.write("log com1 gpgga once\r\n".encode("ascii"))
            time.sleep(0.5)
            self.logger.info(f"in waiting: {ser.in_waiting}")
            while ser.in_waiting:
                res = ser.readline().decode()
                self.logger.info(f"Got message: {res}")
                if res.startswith("$GPGGA"):
                    ser.close()
                    return port
            ser.close()
                
    def _cleanup(self) -> None:
        self.serial.write("unlog gpgga\r\n".encode("ascii"))
        self.serial.close()
        self.serial = None
        self.destroy_lifecycle_publisher(self.publisher)
        self.destroy_timer(self.timer)


def main():
    try:
        rclpy.init()
        minimal_service = GPSExternalNode()
        executor = MultiThreadedExecutor()
        rclpy.spin(minimal_service, executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
