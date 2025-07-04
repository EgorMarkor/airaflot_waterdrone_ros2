import threading
import queue
import time
from flask import Flask, jsonify, request, render_template, Response
import os
from pathlib import Path
import shutil
from contextlib import contextmanager
from datetime import datetime

from airaflot_msgs.msg import ScenarioStateMsg
from rcl_interfaces.msg import Parameter, ParameterType
from ament_index_python.packages import get_package_share_directory
from werkzeug.serving import make_server

from .log_saver import LogSaver
from .scenario_info import WaterSamplerScenario, EcostabSensorsScenario, ScenarioInfo, SUPPORTED_SCENARIOS
from ..senders.file_saver.config import STORE_FILES_PATH

state_mapping = {
    ScenarioStateMsg.WAIT_FOR_COMMAND: "WAIT_FOR_COMMAND",
    ScenarioStateMsg.WORK: "WORK",
    ScenarioStateMsg.GO_TO_NEXT_POINT: "GO_TO_NEX_POINT",
    ScenarioStateMsg.GO_HOME: "GO_HOME",
    ScenarioStateMsg.SENDING_DATA: "SENDING_DATA",
    ScenarioStateMsg.ALL_SENT: "ALL_SENT",
    ScenarioStateMsg.IS_UNSENT_DATA: "IS_UNSENT_DATA",
    -1: "NOT_READY"
}


