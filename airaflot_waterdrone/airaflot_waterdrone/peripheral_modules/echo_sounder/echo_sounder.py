import serial
import rclpy

from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException

from airaflot_msgs.msg import NMEADBT
from std_srvs.srv import Trigger

from ..config_wiring import ECHOSOUNDER_PORT
from ...const_names import ECHOSOUNDER_START_SERVICE_NAME, ECHOSOUNDER_STOP_SERVICE_NAME, ECHOSOUNDER_DATA_TOPIC

NODE_NAME = "echo_sounder"

START_COMMAND = "start\r\n".encode()
STOP_COMMAND = "stop\r\n".encode()
TIMER_PERIOD = 0.5

class EchoSounder(Node):
    def __init__(self) -> None:
        super().__init__(NODE_NAME)
        self.serial = serial.Serial(ECHOSOUNDER_PORT, 115200)
        self.start_service = self.create_service(
            Trigger,
            ECHOSOUNDER_START_SERVICE_NAME,
            self._send_start_command,
        )
        self.stop_service = self.create_service(
            Trigger,
            ECHOSOUNDER_STOP_SERVICE_NAME,
            self._send_stop_command,
        )
        self.publisher = self.create_publisher(NMEADBT, ECHOSOUNDER_DATA_TOPIC, 10)
        self.timer = self.create_timer(TIMER_PERIOD, self.publish_data)

    def publish_data(self) -> None:
        self.get_logger().debug(f"In waiting: {self.serial.in_waiting}")
        if self.serial.in_waiting > 7:
            nmea_string = self.serial.readline().decode()
            self.get_logger().debug(f"New string: {nmea_string}")
            if nmea_string.startswith("$SDDBT"):
                nmea_message = self._parse_nmea_string(nmea_string)
                self.publisher.publish(nmea_message)

    def _parse_nmea_string(self, nmea_string: str) -> NMEADBT:
        nmea_string = nmea_string.split(",")
        nmea_message = NMEADBT()
        nmea_message.foots = float(nmea_string[1])
        nmea_message.meters = float(nmea_string[3])
        nmea_message.fatoms = float(nmea_string[5])
        return nmea_message

    def _send_start_command(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        self.get_logger().info("Send start echo sounder request")
        return self._send_request(START_COMMAND, response)
    
    def _send_stop_command(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        self.get_logger().info("Send stop echo sounder request")
        return self._send_request(STOP_COMMAND, response)

    def _send_request(self, request: bytes, response: Trigger.Response) -> Trigger.Response:
        try:
            self.serial.write(request)
            response.success = True
            response.message = "ok"
        except Exception as e:
            self.get_logger().error(f"Exception in sending message: {e}")
            response.success = False
            response.message = f"Exception in sending message: {e}"

        self.get_logger().info("Request sent")
        return response

def main():
    try:
        rclpy.init()
        minimal_service = EchoSounder()
        executor = MultiThreadedExecutor()
        rclpy.spin(minimal_service, executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()