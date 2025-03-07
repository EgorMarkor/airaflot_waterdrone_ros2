from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource

def generate_launch_description():
    return LaunchDescription([
        # Nodes from airaflot_waterdrone package
        Node(
            package='airaflot_waterdrone',
            executable='rc_controller',
            name='rc_controller',
        ),
        Node(
            package='airaflot_waterdrone',
            executable='water_sampler_servo',
            name='water_sampler_servo',
        ),
        Node(
            package='airaflot_waterdrone',
            executable='water_sampler_motor',
            name='water_sampler_motor',
        ),
        Node(
            package='airaflot_waterdrone',
            executable='water_sampler',
            name='water_sampler',
        ),
        Node(
            package='airaflot_waterdrone',
            executable='mode_controller_helper',
            name='mode_controller_helper',
        ),
    ])