class WebServer:
    def __init__(self, command_queue: queue.Queue, logger_callback, log_saver: LogSaver):
        self.log_saver = log_saver
        self.command_queue = command_queue
        self.logger_callback = logger_callback
        
        # Thread-safe state management
        self._state_lock = threading.RLock()
        self.nodes_states: dict[str, str] = {}
        self.scenario_state = "NOT_READY"
        self.scenario_names = [scenario.name for scenario in SUPPORTED_SCENARIOS]
        self.current_scenario_name = None
        self.current_scenario = None
        
        # Flask app setup
        self.app = Flask(__name__, template_folder=self._get_templates_path(), static_folder=self._get_static_path())
        self.app_server = None
        self._server_running = False
        
        self.logger_callback(f"Template folder: {os.path.abspath(self.app.template_folder)}")
        self.setup_routes()

    @contextmanager
    def _state_context(self):
        """Context manager for thread-safe state access"""
        self._state_lock.acquire()
        try:
            yield
        finally:
            self._state_lock.release()

    def setup_routes(self):
        """Setup Flask routes with improved error handling"""
        
        @self.app.route('/')
        def index():
            try:
                with self._state_context():
                    return render_template("index.html", 
                                         scenario_list=SUPPORTED_SCENARIOS, 
                                         current_scenario=self.current_scenario)
            except Exception as e:
                self.logger_callback(f"Error rendering index: {e}")
                return f"Error: {str(e)}", 500

        @self.app.route('/activate')
        def activate():
            try:
                self.logger_callback("Web request: scheduling nodes activation.")
                self.command_queue.put("activate_all")
                return "Nodes activation scheduled."
            except Exception as e:
                self.logger_callback(f"Error scheduling activation: {e}")
                return f"Error: {str(e)}", 500
        
        @self.app.route('/run_main_service', methods=["POST"])
        def run_main_service():
            try:
                self.logger_callback("Web request: running main service.")
                self.command_queue.put("run_main_service")
                return "Running main service scheduled."
            except Exception as e:
                self.logger_callback(f"Error scheduling main service: {e}")
                return f"Error: {str(e)}", 500

        @self.app.route('/deactivate')
        def deactivate():
            try:
                self.logger_callback("Web request: scheduling nodes deactivation.")
                self.command_queue.put("deactivate_all")
                return "Nodes deactivation scheduled."
            except Exception as e:
                self.logger_callback(f"Error scheduling deactivation: {e}")
                return f"Error: {str(e)}", 500

        @self.app.route('/node_action')
        def node_action():
            try:
                node_name = request.args.get("name")
                action = request.args.get("action")
                
                if not node_name or not action:
                    return "Missing node name or action", 400
                    
                if action not in ["activate", "deactivate"]:
                    return "Invalid action", 400
                    
                self.command_queue.put(f"{action}:{node_name}")
                return f"{action.capitalize()} of {node_name} scheduled."
                
            except Exception as e:
                self.logger_callback(f"Error in node_action: {e}")
                return f"Error: {str(e)}", 500

        @self.app.route('/select_scenario', methods=["POST"])
        def set_scenario():
            try:
                scenario_name = request.form.get("scenario")
                if not scenario_name:
                    return "Missing scenario name", 400
                    
                if scenario_name not in self.scenario_names:
                    return "Invalid scenario", 400
                    
                with self._state_context():
                    self.current_scenario_name = scenario_name
                    for scenario in SUPPORTED_SCENARIOS:
                        if scenario.name == scenario_name:
                            self.current_scenario = scenario
                            break
                
                self.logger_callback(f"Changing scenario to: {scenario_name}")
                self.command_queue.put(f"set_scenario:{scenario_name}")
                return "Scenario changed"
                
            except Exception as e:
                self.logger_callback(f"Error setting scenario: {e}")
                return f"Error: {str(e)}", 500

        @self.app.route("/project_state")
        def project_state():
            try:
                with self._state_context():
                    if not self.current_scenario:
                        return jsonify({"error": "No scenario selected"}), 400
                        
                    project_state = {}
                    nodes_list = [{'full_name': node, 'state': self.nodes_states.get(node, 'unknown')} 
                                for node in self.current_scenario.node_list]
                    project_state["nodes"] = nodes_list
                    
                    project_state["current_scenario"] = {
                        "name": self.current_scenario_name, 
                        "state": self.scenario_state, 
                        "main_service_available": self.current_scenario.main_service_info is not None
                    }
                    project_state["supported_scenarios"] = self.scenario_names
                    
                    # Build parameters data
                    editable_names = {param.name for param in self.current_scenario.get_user_set_parameters()}
                    data = {}
                    for node, params in self.current_scenario.parameters.items():
                        data[node] = [
                            {
                                "name": param.name,
                                "type": param.value.type,
                                "value": self._extract_parameter_value(param.value),
                                "editable": param.name in editable_names
                            } for param in params
                        ]
                    project_state["parameters"] = data
                    
                return jsonify(project_state)
                
            except Exception as e:
                self.logger_callback(f"Error getting project state: {e}")
                return jsonify({"error": str(e)}), 500

        @self.app.route('/set_parameters', methods=['POST'])
        def set_parameters():
            try:
                with self._state_context():
                    if not self.current_scenario:
                        return "No scenario selected", 400
                    scenario = self.current_scenario

                raw = request.get_json()
                if not raw:
                    return "No parameters provided", 400

                updated_params = []
                for param in raw:
                    try:
                        p = Parameter()
                        p.name = param["name"]
                        p.value.type = param["type"]
                        
                        self._set_parameter_value(p.value, param["value"], param["type"])
                        updated_params.append(p)
                        
                    except Exception as e:
                        self.logger_callback(f"Error processing parameter {param.get('name', 'unknown')}: {e}")
                        continue

                scenario.set_parameters_from_user(updated_params)
                self.command_queue.put(f"set_parameters")
                return "Parameters updated"
                
            except Exception as e:
                self.logger_callback(f"Error setting parameters: {e}")
                return f"Error: {str(e)}", 500

        @self.app.route("/list_log_files")
        def list_log_files():
            try:
                files = self._get_filenames(self.log_saver.parent_log_dir)
                return jsonify({"files": files})
            except Exception as e:
                self.logger_callback(f"Error listing log files: {e}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/list_meas_files")
        def list_meas_files():
            try:
                files = self._get_filenames(Path(STORE_FILES_PATH))
                return jsonify({"files": files})
            except Exception as e:
                self.logger_callback(f"Error listing measurement files: {e}")
                return jsonify({"error": str(e)}), 500
        
        @self.app.route("/file_content")
        def log_file_content():
            try:
                filepath = request.args.get('filepath')
                if not filepath:
                    return Response("Missing filepath", status=400)
                return self._read_file(Path(filepath).resolve())
            except Exception as e:
                self.logger_callback(f"Error reading file content: {e}")
                return Response(f"Error: {str(e)}", status=500)

        @self.app.route("/delete_path", methods=["POST"])
        def delete_path():
            try:
                filepath = request.form.get('filepath')
                if not filepath:
                    return Response("Missing filepath", status=400)
                
                target_path = Path(filepath).resolve()
                
                # Security check - ensure path is within allowed directories
                allowed_paths = [str(self.log_saver.parent_log_dir), STORE_FILES_PATH]
                if not any(allowed_path in str(target_path) for allowed_path in allowed_paths):
                    return Response("Invalid file path", status=403)

                if not target_path.exists():
                    return Response("File or folder not found", status=404)

                if target_path.is_file():
                    target_path.unlink()
                    self.logger_callback(f"Deleted file: {target_path}")
                elif target_path.is_dir():
                    shutil.rmtree(target_path)
                    self.logger_callback(f"Deleted directory: {target_path}")
                else:
                    return Response("Unsupported file type", status=400)

                return Response("Deleted successfully", status=200)
                
            except Exception as e:
                self.logger_callback(f"Error deleting path: {e}")
                return Response(f"Error deleting: {str(e)}", status=500)


        @self.app.route("/delete_folders_by_date", methods=["POST"])
        def delete_folders_by_date():
            try:
                date_str = request.form.get("date")
                folder_type = request.form.get("type")
                
                if not date_str or not folder_type:
                    return Response("Missing date or type", status=400)
                
                # Validate date format (YYYY-MM-DD)
                try:
                    selected_date = datetime.strptime(date_str, "%Y-%m-%d")
                    current_date = datetime.now().date()
                    if selected_date.date() >= current_date:
                        return Response("Cannot delete folders for today or future dates", status=400)
                except ValueError:
                    return Response("Invalid date format", status=400)
                
                # Determine directory based on type
                if folder_type == "log":
                    base_dir = self.log_saver.parent_log_dir
                elif folder_type == "meas":
                    base_dir = Path(STORE_FILES_PATH)
                else:
                    return Response("Invalid folder type", status=400)
                
                # Security check
                allowed_paths = [str(self.log_saver.parent_log_dir), STORE_FILES_PATH]
                if str(base_dir) not in allowed_paths:
                    return Response("Invalid directory path", status=403)
                
                # Find and delete folders matching the date prefix
                deleted = False
                for item in base_dir.iterdir():
                    if item.is_dir() and item.name.startswith(date_str):
                        try:
                            shutil.rmtree(item)
                            self.logger_callback(f"Deleted folder: {item}")
                            deleted = True
                        except Exception as e:
                            self.logger_callback(f"Error deleting folder {item}: {e}")
                            continue
                
                if not deleted:
                    return Response("No folders found for the selected date", status=404)
                
                return Response("Folders deleted successfully", status=200)
                
            except Exception as e:
                self.logger_callback(f"Error deleting folders by date: {e}")
                return Response(f"Error: {str(e)}", status=500)

    def _extract_parameter_value(self, param_value):
        """Extract parameter value based on type"""
        if param_value.type == ParameterType.PARAMETER_STRING:
            return param_value.string_value
        elif param_value.type == ParameterType.PARAMETER_BOOL:
            return param_value.bool_value
        elif param_value.type == ParameterType.PARAMETER_INTEGER:
            return param_value.integer_value
        elif param_value.type == ParameterType.PARAMETER_DOUBLE:
            return param_value.double_value
        return None

    def _set_parameter_value(self, param_value, value, param_type):
        """Set parameter value based on type"""
        if param_type == ParameterType.PARAMETER_STRING:
            param_value.string_value = str(value)
        elif param_type == ParameterType.PARAMETER_BOOL:
            param_value.bool_value = bool(value)
        elif param_type == ParameterType.PARAMETER_INTEGER:
            param_value.integer_value = int(value)
        elif param_type == ParameterType.PARAMETER_DOUBLE:
            param_value.double_value = float(value)

    def clear_nodes_list(self) -> None:
        """Clear nodes list with thread safety"""
        with self._state_context():
            self.nodes_states.clear()

    def set_current_scenario(self, scenario: ScenarioInfo) -> None:
        """Set current scenario with thread safety"""
        with self._state_context():
            self.current_scenario = scenario
            self.current_scenario_name = scenario.name
    
    def set_node_state(self, node_name: str, node_state: str) -> None:
        """Set node state with thread safety"""
        with self._state_context():
            self.nodes_states[node_name] = node_state

    def set_scenario_state(self, scenario_state: int) -> None:
        """Set scenario state with thread safety"""
        with self._state_context():
            self.scenario_state = state_mapping.get(scenario_state, "UNKNOWN")

    def start(self):
        """Start the web server with improved error handling"""
        try:
            if self._server_running:
                self.logger_callback("Server already running")
                return
                
            self.app_server = ServerThread(self.app, self.logger_callback)
            self.app_server.start()
            self._server_running = True
            self.logger_callback("Webserver started on port 5000")
            
        except Exception as e:
            self.logger_callback(f"Failed to start webserver: {e}")
            raise

    def stop(self) -> None:
        """Stop the web server with proper cleanup"""
        try:
            if not self._server_running:
                return
                
            self.logger_callback("Shutting down webserver")
            if self.app_server:
                self.app_server.shutdown()
                self.app_server.join(timeout=5.0)  # Wait for thread to finish
                if self.app_server.is_alive():
                    self.logger_callback("Warning: Server thread did not stop gracefully")
                    
            self._server_running = False
            self.logger_callback("Webserver shutdown complete")
            
        except Exception as e:
            self.logger_callback(f"Error during webserver shutdown: {e}")

    def _get_templates_path(self) -> str:
        """Get templates path with error handling"""
        try:
            pkg_name = 'airaflot_waterdrone'
            package_path = get_package_share_directory(pkg_name)
            workspace_root = os.path.abspath(os.path.join(package_path, '../../../..'))
            return os.path.join(workspace_root, 'src', pkg_name, pkg_name, "templates")
        except Exception as e:
            self.logger_callback(f"Error getting templates path: {e}")
            # Fallback to a default path
            return os.path.join(os.getcwd(), "templates")

    def _get_static_path(self) -> str:
        """Get templates path with error handling"""
        try:
            pkg_name = 'airaflot_waterdrone'
            package_path = get_package_share_directory(pkg_name)
            workspace_root = os.path.abspath(os.path.join(package_path, '../../../..'))
            return os.path.join(workspace_root, 'src', pkg_name, pkg_name, "static")
        except Exception as e:
            self.logger_callback(f"Error getting templates path: {e}")
            # Fallback to a default path
            return os.path.join(os.getcwd(), "static")
    
    def _read_file(self, filepath: Path) -> Response:
        """Read file with security and error handling"""
        try:
            if not filepath:
                return Response("Missing filename", status=400)
                
            # Security check
            allowed_paths = [str(self.log_saver.parent_log_dir), STORE_FILES_PATH]
            if not any(allowed_path in str(filepath) for allowed_path in allowed_paths):
                return Response("Invalid file path", status=403)
                
            if not filepath.is_file():
                return Response("File not found", status=404)
                
            # Check file size to prevent memory issues
            file_size = filepath.stat().st_size
            if file_size > 10 * 1024 * 1024:  # 10MB limit
                return Response("File too large", status=413)
                
            content = filepath.read_text(encoding="utf-8")
            return Response(content, mimetype="text/plain")
            
        except UnicodeDecodeError:
            return Response("File is not text or uses unsupported encoding", status=415)
        except Exception as e:
            self.logger_callback(f"Error reading file {filepath}: {e}")
            return Response(f"Error reading file: {str(e)}", status=500)
    
    def _get_filenames(self, directory: Path) -> list:
        """Get filenames recursively with error handling"""
        try:
            if not directory.exists():
                return []
                
            filenames = []
            for item in directory.iterdir():
                try:
                    if item.is_file():
                        filenames.append({
                            "name": item.name, 
                            "path": str(item.absolute()), 
                            "isdir": False, 
                            "items": []
                        })
                    elif item.is_dir():
                        # Limit recursion depth to prevent infinite loops
                        sub_items = self._get_filenames(item) if len(str(item).split(os.sep)) < 20 else []
                        filenames.append({
                            "name": item.name, 
                            "path": str(item.absolute()), 
                            "isdir": True, 
                            "items": sub_items
                        })
                except (PermissionError, OSError) as e:
                    self.logger_callback(f"Cannot access {item}: {e}")
                    continue
                    
            return filenames
            
        except Exception as e:
            self.logger_callback(f"Error listing directory {directory}: {e}")
            return []


class ServerThread(threading.Thread):
    """Improved server thread with better error handling and shutdown"""
    
    def __init__(self, app, logger_callback):
        super().__init__(daemon=True)
        self.app = app
        self.logger_callback = logger_callback
        self.server = None
        self._shutdown_event = threading.Event()
        
    def run(self):
        """Run the server with error handling"""
        try:
            self.server = make_server('0.0.0.0', 5000, self.app, threaded=True)
            self.logger_callback('Starting Flask server on port 5000')
            
            # Serve until shutdown is requested
            while not self._shutdown_event.is_set():
                self.server.handle_request()
                
        except Exception as e:
            self.logger_callback(f"Server error: {e}")
        finally:
            if self.server:
                self.server.server_close()
            self.logger_callback('Flask server stopped')

    def shutdown(self):
        """Shutdown the server gracefully"""
        try:
            self._shutdown_event.set()
            if self.server:
                self.server.shutdown()
        except Exception as e:
            self.logger_callback(f"Error during server shutdown: {e}")