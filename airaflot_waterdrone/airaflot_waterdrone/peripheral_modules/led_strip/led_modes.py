from enum import Enum
from airaflot_msgs.srv import LedStripMode

class LedColor:
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    YELLOW = (255, 255, 0)
    CYAN = (0, 255, 255)
    MAGENTA = (255, 0, 255)
    ORANGE = (255, 110, 0)

class LedMode(Enum):
    ERROR = (0, LedColor.RED, LedColor.RED, False)
    NOT_READY = (1, LedColor.BLACK, LedColor.ORANGE, True)
    NORMAL = (2, LedColor.WHITE, LedColor.WHITE, False)
    PROCESS = (3, LedColor.WHITE, LedColor.BLUE, True)

    def __init__(self, mode_id, main_color, secondary_color, is_blink):
        self.mode_id = mode_id
        self.main_color = main_color
        self.secondary_color = secondary_color
        self.is_blink = is_blink

    @staticmethod
    def from_ros_srv(request: LedStripMode.Request) -> 'LedMode':
        for mode in LedMode:
            if mode.mode_id == request.mode:
                return mode
        raise ValueError(f"Unknown LED mode ID: {request.mode}")