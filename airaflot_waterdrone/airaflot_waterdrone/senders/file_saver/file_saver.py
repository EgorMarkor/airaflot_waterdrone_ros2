import typing as tp
import time
import json
import os
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node, Subscription
from datetime import datetime, date, timedelta
from pathlib import Path

from rclpy.lifecycle import LifecycleNode, LifecyclePublisher, LifecycleState, TransitionCallbackReturn

from airaflot_msgs.msg import DataToSend
from std_msgs.msg import String

from ...const_names import (
    DATA_TO_SEND_TOPIC_NAME,
    FILE_FINISHED_TOPIC_NAME,
    OPERATING_MODE_ONE_MEAS_PER_FILE,
    OPERATING_MODE_FROM_START_TO_LAST,
    OPERATING_MODE_PERMANENTLY,
    FILE_SAVER_MODE_PARAM,
    FILE_PREFIX_PARAM
)
from .config import MAX_MEASUREMENTS_COUNT, NEW_FILE_TIMEOUT, STORE_FILES_PATH
from .filename_util import Filename

NODE_NAME = "file_saver"


class FileSaver(LifecycleNode):
    def __init__(self):
        super().__init__(NODE_NAME)

        self.data_subscription: Subscription | None = None
        self.publisher: LifecyclePublisher | None = None
        self.declare_parameter(FILE_PREFIX_PARAM, "meas")
        self.declare_parameter(FILE_SAVER_MODE_PARAM, OPERATING_MODE_ONE_MEAS_PER_FILE)

        self._current_date: str = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        self._file_prefix: str = "meas"
        self._current_filename: Filename | None = None
        self.operating_mode = OPERATING_MODE_ONE_MEAS_PER_FILE
        self.get_logger().info("FileSaver is unconfigured")

    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.operating_mode = self.get_parameter(FILE_SAVER_MODE_PARAM).get_parameter_value().string_value
        self._file_prefix = self.get_parameter(FILE_PREFIX_PARAM).get_parameter_value().string_value
        self.data_subscription = self.create_subscription(
            DataToSend, DATA_TO_SEND_TOPIC_NAME, self._new_data_callback, 10
        )
        self.publisher = self.create_lifecycle_publisher(String, FILE_FINISHED_TOPIC_NAME, 10)

        self._create_folders()
        self.get_logger().info("FileSaver is configured")
        return TransitionCallbackReturn.SUCCESS
    
    
    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_subscription(self.data_subscription)
        self.destroy_lifecycle_publisher(self.publisher)
        self._file_prefix: str = "meas"

        self.get_logger().info('FileSaver on_cleanup')
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self.destroy_subscription(self.data_subscription)
        self.destroy_lifecycle_publisher(self.publisher)
        self._file_prefix: str = "meas"

        self.get_logger().info('FileSaver on_shutdown')
        return TransitionCallbackReturn.SUCCESS

    def _new_data_callback(self, data: DataToSend) -> None:
        if self.operating_mode == OPERATING_MODE_PERMANENTLY:
            self._check_current_file_and_create_new_if_need()
            self._write_one_measurement(data)
        elif self.operating_mode == OPERATING_MODE_FROM_START_TO_LAST:
            if data.message_position == DataToSend.MESSAGE_POS_START or self._current_filename is None:
                self._current_filename = self._create_new_file()
            self._write_one_measurement(data)
            if data.message_position == DataToSend.MESSAGE_POS_LAST:
                self._publish_info_about_finished_file()
                self._current_filename == None
        elif self.operating_mode == OPERATING_MODE_ONE_MEAS_PER_FILE:
            self._current_filename = self._create_new_file()
            self._write_one_measurement(data)
            self._publish_info_about_finished_file()
            self._current_filename == None


    def _write_one_measurement(self, data: DataToSend) -> None:
        json_new_data = self._format_data_to_json(data)
        file_data = self._get_data_from_file()
        file_data["measurements"].append(json_new_data)
        self._write_data_to_file(file_data)

    def _format_data_to_json(self, data: DataToSend) -> tp.Dict:
        json_data = json.loads(data.sensors_data)
        json_data["gps"] = (data.latitude, data.longitude)
        json_data["timestamp"] = data.timestamp
        return json_data
    
    def _check_current_file_and_create_new_if_need(self) -> None:
        if self._current_filename is None:
            self._current_filename = self._create_new_file()
            return
        time_since_creation = datetime.now() - self._current_filename.get_date()
        file_data = self._get_data_from_file()
        if time_since_creation > NEW_FILE_TIMEOUT or len(file_data["measurements"]) > MAX_MEASUREMENTS_COUNT:
            self._publish_info_about_finished_file()
            self._current_filename = self._create_new_file()

    def _publish_info_about_finished_file(self) -> None:
        msg = String()
        msg.data = self._current_filename.to_str()
        self.publisher.publish(msg)

    def _get_data_from_file(self) -> tp.Dict:
        with open(self._current_filename.to_str(), "r") as f:
            file_data = json.load(f)
        return file_data

    def _write_data_to_file(self, data: tp.Dict) -> tp.Dict:
        with open(self._current_filename.to_str(), "w") as f:
            json.dump(data, f)
    
    def _create_new_file(self) -> str:
        filename = Filename.create_new(self._current_date, self._file_prefix)
        with open(filename.to_str(), "w") as f:
            json.dump({"measurements": []}, f)
        self.get_logger().info(f"New file {filename.to_str()} was created")
        return filename
    
    def _create_folders(self) -> None:
        self._create_folder_if_not_exists(STORE_FILES_PATH)
        self._create_folder_if_not_exists(f"{STORE_FILES_PATH}/{self._current_date}")
        self._create_folder_if_not_exists(f"{STORE_FILES_PATH}/{self._current_date}/sent")
        self._create_folder_if_not_exists(f"{STORE_FILES_PATH}/{self._current_date}/not_sent")
        self._link_to_latest(Path(f"{STORE_FILES_PATH}/{self._current_date}"))

    def _create_folder_if_not_exists(self, path: str) -> None:
        if not os.path.exists(path):
            os.mkdir(path)
            self.get_logger().info(f"Folder {path} was created")

    def _link_to_latest(self, meas_dir: Path) -> None:
        symlink_path = meas_dir.parent.joinpath("latest")
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()
        symlink_path.symlink_to(meas_dir, target_is_directory=True)


def main(args=None):
    try:
        rclpy.init(args=args)
        minimal_subscriber = FileSaver()

        rclpy.spin(minimal_subscriber)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
