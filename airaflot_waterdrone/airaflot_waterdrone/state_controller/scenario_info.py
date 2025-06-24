from rcl_interfaces.msg import Parameter, ParameterType
from airaflot_msgs.srv import WaterSampler
import typing as tp

from ..const_names import (
    OPERATING_MODE_ONE_MEAS_PER_FILE,
    OPERATING_MODE_FROM_START_TO_LAST,
    OPERATING_MODE_PERMANENTLY,
    FILE_SAVER_MODE_PARAM,
    FILE_PREFIX_PARAM,
    USE_EXTERNAL_GPS_PARAM,
    MEASUREMENT_INTERVAL_PARAM,
    MEASUREMENT_DELAY_PARAM,
    EMULATE_SENSORS_PARAM,
    SAMPLING_DELAY_PARAM,
    DEFAULT_DEPTH_PARAM,
    EMULATE_MOTOR_PARAM,
    EMULATE_RELE_PARAM,
    RUN_WATER_SAMPLER_SERVICE_NAME,
    START_MEASURE_SERVICE_NAME,
    USE_OXXYGEN_RAPAM,
    USE_CONDUCTIVITY_RAPAM,
    USE_NITRITE_RAPAM,
    USE_ORP_RAPAM,
    USE_PH_RAPAM,
    SBER_URL_ECHOSOUNDER_PARAM,
    SBER_URL_SENSORS_PARAM,
    SBER_URL_WATERSAMPLER_PARAM
)

from ..senders.sber.config import DEFAUL_URL_ECHOSOUNDER, DEFAUL_URL_SENSORS, DEFAUL_URL_WATERSAMPLER

class ScenarioInfo:
    def __init__(self, name: str, node_list: list[str], parameters: dict[str, list[Parameter]]) -> None:
        self.name = name
        self.node_list = node_list
        self.parameters = parameters
        self.user_set_parameteres = []
        self.main_service_info: MainServiceInfo | None = None

    def get_user_set_parameters(self) -> list[Parameter]:
        return self.user_set_parameteres.copy()
    
    def set_parameters_from_user(self, user_parameters: list[Parameter]) -> None:
        for node_name in self.parameters:
            for parameter in self.parameters[node_name]:
                for new_parameter in user_parameters:
                    if new_parameter.name == parameter.name:
                        parameter.value = new_parameter.value

    
    def _create_parameter_str(self, name: str, value: str) -> Parameter:
        param = Parameter()
        param.name = name
        param.value.type = ParameterType.PARAMETER_STRING
        param.value.string_value = value
        return param
    
    def _create_parameter_bool(self, name: str, value: bool) -> Parameter:
        param = Parameter()
        param.name = name
        param.value.type = ParameterType.PARAMETER_BOOL
        param.value.bool_value = value
        return param
    
    def _create_parameter_int(self, name: str, value: int) -> Parameter:
        param = Parameter()
        param.name = name
        param.value.type = ParameterType.PARAMETER_INTEGER
        param.value.integer_value = value
        return param

class WaterSamplerScenario(ScenarioInfo):
    def __init__(self):
        name = "Water Sampler"
        node_list = [
            "/water_sampler_motor",
            "/water_sampler_rele",
            "/water_sampler",
            "/water_sampler_scenario",
            "/file_saver",
            "/common_sender"
        ]
        parameters: dict[str, list[Parameter]] = {
            "/file_saver": [
                self._create_parameter_str(FILE_SAVER_MODE_PARAM, OPERATING_MODE_ONE_MEAS_PER_FILE),
                self._create_parameter_str(FILE_PREFIX_PARAM, "water_sampler"),
            ],
            "/water_sampler": [
                self._create_parameter_int(SAMPLING_DELAY_PARAM, 30),
                self._create_parameter_int(DEFAULT_DEPTH_PARAM, 30)
            ],
            "/water_sampler_motor": [
                self._create_parameter_bool(EMULATE_MOTOR_PARAM, False)
            ],
            "/water_sampler_rele": [
                self._create_parameter_bool(EMULATE_RELE_PARAM, False)
            ],
            "/common_sender": [
                self._create_parameter_bool("use_sber_sender", True),
                self._create_parameter_str(SBER_URL_ECHOSOUNDER_PARAM, DEFAUL_URL_ECHOSOUNDER),
                self._create_parameter_str(SBER_URL_SENSORS_PARAM, DEFAUL_URL_SENSORS),
                self._create_parameter_str(SBER_URL_WATERSAMPLER_PARAM, DEFAUL_URL_WATERSAMPLER),
            ]
        }
        super().__init__(name, node_list, parameters)
        self.user_set_parameteres = [
            self._create_parameter_int(SAMPLING_DELAY_PARAM, 30),
            self._create_parameter_int(DEFAULT_DEPTH_PARAM, 30),
            self._create_parameter_bool(EMULATE_RELE_PARAM, False),
            self._create_parameter_bool(EMULATE_MOTOR_PARAM, False),
            self._create_parameter_bool("use_sber_sender", True),
            self._create_parameter_str(SBER_URL_ECHOSOUNDER_PARAM, DEFAUL_URL_ECHOSOUNDER),
            self._create_parameter_str(SBER_URL_SENSORS_PARAM, DEFAUL_URL_SENSORS),
            self._create_parameter_str(SBER_URL_WATERSAMPLER_PARAM, DEFAUL_URL_WATERSAMPLER),
        ]
        request = WaterSampler.Request()
        request.depth = 0
        self.main_service_info = MainServiceInfo(name=RUN_WATER_SAMPLER_SERVICE_NAME, type=WaterSampler, request=request)

