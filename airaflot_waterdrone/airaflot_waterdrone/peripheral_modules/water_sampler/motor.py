import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
import RPi.GPIO as GPIO
from RpiMotorLib import RpiMotorLib
import time

from airaflot_msgs.srv import WaterSamplerMotor

from ..config_wiring import (
    # WATER_SAMPLER_STEP_PIN,
    # WATER_SAMPLER_DIRECTION_PIN,
    # WATER_SAMPLER_MODE_PINS,
    # WATER_SUMPLER_MOTOR_TYPE,
    WATER_SAMPLER_UP_MOTOR_PIN,
    WATER_SAMPLER_DOWN_MOTOR_PIN
)
from ...const_names import DOWN_WATER_SAMPLER_MOTOR_SERVICE_NAME, UP_WATER_SAMPLER_MOTOR_SERVICE_NAME

NODE_NAME = "water_sampler_motor"

GET_SAMPLE_DELAY = 3 * 60 # sec

class WaterSamplerMotorNode(Node):
    def __init__(self):
        super().__init__(NODE_NAME)
        self._setup_gpio()
        # self.motor = RpiMotorLib.A4988Nema(
        #     WATER_SAMPLER_DIRECTION_PIN,
        #     WATER_SAMPLER_STEP_PIN,
        #     WATER_SAMPLER_MODE_PINS,
        #     motor_type=WATER_SUMPLER_MOTOR_TYPE,
        # )
        self.service = self.create_service(
            WaterSamplerMotor, DOWN_WATER_SAMPLER_MOTOR_SERVICE_NAME, self.down_motor
        )
        self.service = self.create_service(
            WaterSamplerMotor, UP_WATER_SAMPLER_MOTOR_SERVICE_NAME, self.up_motor
        )
        self.get_logger().info("Water Sampler Motor is ready")

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
    
    def _setup_gpio(self) -> None:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(WATER_SAMPLER_UP_MOTOR_PIN, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(WATER_SAMPLER_DOWN_MOTOR_PIN, GPIO.OUT, initial=GPIO.LOW)
        # GPIO.setup(WATER_SAMPLER_DIRECTION_PIN, GPIO.OUT)
        # GPIO.setup(WATER_SAMPLER_STEP_PIN, GPIO.OUT)

    def _run_stepper(self, revolutions: float, direction_down: bool) -> None:
        self.get_logger().info(f"Run motor to {revolutions} revolutions {'down' if direction_down else 'up'}")
        # self.motor.motor_go(clockwise=direction_down, steps=int(revolutions*8000), stepdelay=.00012)
        pin = WATER_SAMPLER_DOWN_MOTOR_PIN if direction_down else WATER_SAMPLER_UP_MOTOR_PIN
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(9)
        GPIO.output(pin, GPIO.LOW)
        self.get_logger().info("Motor finished")

    def _get_revolutions(self, distance_cm: int) -> int:
        return distance_cm / 18
    


def main():
    try:
        rclpy.init()
        minimal_service = WaterSamplerMotorNode()
        rclpy.spin(minimal_service)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
