from enum import Enum

class LedColor:
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    YELLOW = (255, 255, 0)
    CYAN = (0, 255, 255)
    MAGENTA = (255, 0, 255)
    ORANGE = (255, 170, 0)

class LedMode(Enum):
    ERROR = (LedColor.RED, LedColor.RED, False)
    NORMAL = (LedColor.WHITE, LedColor.WHITE, False)
    PROCESS = (LedColor.WHITE, LedColor.BLUE, True)

    def __init__(self, main_color, secondary_color, is_blink):
        self.main_color = main_color
        self.secondary_color = secondary_color
        self.is_blink = is_blink