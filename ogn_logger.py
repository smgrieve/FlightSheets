
from __future__ import annotations
import datetime as dt
import logging
import socket
import threading
import time
from contextlib import contextmanager
from typing import IO, Any, Dict, Iterator, Optional, Set

from collections import defaultdict
import aprslib  # type: ignore
from mysql.connector import pooling  # type: ignore

###############################################################################
# Configuration
###############################################################################
OGN_HOST   = "aprs.glidernet.org"
OGN_PORT   = 14580
OGN_FILTER = "r/31.7033/-98.1231/200 s/g"
CALLSIGN   = "N0CALL"
PASSCODE   = "-1"
VERSION    = "ogn_logger 2.0"

SOCK_CONNECT_TIMEOUT = 10.0
SOCK_READ_TIMEOUT    = 60.0

DB_CONFIG = {
    "host": "localhost",
    "user": "",
    "password": "",
    "database": "",
    "pool_name": "ogn_pool",
    "pool_size": 10,
    "autocommit": True,
}

BACKOFF_START   = 5
BACKOFF_MAX     = 300
REFRESH_IDS_SEC = 300
FLIGHT_REFRESH  = 300

###############################################################################
# Logging
###############################################################################
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ogn_logger")

###############################################################################
# Database pool & table bootstrap
###############################################################################

db_pool = pooling.MySQLConnectionPool(**DB_CONFIG)


def ensure_tables() -> None:
    conn = db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS ogn_positions (
                        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                        flarm_id VARCHAR(12) NOT NULL,
                        position_time DATETIME(6) NOT NULL,
                        latitude DOUBLE NOT NULL,
                        longitude DOUBLE NOT NULL,
                        speed DOUBLE,
                        altitude DOUBLE,
                        vertical_speed FLOAT,
                        course DOUBLE,
                        KEY idx_time  (position_time),
                        KEY idx_flarm (flarm_id)
                    ) ENGINE=InnoDB"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS ogn_flights (
                        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                        flarm_id VARCHAR(12) NOT NULL,
                        takeoff_time DATETIME(6) NOT NULL,
                        landing_time DATETIME(6) NOT NULL,
                        flight_secs INT NOT NULL,
                        take_lat DOUBLE,
                        take_lng DOUBLE,
                        land_lat DOUBLE,
                        land_lng DOUBLE,
                        UNIQUE KEY uniq_flight (flarm_id, takeoff_time)
                    ) ENGINE=InnoDB"""
            )
    finally:
        conn.close()

###############################################################################
# Whitelist loader
###############################################################################

def load_whitelist() -> Set[str]:
    conn = db_pool.get_connection()
    ids: Set[str] = set()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT flarm_id FROM aircraft WHERE flarm_id IS NOT NULL")
            ids.update(row[0] for row in cur.fetchall())
    finally:
        conn.close()
    logger.info("Whitelist loaded â %d FLARM IDs", len(ids))
    return ids

###############################################################################
# OGN stream
###############################################################################
LOGIN_CMD = f"user {CALLSIGN} pass {PASSCODE} vers {VERSION} filter {OGN_FILTER}\n".encode()

@contextmanager
def open_ogn_stream() -> Iterator[IO[bytes]]:
    sock = socket.create_connection((OGN_HOST, OGN_PORT), timeout=SOCK_CONNECT_TIMEOUT)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.settimeout(SOCK_READ_TIMEOUT)
    sock.sendall(LOGIN_CMD)
    try:
        with sock.makefile("rb") as stream:
            yield stream
    finally:
        sock.close()

###############################################################################
# Insert position with vertical speed
###############################################################################

def insert_position(d: Dict[str, Any]) -> None:
    conn = db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ogn_positions
                       (flarm_id, position_time, latitude, longitude, speed, altitude, vertical_speed, course)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    d["flarm_id"], d["timestamp"], d["lat"], d["lng"],
                    d["speed"], d["altitude"], d.get("vertical_speed"), d["course"]
                )
            )
    finally:
        conn.close()

###############################################################################
# Parse APRS packet
###############################################################################

def parse_aprs(raw: bytes) -> Optional[Dict[str, Any]]:
    try:
        f = aprslib.parse(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return None
    if f.get("latitude") is None or f.get("longitude") is None:
        return None
    return {
        "flarm_id": f.get("from"),
        "timestamp": dt.datetime.utcnow(),
        "lat": f["latitude"],
        "lng": f["longitude"],
        "speed": f.get("speed"),
        "altitude": f.get("altitude") * 3.28084 if f.get("altitude") is not None else None,
        "course": f.get("course"),
    }

###############################################################################
# Logger thread
###############################################################################

last_positions: Dict[str, Dict[str, Any]] = defaultdict(dict)

def logger_thread():
    whitelist = load_whitelist()
    last_reload = time.monotonic()
    backoff = BACKOFF_START

    while True:
        try:
            with open_ogn_stream() as stream:
                logger.info("OGN stream connected (%s)", OGN_FILTER)
                for raw in stream:
                    if time.monotonic() - last_reload >= REFRESH_IDS_SEC:
                        whitelist = load_whitelist()
                        last_reload = time.monotonic()

                    d = parse_aprs(raw)
                    if d and d["flarm_id"] in whitelist:
                        fid = d["flarm_id"]
                        now = d["timestamp"]

                        prev = last_positions.get(fid)
                        if prev:
                            dt_sec = (now - prev["timestamp"]).total_seconds()
                            if dt_sec > 0 and d["altitude"] is not None and prev.get("altitude") is not None:
                                dz = d["altitude"] - prev["altitude"]
                                d["vertical_speed"] = dz / dt_sec
                        last_positions[fid] = d

                        insert_position(d)
            backoff = BACKOFF_START
        except Exception as exc:
            logger.error("Stream error: %s â retry in %s s", exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)

###############################################################################
# Flight extractor
###############################################################################

FLIGHT_QUERY = """
WITH params AS (
  SELECT 1350 AS field_elev_ft, 200 AS climb_thresh, 30 AS land_thresh, 600 AS gap_sec
),
ordered AS (
  SELECT p.*, a.field_elev_ft, a.climb_thresh, a.land_thresh, a.gap_sec,
         ROW_NUMBER() OVER (PARTITION BY flarm_id ORDER BY position_time) AS rn,
         UNIX_TIMESTAMP(position_time) AS ts
  FROM ogn_positions p
  JOIN params a ON 1
  WHERE position_time >= UTC_TIMESTAMP() - INTERVAL 2 DAY
),
gaps AS (
  SELECT *,
    CASE WHEN altitude >= field_elev_ft + climb_thresh THEN 1 ELSE 0 END AS is_airborne,
    CASE WHEN altitude <= field_elev_ft + land_thresh  THEN 1 ELSE 0 END AS is_ground,
    LAG(altitude) OVER (PARTITION BY flarm_id ORDER BY rn) AS prev_altitude,
    LAG(ts)       OVER (PARTITION BY flarm_id ORDER BY rn) AS prev_ts
  FROM ordered
),
tagged AS (
  SELECT *,
    CASE WHEN ts - prev_ts > gap_sec THEN 1 ELSE 0 END AS is_big_gap,
    CASE WHEN is_airborne = 1 AND (prev_altitude IS NULL OR prev_altitude < field_elev_ft + climb_thresh)
              AND (ts - prev_ts <= gap_sec OR prev_ts IS NULL)
         THEN 1
         WHEN ts - prev_ts > gap_sec THEN 1
         ELSE 0 END AS new_flight
  FROM gaps
),
segments AS (
  SELECT *,
    SUM(new_flight) OVER (PARTITION BY flarm_id ORDER BY rn) AS flight_no
  FROM tagged
),
flight_bounds AS (
  SELECT flarm_id, flight_no,
         MIN(CASE WHEN is_airborne = 1 THEN position_time END) AS takeoff_time,
         MAX(CASE WHEN is_ground = 1 THEN position_time END) AS landing_time,
         MIN(CASE WHEN is_airborne = 1 THEN latitude END) AS take_lat,
         MIN(CASE WHEN is_airborne = 1 THEN longitude END) AS take_lng,
         MAX(CASE WHEN is_ground = 1 THEN latitude END) AS land_lat,
         MAX(CASE WHEN is_ground = 1 THEN longitude END) AS land_lng
  FROM segments
  GROUP BY flarm_id, flight_no
  HAVING takeoff_time IS NOT NULL AND landing_time IS NOT NULL
)
SELECT flarm_id, takeoff_time, landing_time,
       TIMESTAMPDIFF(SECOND, takeoff_time, landing_time) AS flight_secs,
       take_lat, take_lng, land_lat, land_lng
