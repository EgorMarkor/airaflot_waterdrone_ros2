# airaflot_waterdrone_ros2
ROS2 packages for Airaflot Water Drone

# Requirements
* ROS2

# Nodes Description

## Peripheral Modules

### 1) echo_sounder
Get data from Echo Sounder

**Services**:
* `/airaflot/echo_sounder/start` (std_srvs/srv/Trigger) - Send start measure command to echo sounder
* `/airaflot/echo_sounder/stop` (std_srvs/srv/Trigger) - Send stop measure command to echo sounder

**Publishers**:
* `/airaflot/echo_sounder/data` (airaflot_msgs/msg/NMEADBT)  - Echo Sounder data (publish period: 0.5 s)

### 2) ecostab_sensors
Get data from Ecostab sensors

**Parameters**:
* `emulate_sensors` (bool) - if True, use sensors emulator, if False, use real sensors

**Publishers**:
* `/airaflot/ecostab_sensors/data` (airaflot_msgs/msg/EcostabSensors) - Data from sensors

### 3) gps_external
Get data from external GPS

**Publishers**:
* `/airaflot/gps_external/data` (airaflot_msgs/msg/NMEAGPGGA) - Data from external GPS

### 4) led_strip
Control Led Strip

**Services**:
* `/airaflot/set_led_mode` (airaflot_msgs/srv/LedStripMode) - Set one of supported modes: ERROR, NOT_READY, NORMAL, PROCESS

### 5) water_sampler_motor
Control motor to up or down payload

**Services**:
* `/airaflot/water_sampler/down_motor` (airaflot_msgs/srv/WaterSamplerMotor) - lower payload to given depth in cm
* `/airaflot/water_sampler/up_motor` (airaflot_msgs/srv/WaterSamplerMotor) - raise payload to given depth in cm

### 6) water_sampler_rele
Control the rele to close the Water Sampler

**Services**:
* `/airaflot/water_sampler/trigger_rele` (std_srvs/srv/Trigger) - trigger rele to close the Water Sampler

## Scenarious

### 1) water_sampler_scenario
Listen to RC commands or mission reach point and run water sampler service

**Subscriptions**:
* `/mavros/rc/in` (mavros_msgs/msg/RCIn) - RC channels topic
* `/airaflot/scenario_state` (airaflot_msgs/msg/ScenarioStateMsg) - Topic with scenario states

**Service Clients**:
* `/airaflot/water_sampler/run_water_sampler` (airaflot_msgs/srv/WaterSampler) - Run water Sampler scenario

**Publishers**:
* `/airaflot/scenario_state` (airaflot_msgs/msg/ScenarioStateMsg) - Topic with scenario states

### 2) water_sampler
Provide service to run water sampler

**Parameters**:
* `use_external_gps` (bool) - if True, use external GPS (gps_external node), if False, use mavros provided GPS

**Services**:
* `/airaflot/water_sampler/run_water_sampler` (airaflot_msgs/srv/WaterSampler) - Lower payload with water sampler, wait for delay, close water sampler and raise it.

**Subscriptions** (depends on use_external_gps parameter):
* `/mavros/global_position/global` (sensor_msgs/msg/NavSatFix) - Mavros provided GPS location
* `/airaflot/gps_external/data` (airaflot_msgs/msg/NMEAGPGGA) - Data from external GPS

**Service Clients**:
* `/airaflot/water_sampler/down_motor` (airaflot_msgs/srv/WaterSamplerMotor) - lower payload to given depth in cm
* `/airaflot/water_sampler/up_motor` (airaflot_msgs/srv/WaterSamplerMotor) - raise payload to given depth in cm
* `/airaflot/water_sampler/trigger_rele` (std_srvs/srv/Trigger) - trigger rele to close the Water Sampler
* `/airaflot/mavros_helpers/set_loiter_mode` (std_srvs/srv/Trigger) - Set mavros Loiter mode (hold current position)
* `/airaflot/mavros_helpers/set_previous_mode` (std_srvs/srv/Trigger) - Set mavros mode that was before using set_loiter_mode service

**Publishers**:
* `/airaflot/scenario_state` (airaflot_msgs/msg/ScenarioStateMsg) - Topic with scenario states
* `/airaflot/data_to_send` (airaflot_msgs/msg/DataToSend) - Data for sender nodes (publish GPS, timestamp and depth of sampling)

## Senders

### 1) file_saver
Save info from `data_to_send` topic in filesystem, and publish the name of the finished file in `file_finished`.

**Parameters**:
* `file_saver_mode` (string) - supported modes: "one_meas_per_file" (new file on every message), "from_start_to_last" (start new file on MESSAGE_POS_START message_position), "permanently" (starts new file after timeout or count of measuremets)
* `file_prefix` (string) - prefix of the name of the files

**Subscriptions**:
* `/airaflot/data_to_send` (airaflot_msgs/msg/DataToSend) - Data from scenario nodes

**Publishers**:
* `/airaflot/file_saver/file_finished` (std_msgs/msg/String) - The full path to the finished file

# Install
Clone packages to your ROS2 workspase:
```bash
cd ros2_ws/src
git clone https://github.com/LoSk-p/airaflot_waterdrone_ros2.git
mv airaflot_waterdrone_ros2/airaflot_waterdrone airaflot_waterdrone
mv airaflot_waterdrone_ros2/airaflot_msgs airaflot_msgs
rm -r airaflot_waterdrone_ros2
```

Build packages
```bash
cd ros2_ws
colcon build
source install/setup.bash
```
