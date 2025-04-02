import threading
import queue
from flask import Flask, jsonify, request

from airaflot_msgs.msg import ScenarioStateMsg

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
    def __init__(self, command_queue: queue.Queue, logger_callback):
        self.command_queue = command_queue
        self.logger_callback = logger_callback
        self.nodes_states: dict[str, str] = {}
        self.app = Flask(__name__)
        self.scenario_state = "NOT_READY"
        self.setup_routes()

    def setup_routes(self):
        @self.app.route('/')
        def index():
            return """
            <!DOCTYPE html>
            <html>
              <head>
                <title>State Controller</title>
                <style>
                  .state-active { color: green; font-weight: bold; }
                  .state-dead { color: red; font-weight: bold; }
                  .state-unconfigured { color: orange; font-weight: bold; }
                </style>
              </head>
              <body>
                <h1>State Controller</h1>
                <h2>Scenario State: <span id="scenario_state">NOT_READY</span></h2>
                <button onclick="fetch('/activate').then(response => response.text()).then(alert)">Run Nodes</button>
                <button onclick="fetch('/deactivate').then(response => response.text()).then(alert)">Stop Nodes</button>
                <h2>Nodes and States</h2>
                <div id="nodes"></div>
                <script>
                  function getStateClass(state) {
                    if (state === "active") return "state-active";
                    if (state === "dead") return "state-dead";
                    if (state === "unconfigured") return "state-unconfigured";
                    return "";
                  }
                  
                  function loadNodes() {
                    fetch('/nodes')
                      .then(response => response.json())
                      .then(data => {
                        let list = '<ul>';
                        data.nodes.forEach(n => {
                          let action = n.state === "active" ? "deactivate" : "activate";
                          let stateClass = getStateClass(n.state);
                          list += `<li>${n.full_name}: <span class="${stateClass}">${n.state}</span> 
                                      <button onclick="fetch('/node_action?name=${n.full_name}&action=${action}').then(response => response.text()).then(alert)">
                                        ${action.charAt(0).toUpperCase() + action.slice(1)}
                                      </button>
                                  </li>`;
                        });
                        list += '</ul>';
                        document.getElementById('nodes').innerHTML = list;
                      });
                  }

                  function loadScenarioState() {
                    fetch('/scenario_state')
                      .then(response => response.text())
                      .then(state => {
                        document.getElementById('scenario_state').textContent = state;
                      });
                  }
                  
                  loadNodes();
                  loadScenarioState();
                  setInterval(loadNodes, 2000);
                  setInterval(loadScenarioState, 2000);
                </script>
              </body>
            </html>
            """

        @self.app.route('/activate')
        def activate():
            self.logger_callback("Web request: scheduling nodes activation.")
            self.command_queue.put("activate_all")
            return "Nodes activation scheduled."

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

        @self.app.route('/nodes')
        def nodes():
            nodes_list = [{'full_name': node, 'state': self.nodes_states[node]} for node in self.nodes_states]
            return jsonify({'nodes': nodes_list})

        @self.app.route('/scenario_state')
        def scenario_state():
            return self.scenario_state

    def set_node_state(self, node_name: str, node_state: str) -> None:
        self.nodes_states[node_name] = node_state

    def set_scenario_state(self, scenario_state: int) -> None:
        self.scenario_state = state_mapping[scenario_state]

    def start(self):
        threading.Thread(target=self.app.run, kwargs={"host": "0.0.0.0", "port": 5000}, daemon=True).start()
        self.logger_callback("Webserver started on port 5000")
