from requests import post
from copy import deepcopy
import time

from rclpy.impl.rcutils_logger import RcutilsLogger

from ..sender_interface import Sender
from .config import DEFAUL_URL_ECHOSOUNDER, DEFAUL_URL_SENSORS, DEFAUL_URL_WATERSAMPLER
from ...const_names import SBER_URL_ECHOSOUNDER_PARAM, SBER_URL_SENSORS_PARAM, SBER_URL_WATERSAMPLER_PARAM

class SberSender(Sender):
    def __init__(self, logger: RcutilsLogger):
        name = "sber"
        parameters_default = [
            {"name": SBER_URL_ECHOSOUNDER_PARAM, "default_value": DEFAUL_URL_ECHOSOUNDER},
            {"name": SBER_URL_SENSORS_PARAM, "default_value": DEFAUL_URL_SENSORS},
            {"name": SBER_URL_WATERSAMPLER_PARAM, "default_value": DEFAUL_URL_WATERSAMPLER},
            ]
        super().__init__(name, parameters_default)
        self._urls: dict[str, str] = {
            SBER_URL_ECHOSOUNDER_PARAM: "",
            SBER_URL_SENSORS_PARAM: "",
            SBER_URL_WATERSAMPLER_PARAM: "",
            }
        self.logger = logger

    def setup(self) -> bool:
        self.logger.info(f"Start setup Sber Sender, Parameters: {self._parameters}")
        try:
            for url_name in self._parameters:
                self._urls[url_name] = self._parameters[url_name].get_parameter_value().string_value
                if not self._urls[url_name]:
                    self.logger.error(f"Sber url {url_name} is empty: {self._urls[url_name]}")
                    return False
        except Exception as e:
            self.logger.error(f"Can't get sber url with error: {e}")
            return False
        self.logger.info(f"Sber Sender successfully set up with urls: {self._urls}")
        return True
    
    def send(self, data: dict) -> bool:
        if len(data["measurements"]) == 0:
            self.logger.warning(f"Data is empty, will not send")
            return True
        url = self._get_url_for_data(data)
        if url is None:
            self.logger.warning(f"Data is incorrect, will not send")
            return False
        while len(data["measurements"]) > 50:
            new_data = deepcopy(data)
            slice_meas = data["measurements"][:50]
            new_data["measurements"] = slice_meas
            data["measurements"] = data["measurements"][50:]
            formatted_data = self._format_data(new_data)
            if not self._post_request(formatted_data, url):
                return False
        formatted_data = self._format_data(data)
        res = self._post_request(formatted_data, url)
        return res

    def _get_url_for_data(self, data: dict) -> str | None:
        url = None
        if "temperature" in data["measurements"][0]:
            url = self._urls[SBER_URL_SENSORS_PARAM]
        elif "depth" in data["measurements"][0]:
            url = self._urls[SBER_URL_ECHOSOUNDER_PARAM]
        elif "sampling_depth" in data["measurements"][0]:
            url = self._urls[SBER_URL_WATERSAMPLER_PARAM]
        return url

    def _post_request(self, data: dict, url: str) -> bool:
        try:
            time.sleep(0.5)
            self.logger.info(f"Start sending data to {url}, data: {data}")
            res = post(url, json=data)
        except Exception as e:
            self.logger.error(f"Error in sber post request to {url}: {e}")
            return False
        if res.status_code == 200:
            self.logger.info(f"Request to {url} was successful")
            return True
        else:
            self.logger.info(f"Request to {url} was not successful, status code {res.status_code}, message: {res.text}")
            return False

    def _format_data(self, data: dict) -> dict:
        formatted_data = {"boat_id": "12345", "measurements": []}
        i = 0
        for meas in data["measurements"]:
            gps = meas.pop("gps")
            timestamp = meas.pop("timestamp")
            new_meas = {"timestamp": timestamp}
            new_meas["GPS"] = {
                "latitude": gps[0],
                "longitude": gps[1]
            }
            if "temperature" in meas:
                new_meas["sensors"] = meas.copy()
            else:
                new_meas.update(meas)
            formatted_data["measurements"].append(new_meas)
            i += 1
        return formatted_data