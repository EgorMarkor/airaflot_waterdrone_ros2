from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'airaflot_waterdrone'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
    ],
    install_requires=['setuptools', 'airaflot_msgs', 'mavros_msgs', 'sensor_msgs', 'pymodbus==3.6.8', 'Flask==3.1.0', 'adafruit-circuitpython-neopixel==6.3.15', 'pyserial==3.5'],
    zip_safe=True,
    maintainer='airalab',
    maintainer_email='airaflot@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
                'water_sampler_scenario = airaflot_waterdrone.scenarios.water_sampler.water_sampler_scenario:main',
                'water_sampler_rele = airaflot_waterdrone.peripheral_modules.water_sampler.rele:main',
                'water_sampler_motor = airaflot_waterdrone.peripheral_modules.water_sampler.motor:main',
                'water_sampler = airaflot_waterdrone.scenarios.water_sampler.water_sampler:main',
                'ecostab_sensors_publisher = airaflot_waterdrone.peripheral_modules.ecostab_sensors.publisher:main', 
                'echo_sounder_publisher = airaflot_waterdrone.peripheral_modules.echo_sounder.echo_sounder:main',
                'mode_controller_helper = airaflot_waterdrone.mavros_helpers.mode_controller:main',
                'gps_external = airaflot_waterdrone.peripheral_modules.gps_external.gps_external:main',
                'file_saver = airaflot_waterdrone.senders.file_saver.file_saver:main',
                'ecostab_sensors_scenario = airaflot_waterdrone.scenarios.ecostab_sensors.data_formatter:main',
                'state_controller = airaflot_waterdrone.state_controller.state_controller:main',
                'led_strip = airaflot_waterdrone.peripheral_modules.led_strip.led_strip:main'
        ],
    },
)
