from collections import deque
from datetime import datetime
import os
from pathlib import Path

from rclpy.node import Node
from rcl_interfaces.msg import Log

LOG_LEVELS ={
    30: "WARNING",
    20: "INFO",
    10: "DEBUG",
    40: "ERROR",
    50: "FATAL"
}

class LogSaver:
    def __init__(self, parent_node: Node, log_dir: str):
        self.parent_node = parent_node
        self.parent_log_dir = Path(log_dir)
        self.log_sub = self.parent_node.create_subscription(Log, "/rosout", self.log_callback, 10)
        self.nodes_logs: dict[str, LogHandler] = {}
        self.current_log_dir: Path = self._create_log_dir(log_dir)

    def log_callback(self, data: Log) -> None:
        node_name = data.name.split(".")[0]
        if node_name not in self.nodes_logs:
            self.nodes_logs[node_name] = LogHandler(node_name, self.current_log_dir)
        self.nodes_logs[node_name].add_log(data)

    def get_logs_for_node(self, node_name: str) -> list[str] | None:
        log_handler = self.nodes_logs.get(node_name)
        if log_handler:
            return log_handler.get_from_buffer()
        
    def get_filename_for_node(self, node_name: str) -> str | None:
        log_handler = self.nodes_logs.get(node_name)
        if log_handler:
            return log_handler.log_filename
        
    def _create_log_dir(self, log_dir_parent: str) -> Path:
        current_dir = self._format_log_dir(log_dir_parent)
        current_dir.mkdir(parents=True, exist_ok=True)
        self._link_to_latest(current_dir)
        return current_dir
        
    def _format_log_dir(self, log_dir_parent: str) -> Path:
        if log_dir_parent[-1] == "/":
            log_dir_parent = log_dir_parent[:-1]
        return Path(f"{log_dir_parent}/{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}")
    
    def _link_to_latest(self, log_dir: Path) -> None:
        symlink_path = log_dir.parent.joinpath("latest")
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()
        symlink_path.symlink_to(log_dir, target_is_directory=True)
        
    

    
class LogHandler:
    def __init__(self, node_name: str, log_dir: Path):
        self.node_name = node_name
        self.log_filename = self._format_filename(node_name, log_dir)
        self._create_file(self.log_filename)
        self._buffer = LogBuffer()

    def add_log(self, log: Log) -> None:
        fornmatted_log = self._format_log(log)
        self._buffer.add_log(fornmatted_log)
        self._write_to_file(fornmatted_log)

    def get_from_buffer(self) -> list[str]:
        return self._buffer.get_buffer()

    def _write_to_file(self, log: str) -> None:
        with self.log_filename.open("a", encoding="utf-8") as f:
            f.write(f"{log}\n")

    def _create_file(self, filepath: Path) -> None:
        filepath.touch()

    def _format_filename(self, node_name: str, log_dir: Path) -> Path:
        return log_dir.joinpath(f"{node_name}.log")
    
    def _format_log(self, log: Log) -> str:
        timestamp = datetime.fromtimestamp(log.stamp.sec)
        timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        log_level_str = LOG_LEVELS[log.level]
        message = log.msg
        filename = log.file.split("/")[-1]
        line = log.line
        function_str = log.function
        return f"[{timestamp_str}] [{log_level_str}] [{filename}:{function_str}:{line}] {message}"

class LogBuffer:
    def __init__(self, first_lines_count: int = 50, last_lines_count: int = 100):
        self.first_lines_count: int = first_lines_count
        self.last_lines_count: int = last_lines_count
        self._first_logs: list[str] = []
        self._last_logs: deque[str] = deque(maxlen=self.last_lines_count)

    def add_log(self, log: str) -> None:
        if len(self._first_logs) < self.first_lines_count:
            self._first_logs.append(log)
        else:
            self._last_logs.append(log)

    def get_buffer(self) -> list[str]:
        if len(self._first_logs) < self.first_lines_count:
            return self._first_logs.copy()
        else:
            return self._first_logs.copy() + list(self._last_logs)