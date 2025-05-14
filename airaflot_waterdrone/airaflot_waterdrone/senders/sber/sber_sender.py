from rclpy.node import Timer, Subscription
import json

from airaflot_msgs.msg import DataToSend
from std_msgs.msg import String

from rclpy.lifecycle import LifecycleNode, LifecyclePublisher, LifecycleState, TransitionCallbackReturn

from ...const_names import FILE_FINISHED_TOPIC_NAME, SBER_URL_PARAM

NODE_NAME = "robonomics"

class SberSenderNode(LifecycleNode):
    def __init__(self):
        super().__init__(NODE_NAME)

        self.file_finished_subscription: Subscription | None = None
        self.timer: Timer | None = None
        self.sber_url: str = ""
        self.declare_parameter(SBER_URL_PARAM, "")
        self.get_logger().info("SberSenderNode is unconfigured")


    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.sber_url = self.get_parameter(SBER_URL_PARAM).get_parameter_value().string_value
        self.file_finished_subscription = self.create_subscription(
            String, FILE_FINISHED_TOPIC_NAME, self._file_finished_callback, 10
        )
        self.timer = self.create_timer(10, self._check_unsent_files)
        self.get_logger().info("SberSenderNode is configured")
        return TransitionCallbackReturn.SUCCESS
    
    
    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.get_logger().info('SberSenderNode on_cleanup')
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.get_logger().info('SberSenderNode on_shutdown')
        return TransitionCallbackReturn.SUCCESS

    def _format_data(self, data: str) -> dict:
        data_json = json.loads(data)
        formatted_data = {"boat_id": 12332, "measurements": []}
        for meas in data_json["measurements"]:
            new_meas = {"timestamp": meas.pop("timestamp")}
            location = meas.pop("gps")
            new_meas["GPS"] = {"latitude": location[0], "longitude": location[1]}
            new_meas["sensors"] = meas
            formatted_data["measurements"].append(new_meas)
        return formatted_data

    def _file_finished_callback(self, data: String) -> None:
        with open(data.data, "r") as f:
            data_from_file = f.read()
        ipfs_hash = IPFS.add_json(formatted_data, self._logger)
        self._robonomics.record_datalog(ipfs_hash)

    def _cleanup(self) -> None:
        self.destroy_subscription(self.file_finished_subscription)
        self.destroy_timer(self.timer)