from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime
from logger_setup import app_logger

class InfluxDBManager:
    def __init__(self, url, token, org, bucket):
        self.client = InfluxDBClient(url=url, token=token)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()
        self.bucket = bucket
        self.org = org

    def write_data(self, measurement, fields, tags=None):
        try:
            point = Point(measurement)
            for key, value in fields.items():
                if isinstance(value, (int, float)):
                    point = point.field(key, value)
                else:
                    point = point.tag(key, str(value))
            if tags:
                for key, value in tags.items():
                    point = point.tag(key, str(value))
            
            point = point.time(datetime.utcnow(), WritePrecision.NS)
            
            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
        except Exception as e:
            app_logger.error(f"Error writing to InfluxDB: {e}")

    def query_data(self, measurement, start="-1h"):
        try:
            query = f'''
            from(bucket:"{self.bucket}")
                |> range(start: {start})
                |> filter(fn: (r) => r._measurement == "{measurement}")
            '''
            result = self.query_api.query(org=self.org, query=query)
            
            for table in result:
                for record in table.records:
                    yield {
                        'time': record.get_time(),
                        'measurement': record.get_measurement(),
                        'field': record.get_field(),
                        'value': record.get_value()
                    }
        except Exception as e:
            app_logger.error(f"Error querying data from InfluxDB: {e}")
            yield None

    def write_test_point(self):
        self.write_data("tick_data", {"last_price": 100.0})

    def query_test_points(self):
        return list(self.query_data("tick_data"))

    def close(self):
        self.client.close()