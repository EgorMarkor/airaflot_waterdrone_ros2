import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Service
import RPi.GPIO as GPIO
from RpiMotorLib import RpiMotorLib
import time
import typing as tp
import serial
import serial.tools.list_ports
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn

from airaflot_msgs.srv import WaterSamplerMotor

from ...const_names import DOWN_WATER_SAMPLER_MOTOR_SERVICE_NAME, UP_WATER_SAMPLER_MOTOR_SERVICE_NAME, EMULATE_MOTOR_PARAM

NODE_NAME = "water_sampler_motor"

class WaterSamplerMotorNode(LifecycleNode):
    def __init__(self):
        super().__init__(NODE_NAME)
        self.service_up: tp.Optional[Service] = None
        self.service_down: tp.Optional[Service] = None
        self.serial: tp.Optional[serial.Serial] = None
        self._emulate = False
        self.declare_parameter(EMULATE_MOTOR_PARAM, False)
        self.get_logger().info("Water Sampler Motor is uncofigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._emulate = self.get_parameter(EMULATE_MOTOR_PARAM).get_parameter_value().bool_value
        self.get_logger().info(f"Start configure Water Sampler Motor, emulate: {self._emulate}")
        if not self._emulate:
            port = self._find_port()
            if port is None:
                self.get_logger().error("Can't find Arduino port for motor")
                return TransitionCallbackReturn.FAILURE
            self.get_logger().info(f"Found arduino port {port}")
            self._setup_serial(port)
        self.service_up = self.create_service(
            WaterSamplerMotor, DOWN_WATER_SAMPLER_MOTOR_SERVICE_NAME, self.down_motor
        )
        self.service_down = self.create_service(
            WaterSamplerMotor, UP_WATER_SAMPLER_MOTOR_SERVICE_NAME, self.up_motor
        )
        self.get_logger().info("Water Sampler Motor is cofigured")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_service(self.service_down)
        self.destroy_service(self.service_up)

        self.get_logger().info("Water Sampler Motor cleanup")
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_service(self.service_down)
        self.destroy_service(self.service_up)

        self.get_logger().info("Water Sampler Motor shutdown")
        return TransitionCallbackReturn.SUCCESS

    def down_motor(self, request, response):
        self.get_logger().info(f"Run water sampler motor down to {request.distance_cm} cm")
        try:
            revolutions = self._get_revolutions(request.distance_cm)
            self._run_stepper(revolutions, direction_down=True)
            response.success = True
        except Exception as e:
            self.get_logger().error(f"Run motor down service faild with error {e}")
            response.success = False
        finally:
            self.get_logger().info("Finished")
            return response
        
    def up_motor(self, request, response):
        self.get_logger().info(f"Run water sampler motor up to {request.distance_cm} cm")
        try:
            revolutions = self._get_revolutions(request.distance_cm)
            self._run_stepper(revolutions, direction_down=False)
            response.success = True
        except Exception as e:
            self.get_logger().error(f"Run motor up service faild with error {e}")
            response.success = False
        finally:
            self.get_logger().info("Finished")
            return response
    
    def _setup_serial(self, port: str) -> None:
        self.serial = serial.Serial(port, baudrate=9600, timeout=1)

    def _run_stepper(self, revolutions: float, direction_down: bool) -> None:
        self.get_logger().info(f"Run motor to {revolutions} revolutions {'down' if direction_down else 'up'}")
        if not self._emulate:
            direction = -1 if direction_down else 1
            command = f"{revolutions * direction * 40}\n"
            self.serial.write(command.encode())
            time.sleep(1)
            res = self.serial.readline().decode().strip()
            while res != "DONE":
                self.get_logger().info(res)
                res = self.serial.readline().decode().strip()
        self.get_logger().info("Motor finished")

    def _get_revolutions(self, distance_cm: int) -> int:
        return distance_cm / 18

    def _find_port(self) -> tp.Optional[str]:
        ports = serial.tools.list_ports.comports()
        port_names = [port.device for port in ports]
        for port in port_names:
            if "USB" in port:
                ser = serial.Serial(port, baudrate=9600, timeout=2)
                time.sleep(2)
                self.get_logger().info(f"Check port {port}")
                ser.write(b"CHECK\n")
                res = ser.readline().decode().strip()
                ser.close()
                self.get_logger().info(res)
                if res == "ARDUINO":
                    return port
    


def main():
    try:
        rclpy.init()
        minimal_service = WaterSamplerMotorNode()
        rclpy.spin(minimal_service)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
