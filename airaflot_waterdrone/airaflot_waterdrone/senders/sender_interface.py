from abc import ABC, abstractmethod
from rclpy.parameter import Parameter
from copy import deepcopy

class Sender(ABC):
    def __init__(self, name: str, parameters_default: list[dict]):
        self._parameters_default: list[dict] = parameters_default
        self._name = name
        self._parameters: dict[str, Parameter] = {}

    @abstractmethod
    def setup(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def send(self, data: dict) -> bool:
        raise NotImplementedError

    @property
    def parameters_default(self) -> list[Parameter]:
        return deepcopy(self._parameters_default)
    
    @property
    def name(self) -> str:
        return self._name
    
    def set_parameter(self, parameter: Parameter) -> None:
        self._parameters[parameter.name] = parameter