class EcostabSensorsScenario(ScenarioInfo):
    def __init__(self):
        name = "Ecostab Sensors"
        node_list = [
            # "/water_sampler_motor",
            "/ecostab_sensors_publisher",
            "/ecostab_sensors_scenario",
            "/file_saver",
            "/common_sender"
        ]
        parameters = {
            "/file_saver": [
                self._create_parameter_str(FILE_SAVER_MODE_PARAM, OPERATING_MODE_FROM_START_TO_LAST),
                self._create_parameter_str(FILE_PREFIX_PARAM, "ecostab_sensors"),
            ],
            "/ecostab_sensors_publisher": [
                self._create_parameter_bool(EMULATE_SENSORS_PARAM, False),
                self._create_parameter_bool(USE_PH_RAPAM, True),
                self._create_parameter_bool(USE_CONDUCTIVITY_RAPAM, True),
                self._create_parameter_bool(USE_NITRITE_RAPAM, True),
                self._create_parameter_bool(USE_ORP_RAPAM, True),
                self._create_parameter_bool(USE_OXXYGEN_RAPAM, True),
            ],
            "/ecostab_sensors_scenario": [
                self._create_parameter_bool(USE_EXTERNAL_GPS_PARAM, False),
                self._create_parameter_int(MEASUREMENT_INTERVAL_PARAM, 5),
                self._create_parameter_int(MEASUREMENT_DELAY_PARAM, 30),
                # self._create_parameter_int(DEFAULT_DEPTH_PARAM, 30)
            ],
            # "/water_sampler_motor": [
            #     self._create_parameter_bool(EMULATE_MOTOR_PARAM, False)
            # ],
            "/common_sender": [
                self._create_parameter_bool("use_sber_sender", True),
                self._create_parameter_str(SBER_URL_ECHOSOUNDER_PARAM, DEFAUL_URL_ECHOSOUNDER),
                self._create_parameter_str(SBER_URL_SENSORS_PARAM, DEFAUL_URL_SENSORS),
                self._create_parameter_str(SBER_URL_WATERSAMPLER_PARAM, DEFAUL_URL_WATERSAMPLER),
            ]
        }
        super().__init__(name, node_list, parameters)
        self.user_set_parameteres = [
            self._create_parameter_bool(EMULATE_SENSORS_PARAM, False),
            self._create_parameter_int(MEASUREMENT_INTERVAL_PARAM, 5),
            self._create_parameter_int(MEASUREMENT_DELAY_PARAM, 30),
            # self._create_parameter_int(DEFAULT_DEPTH_PARAM, 30),
            # self._create_parameter_bool(EMULATE_MOTOR_PARAM, False),
            self._create_parameter_bool(USE_PH_RAPAM, True),
            self._create_parameter_bool(USE_CONDUCTIVITY_RAPAM, True),
            self._create_parameter_bool(USE_NITRITE_RAPAM, True),
            self._create_parameter_bool(USE_ORP_RAPAM, True),
            self._create_parameter_bool(USE_OXXYGEN_RAPAM, True),
            self._create_parameter_bool("use_sber_sender", True),
            self._create_parameter_str(SBER_URL_ECHOSOUNDER_PARAM, DEFAUL_URL_ECHOSOUNDER),
            self._create_parameter_str(SBER_URL_SENSORS_PARAM, DEFAUL_URL_SENSORS),
            self._create_parameter_str(SBER_URL_WATERSAMPLER_PARAM, DEFAUL_URL_WATERSAMPLER),
        ]
        request = WaterSampler.Request()
        request.depth = 0
        self.main_service_info = MainServiceInfo(name=START_MEASURE_SERVICE_NAME, type=WaterSampler, request=request)

class EchoSounderScenario(ScenarioInfo):
    def __init__(self):
        name = "Echo Sounder"
        node_list = [
            "/echo_sounder",
            "/gps_external",
            "/echo_sounder_scenario",
            "/file_saver",
            "/common_sender"
        ]
        parameters = {
            "/file_saver": [
                self._create_parameter_str(FILE_SAVER_MODE_PARAM, OPERATING_MODE_PERMANENTLY),
                self._create_parameter_str(FILE_PREFIX_PARAM, "echo_sounder"),
            ],
            "/echo_sounder_scenario": [
                self._create_parameter_bool(USE_EXTERNAL_GPS_PARAM, True),
            ],
            "/common_sender": [
                self._create_parameter_bool("use_sber_sender", True),
                self._create_parameter_str(SBER_URL_ECHOSOUNDER_PARAM, DEFAUL_URL_ECHOSOUNDER),
                self._create_parameter_str(SBER_URL_SENSORS_PARAM, DEFAUL_URL_SENSORS),
                self._create_parameter_str(SBER_URL_WATERSAMPLER_PARAM, DEFAUL_URL_WATERSAMPLER),
            ]
        }
        super().__init__(name, node_list, parameters)
        self.user_set_parameteres = [
            self._create_parameter_bool("use_sber_sender", True),
            self._create_parameter_str(SBER_URL_ECHOSOUNDER_PARAM, DEFAUL_URL_ECHOSOUNDER),
            self._create_parameter_str(SBER_URL_SENSORS_PARAM, DEFAUL_URL_SENSORS),
            self._create_parameter_str(SBER_URL_WATERSAMPLER_PARAM, DEFAUL_URL_WATERSAMPLER),
        ]

class MainServiceInfo:
    def __init__(self, name: str, type, request):
        self.name = name
        self.request = request
        self.type = type

SUPPORTED_SCENARIOS = [EchoSounderScenario(), WaterSamplerScenario(), EcostabSensorsScenario()]