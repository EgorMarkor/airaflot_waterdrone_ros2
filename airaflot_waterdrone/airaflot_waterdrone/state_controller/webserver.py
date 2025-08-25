"""Django based web server for Airaflot water drone.

This module replaces the previous Flask implementation.  It exposes the same
REST style endpoints but uses Django so that future UI improvements can leverage
the wider Django ecosystem.  Only a lightweight configuration is used – the
project is configured entirely from code and runs inside a background thread so
that it can live inside a ROS node without additional management scripts.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import types

from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import render
from django.urls import path

from airaflot_msgs.msg import ScenarioStateMsg
from rcl_interfaces.msg import Parameter, ParameterType
from ament_index_python.packages import get_package_share_directory

from .log_saver import LogSaver
from .scenario_info import ScenarioInfo, get_supported_scenarios
from ..senders.file_saver.config import STORE_FILES_PATH


state_mapping = {
    ScenarioStateMsg.WAIT_FOR_COMMAND: "WAIT_FOR_COMMAND",
    ScenarioStateMsg.WORK: "WORK",
    ScenarioStateMsg.GO_TO_NEXT_POINT: "GO_TO_NEX_POINT",
    ScenarioStateMsg.GO_HOME: "GO_HOME",
    ScenarioStateMsg.SENDING_DATA: "SENDING_DATA",
    ScenarioStateMsg.ALL_SENT: "ALL_SENT",
    ScenarioStateMsg.IS_UNSENT_DATA: "IS_UNSENT_DATA",
    -1: "NOT_READY",
}


class WebServer:
    """Small wrapper around a Django application.

    The server mirrors the behaviour of the original Flask based implementation
    but relies solely on Django.  The configuration is created on the fly which
    keeps the ROS package self‑contained.
    """

    def __init__(self, command_queue: queue.Queue, logger_callback, log_saver: LogSaver):
        self.log_saver = log_saver
        self.command_queue = command_queue
        self.logger_callback = logger_callback

        # Thread‑safe state management
        self._state_lock = threading.RLock()
        self.nodes_states: dict[str, str] = {}
        self.scenario_state = "NOT_READY"
        self.scenario_names = [s.name for s in get_supported_scenarios()]
        self.current_scenario_name: str | None = None
        self.current_scenario: ScenarioInfo | None = None

        self._server_running = False
        self.app_server: ServerThread | None = None

        self._setup_django()
        self.logger_callback(f"Template folder: {self._get_templates_path()}")

    # ------------------------------------------------------------------
    # Django setup
    # ------------------------------------------------------------------
    def _setup_django(self) -> None:
        """Configure Django settings and URL routes."""

        template_dir = self._get_templates_path()
        static_dir = self._get_static_path()

        urls_module = types.ModuleType("webserver_urls")

        # --------------------------- Views ---------------------------
        def index(request):
            try:
                with self._state_context():
                    ctx = {
                        "scenario_list": get_supported_scenarios(),
                        "current_scenario": self.current_scenario,
                        "current_date": datetime.now().date().isoformat(),
                    }
                return render(request, "index.html", ctx)
            except Exception as exc:  # pragma: no cover - defensive
                self.logger_callback(f"Error rendering index: {exc}")
                return HttpResponse(f"Error: {exc}", status=500)

        def activate(request):
            try:
                self.logger_callback("Web request: scheduling nodes activation.")
                self.command_queue.put("activate_all")
                return HttpResponse("Nodes activation scheduled.")
            except Exception as exc:  # pragma: no cover - defensive
                self.logger_callback(f"Error scheduling activation: {exc}")
                return HttpResponse(f"Error: {exc}", status=500)

        def run_main_service(request):
            if request.method != "POST":
                return HttpResponseBadRequest("Invalid method")
            try:
                self.logger_callback("Web request: running main service.")
                self.command_queue.put("run_main_service")
                return HttpResponse("Running main service scheduled.")
            except Exception as exc:
                self.logger_callback(f"Error scheduling main service: {exc}")
                return HttpResponse(f"Error: {exc}", status=500)

        def deactivate(request):
            try:
                self.logger_callback("Web request: scheduling nodes deactivation.")
                self.command_queue.put("deactivate_all")
                return HttpResponse("Nodes deactivation scheduled.")
            except Exception as exc:
                self.logger_callback(f"Error scheduling deactivation: {exc}")
                return HttpResponse(f"Error: {exc}", status=500)

        def node_action(request):
            try:
                node_name = request.GET.get("name")
                action = request.GET.get("action")
                if not node_name or not action:
                    return HttpResponseBadRequest("Missing node name or action")
                if action not in ["activate", "deactivate"]:
                    return HttpResponseBadRequest("Invalid action")
                self.command_queue.put(f"{action}:{node_name}")
                return HttpResponse(f"{action.capitalize()} of {node_name} scheduled.")
            except Exception as exc:
                self.logger_callback(f"Error in node_action: {exc}")
                return HttpResponse(f"Error: {exc}", status=500)

        def select_scenario(request):
            if request.method != "POST":
                return HttpResponseBadRequest("Invalid method")
            try:
                scenario_name = request.POST.get("scenario")
                if not scenario_name:
                    return HttpResponse("Missing scenario name", status=400)
                if scenario_name not in self.scenario_names:
                    return HttpResponse("Invalid scenario", status=400)
                with self._state_context():
                    self.current_scenario_name = scenario_name
                    for scenario in get_supported_scenarios():
                        if scenario.name == scenario_name:
                            self.current_scenario = scenario
                            break
                self.logger_callback(f"Changing scenario to: {scenario_name}")
                self.command_queue.put(f"set_scenario:{scenario_name}")
                return HttpResponse("Scenario changed")
            except Exception as exc:
                self.logger_callback(f"Error setting scenario: {exc}")
                return HttpResponse(f"Error: {exc}", status=500)

        def project_state(request):
            try:
                with self._state_context():
                    if not self.current_scenario:
                        return JsonResponse({"error": "No scenario selected"}, status=400)

                    project_state: dict[str, Any] = {}
                    nodes_list = [
                        {"full_name": node, "state": self.nodes_states.get(node, "unknown")}
                        for node in self.current_scenario.node_list
                    ]
                    project_state["nodes"] = nodes_list

                    project_state["current_scenario"] = {
                        "name": self.current_scenario_name,
                        "state": self.scenario_state,
                        "main_service_available": self.current_scenario.main_service_info is not None,
                    }
                    project_state["supported_scenarios"] = self.scenario_names

                    editable_names = {p.name for p in self.current_scenario.get_user_set_parameters()}
                    data = {}
                    for node, params in self.current_scenario.parameters.items():
                        data[node] = [
                            {
                                "name": p.name,
                                "type": p.value.type,
                                "value": self._extract_parameter_value(p.value),
                                "editable": p.name in editable_names,
                            }
                            for p in params
                        ]
                    project_state["parameters"] = data

                return JsonResponse(project_state)
            except Exception as exc:
                self.logger_callback(f"Error getting project state: {exc}")
                return JsonResponse({"error": str(exc)}, status=500)

        def set_parameters(request):
            try:
                with self._state_context():
                    if not self.current_scenario:
                        return HttpResponse("No scenario selected", status=400)
                    scenario = self.current_scenario

                raw = json.loads(request.body or b"[]")
                if not raw:
                    return HttpResponse("No parameters provided", status=400)

                updated_params = []
                for param in raw:
                    try:
                        p = Parameter()
                        p.name = param["name"]
                        p.value.type = param["type"]
                        self._set_parameter_value(p.value, param["value"], param["type"])
                        updated_params.append(p)
                    except Exception as exc:
                        self.logger_callback(
                            f"Error processing parameter {param.get('name', 'unknown')}: {exc}"
                        )
                        continue

                scenario.set_parameters_from_user(updated_params)
                self.command_queue.put("set_parameters")
                return HttpResponse("Parameters updated")
            except Exception as exc:
                self.logger_callback(f"Error setting parameters: {exc}")
                return HttpResponse(f"Error: {exc}", status=500)

        def list_log_files(request):
            try:
                files = self._get_filenames(self.log_saver.parent_log_dir)
                return JsonResponse({"files": files})
            except Exception as exc:
                self.logger_callback(f"Error listing log files: {exc}")
                return JsonResponse({"error": str(exc)}, status=500)

        def list_meas_files(request):
            try:
                files = self._get_filenames(Path(STORE_FILES_PATH))
                return JsonResponse({"files": files})
            except Exception as exc:
                self.logger_callback(f"Error listing measurement files: {exc}")
                return JsonResponse({"error": str(exc)}, status=500)

        def file_content(request):
            try:
                filepath = request.GET.get("filepath")
                if not filepath:
                    return HttpResponse("Missing filepath", status=400)
                return self._read_file(Path(filepath).resolve())
            except Exception as exc:
                self.logger_callback(f"Error reading file content: {exc}")
                return HttpResponse(f"Error: {exc}", status=500)

        def delete_path(request):
            if request.method != "POST":
                return HttpResponseBadRequest("Invalid method")
            try:
                filepath = request.POST.get("filepath")
                if not filepath:
                    return HttpResponse("Missing filepath", status=400)

                target_path = Path(filepath).resolve()
                allowed_paths = [str(self.log_saver.parent_log_dir), STORE_FILES_PATH]
                if not any(allowed in str(target_path) for allowed in allowed_paths):
                    return HttpResponse("Invalid file path", status=403)
                if not target_path.exists():
                    return HttpResponse("File or folder not found", status=404)
                if target_path.is_file():
                    target_path.unlink()
                    self.logger_callback(f"Deleted file: {target_path}")
                elif target_path.is_dir():
                    shutil.rmtree(target_path)
                    self.logger_callback(f"Deleted directory: {target_path}")
                else:
                    return HttpResponse("Unsupported file type", status=400)
                return HttpResponse("Deleted successfully", status=200)
            except Exception as exc:
                self.logger_callback(f"Error deleting path: {exc}")
                return HttpResponse(f"Error deleting: {exc}", status=500)

        def delete_folders_by_date(request):
            if request.method != "POST":
                return HttpResponseBadRequest("Invalid method")
            try:
                date_str = request.POST.get("date")
                folder_type = request.POST.get("type")
                if not date_str or not folder_type:
                    return HttpResponse("Missing date or type", status=400)
                try:
                    selected_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if selected_date.date() >= datetime.now().date():
                        return HttpResponse(
                            "Cannot delete folders for today or future dates",
                            status=400,
                        )
                except ValueError:
                    return HttpResponse("Invalid date format", status=400)

                base_dir = (
                    self.log_saver.parent_log_dir
                    if folder_type == "log"
                    else Path(STORE_FILES_PATH)
                    if folder_type == "meas"
                    else None
                )
                if base_dir is None:
                    return HttpResponse("Invalid folder type", status=400)

                allowed_paths = [str(self.log_saver.parent_log_dir), STORE_FILES_PATH]
                if str(base_dir) not in allowed_paths:
                    return HttpResponse("Invalid directory path", status=403)

                deleted = False
                for item in base_dir.iterdir():
                    if item.is_dir() and item.name.startswith(date_str):
                        try:
                            shutil.rmtree(item)
                            self.logger_callback(f"Deleted folder: {item}")
                            deleted = True
                        except Exception as exc:
                            self.logger_callback(f"Error deleting folder {item}: {exc}")
                if not deleted:
                    return HttpResponse(
                        "No folders found for the selected date", status=404
                    )
                return HttpResponse("Folders deleted successfully", status=200)
            except Exception as exc:
                self.logger_callback(f"Error deleting folders by date: {exc}")
                return HttpResponse(f"Error: {exc}", status=500)

        # Register URL patterns
        urls_module.urlpatterns = [
            path("", index),
            path("activate", activate),
            path("run_main_service", run_main_service),
            path("deactivate", deactivate),
            path("node_action", node_action),
            path("select_scenario", select_scenario),
            path("project_state", project_state),
            path("set_parameters", set_parameters),
            path("list_log_files", list_log_files),
            path("list_meas_files", list_meas_files),
            path("file_content", file_content),
            path("delete_path", delete_path),
            path("delete_folders_by_date", delete_folders_by_date),
        ]

        sys.modules["webserver_urls"] = urls_module

        if not settings.configured:
            settings.configure(
                DEBUG=True,
                SECRET_KEY="airaflot-secret",
                ROOT_URLCONF="webserver_urls",
                ALLOWED_HOSTS=["*"],
                INSTALLED_APPS=["django.contrib.staticfiles"],
                MIDDLEWARE=[],
                TEMPLATES=[
                    {
                        "BACKEND": "django.template.backends.django.DjangoTemplates",
                        "DIRS": [template_dir],
                        "APP_DIRS": False,
                        "OPTIONS": {
                            "loaders": [
                                "django.template.loaders.filesystem.Loader",
                            ]
                        },
                    }
                ],
                STATIC_URL="/static/",
                STATICFILES_DIRS=[static_dir],
            )
        import django

        django.setup()
        self.application = StaticFilesHandler(get_wsgi_application())

    # ------------------------------------------------------------------
    # Helper methods mirroring previous implementation
    # ------------------------------------------------------------------
    @contextmanager
    def _state_context(self):
        self._state_lock.acquire()
        try:
            yield
        finally:
            self._state_lock.release()

    def _extract_parameter_value(self, param_value):
        if param_value.type == ParameterType.PARAMETER_STRING:
            return param_value.string_value
        if param_value.type == ParameterType.PARAMETER_BOOL:
            return param_value.bool_value
        if param_value.type == ParameterType.PARAMETER_INTEGER:
            return param_value.integer_value
        if param_value.type == ParameterType.PARAMETER_DOUBLE:
            return param_value.double_value
        return None

    def _set_parameter_value(self, param_value, value, param_type):
        if param_type == ParameterType.PARAMETER_STRING:
            param_value.string_value = str(value)
        elif param_type == ParameterType.PARAMETER_BOOL:
            param_value.bool_value = bool(value)
        elif param_type == ParameterType.PARAMETER_INTEGER:
            param_value.integer_value = int(value)
        elif param_type == ParameterType.PARAMETER_DOUBLE:
            param_value.double_value = float(value)

    def clear_nodes_list(self) -> None:
        with self._state_context():
            self.nodes_states.clear()

    def set_current_scenario(self, scenario: ScenarioInfo) -> None:
        with self._state_context():
            self.current_scenario = scenario
            self.current_scenario_name = scenario.name

    def set_node_state(self, node_name: str, node_state: str) -> None:
        with self._state_context():
            self.nodes_states[node_name] = node_state

    def set_scenario_state(self, scenario_state: int) -> None:
        with self._state_context():
            self.scenario_state = state_mapping.get(scenario_state, "UNKNOWN")

    def start(self) -> None:
        try:
            if self._server_running:
                self.logger_callback("Server already running")
                return
            self.app_server = ServerThread(self.application, self.logger_callback)
            self.app_server.start()
            self._server_running = True
            self.logger_callback("Webserver started on port 5000")
        except Exception as exc:
            self.logger_callback(f"Failed to start webserver: {exc}")
            raise

    def stop(self) -> None:
        try:
            if not self._server_running:
                return
            self.logger_callback("Shutting down webserver")
            if self.app_server:
                self.app_server.shutdown()
                self.app_server.join(timeout=5.0)
            self._server_running = False
            self.logger_callback("Webserver shutdown complete")
        except Exception as exc:
            self.logger_callback(f"Error during webserver shutdown: {exc}")

    # ------------------------------------------------------------------
    # Utilities for files and directories
    # ------------------------------------------------------------------
    def _get_templates_path(self) -> str:
        try:
            pkg_name = "airaflot_waterdrone"
            package_path = get_package_share_directory(pkg_name)
            workspace_root = os.path.abspath(os.path.join(package_path, "../../../.."))
            return os.path.join(workspace_root, "src", pkg_name, pkg_name, "templates")
        except Exception as exc:
            self.logger_callback(f"Error getting templates path: {exc}")
            return os.path.join(os.getcwd(), "templates")

    def _get_static_path(self) -> str:
        try:
            pkg_name = "airaflot_waterdrone"
            package_path = get_package_share_directory(pkg_name)
            workspace_root = os.path.abspath(os.path.join(package_path, "../../../.."))
            return os.path.join(workspace_root, "src", pkg_name, pkg_name, "static")
        except Exception as exc:
            self.logger_callback(f"Error getting templates path: {exc}")
            return os.path.join(os.getcwd(), "static")

    def _read_file(self, filepath: Path) -> HttpResponse:
        try:
            allowed_paths = [str(self.log_saver.parent_log_dir), STORE_FILES_PATH]
            if not any(allowed in str(filepath) for allowed in allowed_paths):
                return HttpResponse("Invalid file path", status=403)
            if not filepath.is_file():
                return HttpResponse("File not found", status=404)
            file_size = filepath.stat().st_size
            if file_size > 10 * 1024 * 1024:
                return HttpResponse("File too large", status=413)
            content = filepath.read_text(encoding="utf-8")
            return HttpResponse(content, content_type="text/plain")
        except UnicodeDecodeError:
            return HttpResponse(
                "File is not text or uses unsupported encoding", status=415
            )
        except Exception as exc:
            self.logger_callback(f"Error reading file {filepath}: {exc}")
            return HttpResponse(f"Error reading file: {exc}", status=500)

    def _get_filenames(self, directory: Path) -> list:
        try:
            if not directory.exists():
                return []
            filenames = []
            for item in directory.iterdir():
                try:
                    if item.is_file():
                        filenames.append(
                            {
                                "name": item.name,
                                "path": str(item.absolute()),
                                "isdir": False,
                                "items": [],
                            }
                        )
                    elif item.is_dir():
                        sub_items = (
                            self._get_filenames(item)
                            if len(str(item).split(os.sep)) < 20
                            else []
                        )
                        filenames.append(
                            {
                                "name": item.name,
                                "path": str(item.absolute()),
                                "isdir": True,
                                "items": sub_items,
                            }
                        )
                except (PermissionError, OSError) as exc:
                    self.logger_callback(f"Cannot access {item}: {exc}")
                    continue
            return filenames
        except Exception as exc:
            self.logger_callback(f"Error listing directory {directory}: {exc}")
            return []


class ServerThread(threading.Thread):
    """Background thread running a simple WSGI server."""

    def __init__(self, app, logger_callback):
        super().__init__(daemon=True)
        self.app = app
        self.logger_callback = logger_callback
        self.httpd = None

    def run(self) -> None:  # pragma: no cover - executed in thread
        from wsgiref.simple_server import make_server

        try:
            self.httpd = make_server("0.0.0.0", 5000, self.app)
            self.logger_callback("Starting Django server on port 5000")
            self.httpd.serve_forever()
        except Exception as exc:
            self.logger_callback(f"Server error: {exc}")
        finally:
            if self.httpd:
                self.httpd.server_close()
            self.logger_callback("Django server stopped")

    def shutdown(self) -> None:
        try:
            if self.httpd:
                self.httpd.shutdown()
        except Exception as exc:  # pragma: no cover - defensive
            self.logger_callback(f"Error during server shutdown: {exc}")

