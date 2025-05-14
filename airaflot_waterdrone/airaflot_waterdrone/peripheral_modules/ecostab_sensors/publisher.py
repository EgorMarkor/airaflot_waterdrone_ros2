import rclpy
import typing as tp
import time
import pymodbus.client as ModbusClient
from pymodbus.register_read_message import ReadHoldingRegistersResponse

from rclpy.lifecycle import LifecycleNode, LifecyclePublisher, LifecycleState, TransitionCallbackReturn
from rclpy.timer import Timer
import serial.tools.list_ports

from airaflot_msgs.msg import EcostabSensors

from .sensors import Sensor, pHSensor, ConductivitySensor, ORPSensor, OxxygenSensor, EmulateSensor, NitriteSensor
from ...const_names import ECOSTAB_SENSORS_TOPIC_NAME, EMULATE_SENSORS_PARAM
from ..config_wiring import ECOSTAB_SENSORS_PORT
from ..config import EMULATE_ECOSTAB_SENSORS

NODE_NAME = "ecostab_sensors"

class EcostabSensorsNode(LifecycleNode):

    def __init__(self, **kwargs):
        self.sensors: list = []
        self.publisher: tp.Optional[LifecyclePublisher] = None
        self.timer: tp.Optional[Timer] = None
        self.modbus_client: tp.Optional[ModbusClient.ModbusSerialClient] = None
        super().__init__(NODE_NAME, **kwargs)
        self.declare_parameter(EMULATE_SENSORS_PARAM, False)
        self.supported_sensors: list[Sensor] = [ConductivitySensor(), ORPSensor(), OxxygenSensor(), pHSensor(), NitriteSensor()]
        for sensor in self.supported_sensors:
            self.declare_parameter(sensor.use_param, True)
        self.get_logger().info("Ecostab sensors publisher is unconfigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        emulate_sensors = self.get_parameter(EMULATE_SENSORS_PARAM).get_parameter_value().bool_value
        self.get_logger().info(f"Start configure Ecostab Sensors Publisher, emulate_sensors: {emulate_sensors}")
        if emulate_sensors:
            self.sensors: tp.List[Sensor] = [EmulateSensor()]
        else:
            for sensor in self.supported_sensors:
                if self.get_parameter(sensor.use_param).get_parameter_value().bool_value:
                    self.sensors.append(sensor)
                    self.get_logger().info(f"Sensor {sensor.name} will be used")
            port = self._find_port(self.sensors[0])
            self.get_logger().info(f"Found port: {port}")
            if port is None:
                return TransitionCallbackReturn.FAILURE
            time.sleep(0.1)
            self.modbus_client = ModbusClient.ModbusSerialClient(
                port, baudrate=9600, bytesize=8, stopbits=1
            )  
        for sensor in self.sensors:
            try:
                time.sleep(0.1)
                self.get_logger().info(f"Start check sensor {sensor.name}")
                sensor.activate(self.modbus_client)
                sensor.fetch(EcostabSensors())
                time.sleep(0.1)
            except Exception as e:
                self.get_logger().error(f"Exception in configure sensor {sensor.name}: {e}")
                return TransitionCallbackReturn.FAILURE
        self.get_logger().info(f"Working sensors: {[sensor.name for sensor in self.sensors]}")
        self.publisher = self.create_lifecycle_publisher(EcostabSensors, ECOSTAB_SENSORS_TOPIC_NAME, 10)
        timer_period = 1  # seconds
        self.timer = self.create_timer(timer_period, self.timer_callback)
        self.get_logger().info("Ecostab sensors publisher is configured")
        return TransitionCallbackReturn.SUCCESS
    
    
    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_timer(self.timer)
        self.destroy_publisher(self.publisher)
        if self.modbus_client:
            self.modbus_client.close()
        self.sensors.clear()

        self.get_logger().info('Ecostab sensors publisher on_cleanup()')
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_timer(self.timer)
        self.destroy_publisher(self.publisher)
        if self.modbus_client:
            self.modbus_client.close()
        self.sensors.clear()

        self.get_logger().info('Ecostab sensors publisher on_shutdown()')
        return TransitionCallbackReturn.SUCCESS

    def timer_callback(self):
        msg = EcostabSensors()
        if self.publisher is not None and self.publisher.is_activated:
            for sensor in self.sensors:
                msg = sensor.fetch(msg)
                # self.get_logger().info(f"Sensor: {sensor.name}, values: {msg}")
                time.sleep(0.1)
            self.publisher.publish(msg)
            self.get_logger().info(f"Publishing: {msg}")

    def _find_port(self, sensor: Sensor) -> str:
        ports = serial.tools.list_ports.comports()
        port_names = [port.device for port in ports]
        for port in port_names:
            client = ModbusClient.ModbusSerialClient(port, baudrate=9600, bytesize=8, stopbits=1)
            res = client.read_holding_registers(sensor.registers[0], 2, sensor.slave_id)
            client.close()
            if isinstance(res, ReadHoldingRegistersResponse):
                return port

    # def _create_sensors_list(self) -> None:
    #     use_ph = self.get_parameter(USE_PH_RAPAM).get_parameter_value().bool_value
    #     use_cond = self.get_parameter(USE_CONDUCTIVITY_RAPAM).get_parameter_value().bool_value
    #     use_nitrite = self.get_parameter(USE_NITRITE_RAPAM).get_parameter_value().bool_value
    #     use_orp = self.get_parameter(USE_ORP_RAPAM).get_parameter_value().bool_value
    #     use_oxxygen = self.get_parameter(USE_OXXYGEN_RAPAM).get_parameter_value().bool_value
    #     sensors: tp.List[Sensor] = []
    #     if use_ph:
    #         sensor = pHSensor(self.modbus_client)
    #         try:
    #             sensor.fetch(EcostabSensors())
    #         sensors.append()

def main(args=None):

    rclpy.init(args=args)

    minimal_publisher = EcostabSensorsNode()

    rclpy.spin(minimal_publisher)

    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    minimal_publisher.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()