# SPDX-License-Identifier: MIT

"""
Open511 class -- handles 511 Data Exchange server queries and infers
arrival times based on last-queried predictions and elapsed time.

API compatible with NextBus
"""

# pylint: disable=bare-except, too-many-instance-attributes, too-many-arguments

import json
import time
import zlib

from adafruit_datetime import datetime

class Open511():
    """ Class to handle 511 Data Exchange prediction times for one route & stop.
    """

    def __init__(self, network, api_key, agency, line, stop, data=None,
                 max_predictions=3, minimum_time=300):
        """ Constructor expects a Requests-capable Network object,
            strings for transit agency, route, and stop ID, plus optional
            per-stop data as defined by an application (e.g. text
            description, but could be an object or tuple of data, or None,
            or whatever's needed by the app), limits for the maximum number
            of future arrivals to predict (limited to server response,
            typically 5) and minimum time below which arrivals are not shown
            (to discourage unsafe bus-chasing).
        """
        self.network = network
        self.api_key = api_key
        self.agency = agency
        self.line = line
        self.stop = stop
        self.data = data
        self.max_predictions = max_predictions
        self.minimum_time = minimum_time
        self.predictions = []
        self.last_query_time = -1000

    def fetch(self):
        """ Contact 511 server and request predictions for one
            agency/route/stop.
        """
        try:
            url = ('http://api.511.org/transit/StopMonitoring' + '?api_key=' + self.api_key +
                   '&agency=' + self.agency + '&stopcode=' + self.stop)
            response = self.network.requests.get(url)
            if response.status_code == 200:
                if response.headers['content-encoding'] == 'gzip':
                    decompressed = zlib.decompress(response.content, 31)
                    if decompressed[:3] == b'\xEF\xBB\xBF': # Remove any UTF-8 BOM
                        decompressed = decompressed[3:]
                    data = json.loads(decompressed)
                else:
                    data = response.json
                self.last_query_time = time.monotonic()
                self.predictions = []
                visits = iter(data['ServiceDelivery']['StopMonitoringDelivery']['MonitoredStopVisit'])
                while len(self.predictions) < self.max_predictions:
                    try:
                        visit = next(visits)
                    except StopIteration:
                        break
                    recorded_at = datetime.fromisoformat(visit['RecordedAtTime'])
                    if recorded_at.timestamp() == 0:
                        # Don't know what this is about. Maybe a bus not in motion yet?
                        recorded_at = datetime.fromisoformat(data['ServiceDelivery']['ResponseTimestamp'])
                    journey = visit['MonitoredVehicleJourney']
                    if journey['LineRef'] == self.line: # Can have same stop for multiple lines.
                        arrival = datetime.fromisoformat(journey['MonitoredCall']['ExpectedArrivalTime'])
                        seconds = (arrival - recorded_at).seconds
                        if seconds >= self.minimum_time:
                            self.predictions.append(seconds)
                self.predictions.sort()
        except:
            # If server query fails, we can keep extrapolating from the
            # last set of predictions and try query again on next pass.
            pass

    def predict(self):
        """ Extrapolate predictions based on last values queried from
            511 server and time elapsed since last query. Predictions
            are returned as a list of integer seconds values.
        """
        times = []
        for predict in self.predictions:
            seconds = predict - (time.monotonic() - self.last_query_time)
            if seconds >= self.minimum_time:
                times.append(seconds)
        return times