FROM flight_bounds;
"""

def extract_flights():
    conn = db_pool.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(FLIGHT_QUERY)
            rows = cur.fetchall()
            logger.info("Extracted %d flights", len(rows))
            inserted = 0
            updated_positions = 0

            for row in rows:
                flarm_id, takeoff_time, landing_time, flight_secs, take_lat, take_lng, land_lat, land_lng = row

                # Insert or update flight record
                cur.execute(
                    """INSERT INTO ogn_flights
                           (flarm_id, takeoff_time, landing_time, flight_secs, take_lat, take_lng, land_lat, land_lng)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                         ON DUPLICATE KEY UPDATE
                           landing_time=VALUES(landing_time),
                           flight_secs=VALUES(flight_secs),
                           take_lat=VALUES(take_lat),
                           take_lng=VALUES(take_lng),
                           land_lat=VALUES(land_lat),
                           land_lng=VALUES(land_lng)""",
                    (flarm_id, takeoff_time, landing_time, flight_secs, take_lat, take_lng, land_lat, land_lng)
                )

                # Get the flight ID (for both insert or update cases)
                cur.execute(
                    "SELECT id FROM ogn_flights WHERE flarm_id=%s AND takeoff_time=%s",
                    (flarm_id, takeoff_time)
                )
                result = cur.fetchone()
                if result:
                    flight_id = result[0]

                    # Update ogn_positions with flight_id
                    cur.execute(
                        """UPDATE ogn_positions
                           SET flight_id = %s
                           WHERE flarm_id = %s
                             AND position_time BETWEEN %s AND %s""",
                        (flight_id, flarm_id, takeoff_time, landing_time)
                    )
                    updated_positions += cur.rowcount
                    inserted += 1

            logger.info("Upserted %d flights, tagged %d positions", inserted, updated_positions)
    finally:
        conn.close()



def flight_thread():
    while True:
        try:
            extract_flights()
        except Exception as e:
            logger.error("Flight extraction failed: %s", e)
        time.sleep(FLIGHT_REFRESH)

###############################################################################
# Entrypoint
###############################################################################

def main():
    ensure_tables()
    threading.Thread(target=logger_thread, daemon=True).start()
    threading.Thread(target=flight_thread, daemon=True).start()
    logger.info("ogn_logger running â press Ctrl+C to stop")
    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()

