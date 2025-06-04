import rclpy
import time

from rclpy.node import Node, Service
from rclpy.executors import ExternalShutdownException
import RPi.GPIO as GPIO
import pymodbus.client as ModbusClient
from pymodbus.register_read_message import ReadHoldingRegistersResponse
from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn
import serial.tools.list_ports

from std_srvs.srv import Trigger
import typing as tp

from ..config_wiring import WATER_SAMPLER_RELE_PORT
from ...const_names import TRIGGER_RELE_SERVICE_NAME, EMULATE_RELE_PARAM

NODE_NAME = "water_sampler_rele"

CLOSE_POSITION = 10
OPEN_POSITION = 6
OPEN_RELE_DELAY = 1


class WaterSamplerReleNode(LifecycleNode):
    def __init__(self):
        super().__init__(NODE_NAME)
        self.modbus_client: tp.Optional[ModbusClient.ModbusSerialClient] = None
        self.service: tp.Optional[Service] = None
        self._emulate = False
        self.declare_parameter(EMULATE_RELE_PARAM, False)
        self.get_logger().info("Water Sampler Servo is unconfigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._emulate = self.get_parameter(EMULATE_RELE_PARAM).get_parameter_value().bool_value
        self.get_logger().info(f"Start configure Water Sampler Rele, emulate: {self._emulate}")
        if not self._emulate:
            port = self._find_port()
            if port is None:
                self.get_logger().error("Can't find rele port")
                return TransitionCallbackReturn.FAILURE
            self.get_logger().info(f"Found rele port {port}")
            self.modbus_client = ModbusClient.ModbusSerialClient(
                    port, baudrate=9600, bytesize=8, stopbits=1
                )
        self.service = self.create_service(
            Trigger, TRIGGER_RELE_SERVICE_NAME, self.trigger_rele
        )
        self.get_logger().info("Water Sampler Servo is configured")
        return TransitionCallbackReturn.SUCCESS

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_service(self.service)
        if self.modbus_client:
            self.modbus_client.close()

        self.get_logger().info("Water Sampler Servo cleanup")
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_service(self.service)
        if self.modbus_client:
            self.modbus_client.close()

        self.get_logger().info("Water Sampler Servo shutdown")
        return TransitionCallbackReturn.SUCCESS

    def trigger_rele(self, request: Trigger.Request, response: Trigger.Response):
        self.get_logger().info("Start trigger rele")
        try:
            if not self._emulate:
                res = self.modbus_client.write_register(112,1,1)
                self.get_logger().info(f"Open rele: {res}")
                time.sleep(OPEN_RELE_DELAY)
                res = self.modbus_client.write_register(112,0,1)
                self.get_logger().info(f"Close rele: {res}")
            response.success = True
            response.message = "ok"
        except Exception as e:
            self.get_logger().error(f"Open servo service failed with error {e}")
            response.success = False
            response.message = f"Open servo service failed with error {e}"
        finally:
            return response

    def _find_port(self) -> str:
        ports = serial.tools.list_ports.comports()
        port_names = [port.device for port in ports]
        for port in port_names:
            client = ModbusClient.ModbusSerialClient(port, baudrate=9600, bytesize=8, stopbits=1)
            res = client.read_holding_registers(112, 1, 1)
            client.close()
            if isinstance(res, ReadHoldingRegistersResponse):
                return port


def main():
    try:
        rclpy.init()
        minimal_service = WaterSamplerReleNode()
        rclpy.spin(minimal_service)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
