### Water Sampler Servo Node ###
TRIGGER_RELE_SERVICE_NAME = "/airaflot/water_sampler/trigger_rele"

### Water Sampler Motor Node ###
DOWN_WATER_SAMPLER_MOTOR_SERVICE_NAME = "/airaflot/water_sampler/down_motor"
UP_WATER_SAMPLER_MOTOR_SERVICE_NAME = "/airaflot/water_sampler/up_motor"

### Water Sampler Node ###
RUN_WATER_SAMPLER_SERVICE_NAME = "/airaflot/water_sampler/run_water_sampler"
SAMPLING_DELAY_PARAM = "sampling_delay"

### Ecostab Sensors ###
ECOSTAB_SENSORS_TOPIC_NAME = "/airaflot/ecostab_sensors/data"
EMULATE_SENSORS_PARAM = "emulate_sensors"

### Echo Sounder ###
ECHOSOUNDER_START_SERVICE_NAME = "/airaflot/echo_sounder/start"
ECHOSOUNDER_STOP_SERVICE_NAME = "/airaflot/echo_sounder/stop"
ECHOSOUNDER_DATA_TOPIC = "/airaflot/echo_sounder/data"

### Mavros Utils ###
SET_LOITER_MODE_SERVICE_NAME = "/airaflot/mavros_helpers/set_loiter_mode"
SET_PREVIOUS_MODE_SERVICE_NAME = "/airaflot/mavros_helpers/set_previous_mode"

### GPS External ###
GPS_EXTERNAL_DATA_TOPIC_NAME = "/airaflot/gps_external/data"

### File Saver ###
FILE_FINISHED_TOPIC_NAME = "/airaflot/file_saver/file_finished"
OPERATING_MODE_ONE_MEAS_PER_FILE = "one_meas_per_file"
OPERATING_MODE_FROM_START_TO_LAST = "from_start_to_last"
OPERATING_MODE_PERMANENTLY = "permanently"
FILE_SAVER_MODE_PARAM = "file_saver_mode"
FILE_PREFIX_PARAM = "file_prefix"

### Ecostab Sensors Scenario ###
START_MEASURE_SERVICE_NAME = "/airaflot/ecostab_sensors_scenario/start_measure"
USE_EXTERNAL_GPS_PARAM = "use_external_gps"
MEASUREMENT_INTERVAL_PARAM = "measurement_interval"
MEASUREMENT_DELAY_PARAM = "measurement_delay"
DEFAULT_DEPTH_PARAM = "default_depth"

### Scenarios Service ###
DATA_TO_SEND_TOPIC_NAME = "/airaflot/data_to_send"
SCENARIO_STATE_TOPIC_NAME = "/airaflot/scenario_state"

### Led Strip ###
LED_STRIP_SET_MODE_SERVICE = "/airaflot/set_led_mode"