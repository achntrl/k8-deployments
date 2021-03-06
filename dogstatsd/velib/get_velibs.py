import json
import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from datadog.dogstatsd.base import DogStatsd
from datadog.api.constants import CheckStatus
import json_log_formatter
import requests
from pytz import utc

CHARONNE = "charonne"
CHARONNE_ID = "11004"
TRAVERSIERE = "traversiere"
TRAVERSIERE_ID = "12004"
STATE_OK = "Operative"
STATE_KO = "Close"
HOST = os.getenv("DOGSTATSD_HOST", "192.168.0.100")
PORT = int(os.getenv("DOGSTATSD_PORT", 30125))


class JSONFormatterWithLevel(json_log_formatter.JSONFormatter):
    def json_record(self, message, extra, record):
        if "status" not in extra:
            extra["status"] = record.levelname
        return super().json_record(message, extra, record)


formatter = JSONFormatterWithLevel()
json_handler = logging.StreamHandler()
json_handler.setFormatter(formatter)
logger = logging.getLogger("my_json")
logger.addHandler(json_handler)
logger.setLevel(logging.INFO)


def get_state(station):
    state_status = station["station"]["state"]
    if state_status == STATE_OK:
        return CheckStatus.OK
    if state_status == STATE_KO:
        return CheckStatus.CRITICAL

    return CheckStatus.WARNING


def get_station_name(station):
    station_id = station["station"]["code"]
    if station_id == CHARONNE_ID:
        return CHARONNE
    if station_id == TRAVERSIERE_ID:
        return TRAVERSIERE


def get_tag(station):
    return ["station:" + get_station_name(station)]


def get_velibs():
    r = requests.get(
        "https://www.velib-metropole.fr/webapi/map/details?gpsTopLatitude=48.85240750385378&gpsTopLongitude=2.378431586815509&gpsBotLatitude=48.850687689726385&gpsBotLongitude=2.3723489091318015&zoomLevel=17.174858916253687"
    )
    velib_stations = json.loads(r.content.decode("utf-8"))
    statsd = DogStatsd(host=HOST, port=PORT, constant_tags=["host:api"])

    for station in velib_stations:
        tag = get_tag(station)
        bike_nb = station["nbBike"]
        ebike_nb = station["nbEbike"]
        free_dock_nb = station["nbFreeDock"] + station["nbFreeEDock"]
        dock_nb = station["nbDock"] + station["nbEDock"]
        statsd.gauge("velib.regular_bikes", bike_nb, tags=tag)
        statsd.gauge("velib.electric_bikes", ebike_nb, tags=tag)
        statsd.gauge("velib.free_docks", free_dock_nb, tags=tag)
        statsd.gauge("velib.total_docks", dock_nb, tags=tag)
        statsd.service_check(
            "velib.station_state",
            get_state(station),
            tags=tag,
            message=station["station"]["state"],
        )
        logger.info(
            "Found {} ebike(s), {} bike(s), {} free dock(s) on {} dock(s). The station is {}".format(
                ebike_nb, bike_nb, free_dock_nb, dock_nb, station["station"]["state"]
            ),
            extra={"station": get_station_name(station)},
        )


if __name__ == "__main__":
    sched = BlockingScheduler()
    sched.configure(timezone=utc)
    sched.add_job(get_velibs, "cron", second="0")
    sched.start()
