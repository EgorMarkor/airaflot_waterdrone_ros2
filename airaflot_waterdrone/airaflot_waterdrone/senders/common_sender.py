from rclpy.node import Timer, Subscription
import json
from pathlib import Path
import shutil
import rclpy
from rclpy.executors import ExternalShutdownException
from datetime import datetime, timedelta, time

from std_msgs.msg import String

from rclpy.lifecycle import LifecycleNode, LifecycleState, TransitionCallbackReturn
from rclpy.callback_groups import ReentrantCallbackGroup, MutuallyExclusiveCallbackGroup

from ..const_names import FILE_FINISHED_TOPIC_NAME
from .file_saver.config import STORE_FILES_PATH
from .sender_interface import Sender
from .sber import SberSender

NODE_NAME = "common_sender"
AVAILABLE_SENDERS: list[Sender] = [SberSender]

SENT_DIRNAME = "sent"
NOT_SENT_DIRNAME = "not_sent"

class CommonSender(LifecycleNode):
    def __init__(self):
        super().__init__(NODE_NAME)
        self.logger = self.get_logger()
        self.available_senders: list[Sender] = [sender(self.logger) for sender in AVAILABLE_SENDERS]
        self.file_finished_subscription: Subscription | None = None
        self.timer_callback = MutuallyExclusiveCallbackGroup()
        self.timer: Timer | None = None
        self.sber_url: str = ""
        self.active_senders: list[Sender] = []
        self._base_path = Path(STORE_FILES_PATH)
        for sender in self.available_senders:
            for param in sender.parameters_default:
                self.declare_parameter(param["name"], param["default_value"])
            self.declare_parameter(f"use_{sender.name}_sender", False)
        self.logger.info("Common Sender is unconfigured")


    def on_configure(self, state: LifecycleState) -> TransitionCallbackReturn:
        for sender in self.available_senders:
            self.logger.info(f"Start setup sender: {sender.name}, use: {self.get_parameter(f'use_{sender.name}_sender').get_parameter_value().bool_value}")
            if self.get_parameter(f"use_{sender.name}_sender").get_parameter_value().bool_value:
                self.logger.info(f"Start setup 1 sender: {sender.name}")
                for param_descr in sender.parameters_default:
                    param = self.get_parameter(param_descr["name"])
                    self.logger.info(f"Start set parameter: {param}")
                    sender.set_parameter(param)
                if not sender.setup():
                    self.logger.error(f"Can't setup {sender.name}")
                    return TransitionCallbackReturn.FAILURE
                self.active_senders.append(sender)
        self.logger.info(f"Use senders: {[sender.name for sender in self.active_senders]}")
        self.file_finished_subscription = self.create_subscription(
            String, FILE_FINISHED_TOPIC_NAME, self._file_finished_callback, 10
        )
        self.timer = self.create_timer(10, self._check_unsent_files, callback_group=self.timer_callback)
        self.logger.info("Common Sender is configured")
        return TransitionCallbackReturn.SUCCESS

    def _file_finished_callback(self, data: String) -> None:
        if self._send_data_from_file(data.data):
            self._move_to_sent(data.data)

    def _check_unsent_files(self) -> None:
        self.logger.info("Start check unsent files")
        files_sent = 0
        unsent_files = 0
        for item in self._base_path.iterdir():
            if item.stem != "latest":
                not_sent_path = item / NOT_SENT_DIRNAME
                if not_sent_path.exists():
                    if any(not_sent_path.iterdir()):
                        for filepath in not_sent_path.iterdir():
                            rclpy.spin_once(self, timeout_sec=0)
                            if self._file_created_long_ago(filepath):
                                if self._send_data_from_file(filepath):
                                    self._move_to_sent(filepath)
                                    files_sent += 1
                                else:
                                    unsent_files += 1
                            else:
                                self.logger.info(f"file {filepath} was created recently, not sent")
                                unsent_files += 1
        self.logger.info(f"Finished check unsent files, sent now: {files_sent}, unsent: {unsent_files}")

    def _send_data_from_file(self, filepath: Path | str) -> bool:
        self.logger.info(f"Start sending data from file {filepath}")
        if len(self.active_senders) == 0:
            self.logger.info("No senders configured")
            return False
        try:
            with open(filepath, "r") as f:
                sensors_data = json.load(f)
        except Exception as e:
            self.logger.error(f"Error in reading data from {filepath}: {e}")
            if filepath.exists() and len(filepath.read_text()) == 0:
                try:
                    filepath.unlink()
                    self.logger.error(f"Empty file {filepath} was removed")
                except Exception as e:
                    self.logger.error(f"Error in removing file {filepath}: {e}")
            return True
        for sender in self.active_senders:
            if not sender.send(sensors_data):
                self.logger.error(f"Error in sending data from {sender.name}")
                return False
            self.logger.info(f"Data succesfully sent with {sender.name}")
        return True
    
    def _move_to_sent(self, filepath: Path | str) -> None:
        source = Path(filepath)
        if not source.exists():
            self.logger.info(f"Source file not found: {source}")
            return
        try:
            parts = list(source.parts)
            idx = parts.index(NOT_SENT_DIRNAME)
            parts[idx] = SENT_DIRNAME
            destination = Path(*parts)
        except ValueError:
            raise ValueError(f"'not_sent' must be in the source path: {source}")
        shutil.move(str(source), str(destination))
        self.logger.info(f"File {source} moved to sent")

    def _file_created_long_ago(self, filepath: Path) -> bool:
        splitted = filepath.stem.split("_")
        splitted_date = filepath.parent.parent.stem.split("-")
        file_time = datetime(
            year=int(splitted_date[0]), 
            month=int(splitted_date[1]), 
            day=int(splitted_date[2]), 
            hour=int(splitted[-3]), 
            minute=int(splitted[-2]), 
            second=int(splitted[-1])
        )
        return (datetime.now() - file_time) > timedelta(minutes=5)

    def on_cleanup(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.logger.info('Common Sender on_cleanup')
        return TransitionCallbackReturn.SUCCESS
    
    def on_shutdown(self, state: LifecycleState) -> TransitionCallbackReturn:
        self._cleanup()

        self.logger.info('Common Sender on_shutdown')
        return TransitionCallbackReturn.SUCCESS

    def _cleanup(self) -> None:
        self.destroy_subscription(self.file_finished_subscription)
        self.destroy_timer(self.timer)
        self.active_senders.clear()


def main(args=None):
    try:
        rclpy.init(args=args)
        minimal_subscriber = CommonSender()

        rclpy.spin(minimal_subscriber)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass


if __name__ == '__main__':
    main()