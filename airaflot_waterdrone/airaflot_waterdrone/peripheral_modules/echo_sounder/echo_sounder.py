import serial
import time
import rclpy

from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException

from rclpy.lifecycle import LifecycleNode, LifecyclePublisher, LifecycleState, TransitionCallbackReturn

from airaflot_msgs.msg import NMEADBT
from rclpy.timer import Timer
import serial.tools.list_ports

from ..config_wiring import ECHOSOUNDER_PORT
from ...const_names import ECHOSOUNDER_DATA_TOPIC

NODE_NAME = "echo_sounder"

START_COMMAND = "start\r\n".encode()
STOP_COMMAND = "stop\r\n".encode()
INFO_COMMAND = "info\r\n".encode()
TIMER_PERIOD = 0.5

class EchoSounder(LifecycleNode):
    def __init__(self) -> None:
        super().__init__(NODE_NAME)
        self.serial: serial.Serial | None = None
        self.publisher: LifecyclePublisher | None = None
        self.timer: Timer | None = None
        self.logger = self.get_logger()
        self.logger.info("Echo Sounder is unconfigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        try:
            port = self._find_port()
            self.logger.info(f"Found port for Echo Sounder: {port}")
            if port is None:
                return TransitionCallbackReturn.FAILURE

            self.serial : serial.Serial | None = serial.Serial(port, 115200, timeout=0.1)
            self.publisher = self.create_lifecycle_publisher(
                NMEADBT, ECHOSOUNDER_DATA_TOPIC, 10
            )

            self._send_start_command()
            self.timer = self.create_timer(TIMER_PERIOD, self.publish_data)
            
            self.logger.info("Echo Sounder is configured")
        except Exception as e:
            self.logger.error(f"Exception in configure: {e}")
        return TransitionCallbackReturn.SUCCESS
    
    
    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.logger.info('Echo Sounder on_cleanup()')
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.logger.info('Echo Sounder on_shutdown()')
        return TransitionCallbackReturn.SUCCESS

    def publish_data(self) -> None:
        self.logger.debug(f"In waiting: {self.serial.in_waiting}")
        if self.serial.in_waiting > 7:
            nmea_string = self.serial.readline().decode()
            self.logger.debug(f"New string: {nmea_string}")
            if nmea_string.startswith("$SDDBT"):
                nmea_message = self._parse_nmea_string(nmea_string)
                self.publisher.publish(nmea_message)

    def _parse_nmea_string(self, nmea_string: str) -> NMEADBT:
        nmea_string = nmea_string.split(",")
        nmea_message = NMEADBT()
        nmea_message.foots = float(nmea_string[1]) if nmea_string[1] else 0.0
        nmea_message.meters = float(nmea_string[3]) if nmea_string[3] else 0.0
        nmea_message.fatoms = float(nmea_string[5]) if nmea_string[5] else 0.0
        return nmea_message

    def _send_start_command(self) -> None:
        self.logger.info("Send start echo sounder request")
        self.serial.write(START_COMMAND)
    
    def _send_stop_command(self) -> None:
        self.logger.info("Send stop echo sounder request")
        self.serial.write(STOP_COMMAND)


    def _find_port(self) -> str:
        ports = serial.tools.list_ports.comports()
        port_names = [port.device for port in ports if "USB" in port.device]
        self.logger.info(f"Available ports: {port_names}")
        for port in port_names:
            self.logger.info(f"Check port: {port}")
            ser = serial.Serial(port, 115200, timeout=0.1)
            time.sleep(0.5)
            ser.write(INFO_COMMAND)
            time.sleep(0.5)
            self.logger.info(f"in waiting: {ser.in_waiting}")
            while ser.in_waiting:
                res = ser.readline().decode()
                self.logger.info(f"Got message: {res}")
                if "info" in res:
                    ser.close()
                    return port
            ser.close()
                
    def _cleanup(self) -> None:
        self._send_stop_command()
        self.serial.close()
        self.serial = None
        self.destroy_lifecycle_publisher(self.publisher)
        self.destroy_timer(self.timer)

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