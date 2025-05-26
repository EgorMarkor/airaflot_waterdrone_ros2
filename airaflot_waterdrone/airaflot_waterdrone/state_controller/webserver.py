import threading
import queue
from flask import Flask, jsonify, request, render_template, Response
import os
from pathlib import Path
import shutil

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
        self.nodes_states: dict[str, str] = {}
        self.app = Flask(__name__, template_folder=self._get_templates_path())
        self.app_server = ServerThread(self.app)
        self.scenario_state = "NOT_READY"
        self.scenario_names = [scenario.name for scenario in SUPPORTED_SCENARIOS]
        self.current_scenario_name = None
        self.current_scenario = None
        self.logger_callback(f"Template folder: {os.path.abspath(self.app.template_folder)}")
        self.setup_routes()

    def setup_routes(self):
        @self.app.route('/')
        def index():
            return render_template("index.html", scenario_list=SUPPORTED_SCENARIOS, current_scenario=self.current_scenario)

        @self.app.route('/activate')
        def activate():
            self.logger_callback("Web request: scheduling nodes activation.")
            self.command_queue.put("activate_all")
            return "Nodes activation scheduled."
        
        @self.app.route('/run_main_service', methods=["POST"])
        def run_main_service():
            self.logger_callback("Web request: running main service.")
            self.command_queue.put("run_main_service")
            return "Running main service scheduled."

        @self.app.route('/deactivate')
        def deactivate():
            self.logger_callback("Web request: scheduling nodes deactivation.")
            self.command_queue.put("deactivate_all")
            return "Nodes deactivation scheduled."

        @self.app.route('/node_action')
        def node_action():
            node_name = request.args.get("name")
            action = request.args.get("action")
            if node_name:
                if action == "activate":
                    self.command_queue.put(f"activate:{node_name}")
                    return f"Activation of {node_name} scheduled."
                elif action == "deactivate":
                    self.command_queue.put(f"deactivate:{node_name}")
                    return f"Deactivation of {node_name} scheduled."
            return "Invalid request", 400

        @self.app.route('/select_scenario', methods=["POST"])
        def set_scenario():
            scenario_name = request.form.get("scenario")
            if scenario_name in self.scenario_names:
                self.current_scenario_name = scenario_name
                for scenario in SUPPORTED_SCENARIOS:
                    if scenario.name == scenario_name:
                        self.current_scenario = scenario
                self.logger_callback(f"Changing scenario to: {self.current_scenario.name}")
                self.command_queue.put(f"set_scenario:{scenario_name}")
                return "Scenario changed"
            return "Invalid scenario", 400

        @self.app.route("/project_state")
        def project_state():
            if not self.current_scenario:
                return jsonify({"error": "No scenario selected"}), 400
            project_state = {}
            nodes_list = [{'full_name': node, 'state': self.nodes_states[node]} for node in self.nodes_states]
            project_state["nodes"] = nodes_list
            project_state["current_scenario"] = {"name": self.current_scenario_name, "state": self.scenario_state, "main_service_available": self.current_scenario.main_service_info is not None}
            project_state["supported_scenarios"] = self.scenario_names
            editable_names = {param.name for param in self.current_scenario.get_user_set_parameters()}
            data = {}
            for node, params in self.current_scenario.parameters.items():
                data[node] = [
                    {
                        "name": param.name,
                        "type": param.value.type,
                        "value": (
                            param.value.string_value if param.value.type == ParameterType.PARAMETER_STRING else
                            param.value.bool_value if param.value.type == ParameterType.PARAMETER_BOOL else
                            param.value.integer_value if param.value.type == ParameterType.PARAMETER_INTEGER else None
                        ),
                        "editable": param.name in editable_names
                    } for param in params
                ]
            project_state["parameters"] = data
            return jsonify(project_state)

        @self.app.route('/set_parameters', methods=['POST'])
        def set_parameters():
            if not self.current_scenario:
                return "No scenario selected", 400

            scenario: ScenarioInfo = self.current_scenario
            raw = request.get_json()
            updated_params = []

            for param in raw:
                p = Parameter()
                p.name = param["name"]
                p.value.type = param["type"]
                if p.value.type == ParameterType.PARAMETER_STRING:
                    p.value.string_value = param["value"]
                elif p.value.type == ParameterType.PARAMETER_BOOL:
                    p.value.bool_value = param["value"]
                elif p.value.type == ParameterType.PARAMETER_INTEGER:
                    p.value.integer_value = param["value"]
                updated_params.append(p)

            scenario.set_parameters_from_user(updated_params)
            return "Parameters updated"

        @self.app.route("/list_log_files")
        def list_log_files():
            return jsonify({"files": self._get_filenames(self.log_saver.parent_log_dir)})
        

        @self.app.route("/list_meas_files")
        def list_meas_files():
            return jsonify({"files": self._get_filenames(Path(STORE_FILES_PATH))})
        
        @self.app.route("/file_content")
        def log_file_content():
            filepath = request.args.get('filepath')
            return self._read_file(Path(filepath).resolve())

        @self.app.route("/delete_path", methods=["POST"])
        def delete_path():
            filepath = request.form.get('filepath')
            if not filepath:
                return Response("Missing filepath", status=400)
            
            target_path = Path(filepath).resolve()
            
            # Resolve and sanitize path
            if not (str(self.log_saver.parent_log_dir) in str(target_path) or STORE_FILES_PATH in str(target_path)):
                return Response("Invalid file path", status=403)

            if not target_path.exists():
                return Response("File or folder not found", status=404)

            try:
                if target_path.is_file():
                    target_path.unlink()
                elif target_path.is_dir():
                    shutil.rmtree(target_path)
                else:
                    return Response("Unsupported file type", status=400)
            except Exception as e:
                return Response(f"Error deleting: {str(e)}", status=500)

            return Response("Deleted successfully", status=200)
    

    def clear_nodes_list(self) -> None:
        self.nodes_states.clear()

    def set_current_scenario(self, scenario: ScenarioInfo) -> None:
        self.current_scenario = scenario
        self.current_scenario_name = scenario.name
    
    def set_node_state(self, node_name: str, node_state: str) -> None:
        self.nodes_states[node_name] = node_state

    def set_scenario_state(self, scenario_state: int) -> None:
        self.scenario_state = state_mapping[scenario_state]

    def start(self):
        # threading.Thread(target=self.app.run, kwargs={"host": "0.0.0.0", "port": 5000}, daemon=True).start()
        self.app_server.start()
        self.logger_callback("Webserver started on port 5000")

    def _get_templates_path(self) -> str:
        pkg_name = 'airaflot_waterdrone'
        package_path = get_package_share_directory(pkg_name)
        workspace_root = os.path.abspath(os.path.join(package_path, '../../../..'))
        return os.path.join(workspace_root, 'src', pkg_name, pkg_name, "templates")
    
    def _read_file(self, filepath: Path) -> Response:
        self.logger_callback(f"Readin file: {filepath}")
        if not filepath:
            return Response("Missing filename", status=400)
        if not (str(self.log_saver.parent_log_dir) in str(filepath) or STORE_FILES_PATH in str(filepath)):
            return Response("Invalid file path", status=403)
        if not filepath.is_file():
            return Response("File not found", status=404)
        return Response(filepath.read_text(encoding="utf-8"), mimetype="text/plain")
    
    def _get_filenames(self, directory: Path) -> dict:
        filenames = []
        for item in directory.iterdir():
            if item.is_file():
                filenames.append({"name": item.name, "path": str(item.absolute()), "isdir": False, "items": []})
            else:
                filenames.append({"name": item.name, "path": str(item.absolute()), "isdir": True, "items": self._get_filenames(item)})
        return filenames

    def stop(self) -> None:
        self.logger_callback("Shutdown webserver")
        self.app_server.shutdown()
        


class ServerThread(threading.Thread):
    def __init__(self, app):
        super().__init__()
        self.server = make_server('0.0.0.0', 5000, app)
        self.ctx = app.app_context()
        self.ctx.push()
    
    def run(self):
        print('Starting server')
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()