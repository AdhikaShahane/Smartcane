/*
 * Sahayak Drishti - Arduino Uno sensor hub
 * ========================================
 *
 * The Uno does the timing-critical work the Pi is bad at, and it owns one job
 * the Pi must never be allowed to break: the hardware reflex.
 *
 *   HC-SR04  ->  median filter  ->  if closer than STOP_CM
 *                                     -> vibration motor ON (digital pin)
 *                                     -> also reported over serial
 *
 * That reflex path is ~5 ms and completely independent of the Pi. If the Pi
 * hangs, the camera crashes or the recogniser deadlocks, the motor still buzzes.
 *
 * SERIAL PROTOCOL  (115200 baud, binary, little-endian)
 *   frame: 0xAA 0x55 | type | len | payload... | crc8(body)
 *
 *   type 0x01 FAST @ 20 Hz : seq:u8, dist_cm:u16, dist_raw_cm:u16, flags:u8
 *   type 0x02 SLOW @ 1 Hz  : fix:u8, sats:u8, lat:i32 (x1e7), lon:i32 (x1e7)
 *
 *   flags bit0 = reflex asserted (something inside STOP_CM)
 *
 * WIRING (change the pin defines below to match your build)
 *   HC-SR04  TRIG -> D7    ECHO -> D8
 *   MPU6050  SDA  -> A4    SCL  -> A5
 *   GPS NEO-6M RX -> D3 (SoftwareSerial RX)   TX -> D2 (SoftwareSerial TX)
 *   Motor    gate -> D9    (use a transistor + flyback diode, never direct)
 *   LED      -> D13
 *
 * NOTE: the GPS module's TX must go to the Arduino's SoftwareSerial RX pin
 * (D3 here). If you only have one wire, wire GPS TX -> D3 and leave D2 free.
 */

#include <Wire.h>
#include <SoftwareSerial.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>

// ---------------------------------------------------------------- config
static const uint8_t  PIN_TRIG      = 7;
static const uint8_t  PIN_ECHO      = 8;
static const uint8_t  PIN_MOTOR     = 9;
static const uint8_t  PIN_LED       = 13;

static const uint8_t  PIN_GPS_RX    = 3;   // Arduino RX  <- GPS TX
static const uint8_t  PIN_GPS_TX    = 2;   // Arduino TX  -> GPS RX (often unused)

static const uint16_t STOP_CM       = 60;   // hardware reflex threshold
static const uint16_t SENSOR_MAX_CM = 400;
static const uint32_t FAST_PERIOD   = 50;   // ms -> 20 Hz
static const uint32_t SLOW_PERIOD   = 1000; // ms -> 1 Hz
static const uint8_t  MPU_ADDR      = 0x68;

// ---------------------------------------------------------------- state
SoftwareSerial gps(PIN_GPS_RX, PIN_GPS_TX);

static uint8_t  seq = 0;
static uint16_t ring[3] = {0, 0, 0};
static uint8_t  ringIdx = 0;
static uint16_t distMedian = 0;
static uint16_t distRaw = 0;
static bool     reflex = false;

static bool     mpuPresent = false;
static float    accelMax = 0.0f;
static float    accelMin = 0.0f;
static uint32_t lastFast = 0;
static uint32_t lastSlow = 0;
static uint32_t lastMpu = 0;

// GPS
static bool     gpsFix = false;
static uint8_t  gpsSats = 0;
static int32_t  gpsLat = 0;
static int32_t  gpsLon = 0;
static char     gpsLine[96];
static uint8_t  gpsLen = 0;

// ---------------------------------------------------------------- crc8
static uint8_t crc8(const uint8_t *data, uint8_t len) {
  uint8_t crc = 0;
  for (uint8_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (uint8_t b = 0; b < 8; b++) {
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
    }
  }
  return crc;
}

static void sendFrame(uint8_t type, const uint8_t *payload, uint8_t len) {
  uint8_t body[2 + 1 + 1 + 32];
  uint8_t n = 0;
  body[n++] = 0xAA;
  body[n++] = 0x55;
  body[n++] = type;
  body[n++] = len;
  for (uint8_t i = 0; i < len && n < sizeof(body); i++) body[n++] = payload[i];
  Serial.write(body, n);
  Serial.write(crc8(body, n));
}

// ---------------------------------------------------------------- ultrasonic
static uint16_t readDistanceCm() {
  // 25 ms timeout covers ~4.3 m. Never use pulseIn() without a timeout: the
  // default is 1 second, which would stall the whole 20 Hz loop.
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(3);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  unsigned long us = pulseIn(PIN_ECHO, HIGH, 25000UL);
  if (us == 0) return SENSOR_MAX_CM;
  uint16_t cm = (uint16_t)(us / 58UL);
  if (cm < 2)   return SENSOR_MAX_CM;         // crosstalk / too close
  if (cm > SENSOR_MAX_CM) return SENSOR_MAX_CM;
  return cm;
}

static uint16_t median3() {
  uint16_t a = ring[0], b = ring[1], c = ring[2];
  if (a > b) { uint16_t t = a; a = b; b = t; }
  if (b > c) { uint16_t t = b; b = c; c = t; }
  if (a > b) { uint16_t t = a; a = b; b = t; }
  return b;
}

// ---------------------------------------------------------------- MPU6050
static void mpuInit() {
  Wire.begin();
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);        // PWR_MGMT_1
  Wire.write(0x00);        // wake
  mpuPresent = (Wire.endTransmission() == 0);
  if (mpuPresent) {
    Wire.beginTransmission(MPU_ADDR);
    Wire.write(0x1C);      // ACCEL_CONFIG
    Wire.write(0x00);      // +-2g
    Wire.endTransmission();
  }
}

static void mpuUpdate() {
  if (!mpuPresent) return;
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) { mpuPresent = false; return; }
  if (Wire.requestFrom((uint8_t)MPU_ADDR, (uint8_t)6) != 6) return;

  int16_t ax = (Wire.read() << 8) | Wire.read();
  int16_t ay = (Wire.read() << 8) | Wire.read();
  int16_t az = (Wire.read() << 8) | Wire.read();

  float gx = ax / 16384.0f * 9.81f;
  float gy = ay / 16384.0f * 9.81f;
  float gz = az / 16384.0f * 9.81f;
  float mag = sqrt(gx * gx + gy * gy + gz * gz);

  if (mag > accelMax) accelMax = mag;
  if (mag < accelMin || accelMin == 0.0f) accelMin = mag;
}

// ---------------------------------------------------------------- GPS
static int32_t nmeaToE7(const char *field, char hemi) {
  // ddmm.mmmm or dddmm.mmmm -> degrees * 1e7
  if (!field || !*field) return 0;
  double v = atof(field);
  int deg = (int)(v / 100.0);
  double min = v - deg * 100.0;
  double dec = deg + min / 60.0;
  if (hemi == 'S' || hemi == 'W') dec = -dec;
  return (int32_t)(dec * 1e7);
}

static void gpsParseLine(char *line) {
  if (strncmp(line, "$GPRMC", 6) != 0 && strncmp(line, "$GNRMC", 6) != 0) return;
  // $GPRMC,hhmmss,A,lat,N,lon,E,...
  char *fields[12];
  uint8_t n = 0;
  char *p = line;
  fields[n++] = p;
  while (*p && n < 12) {
    if (*p == ',') { *p = '\0'; fields[n++] = p + 1; }
    p++;
  }
  if (n < 7) return;
  gpsFix = (fields[2][0] == 'A');
  if (!gpsFix) return;
  gpsLat = nmeaToE7(fields[3], fields[4][0]);
  gpsLon = nmeaToE7(fields[5], fields[6][0]);
}

static void gpsPoll() {
  while (gps.available()) {
    char c = (char)gps.read();
    if (c == '\n' || c == '\r') {
      if (gpsLen > 6) { gpsLine[gpsLen] = '\0'; gpsParseLine(gpsLine); }
      gpsLen = 0;
    } else if (gpsLen < sizeof(gpsLine) - 1) {
      gpsLine[gpsLen++] = c;
    }
  }
}

// ---------------------------------------------------------------- setup
void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_MOTOR, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  digitalWrite(PIN_MOTOR, LOW);

  gps.begin(9600);
  mpuInit();

  // prime the median filter so the first frame is already sane
  for (uint8_t i = 0; i < 3; i++) { ring[i] = readDistanceCm(); delay(30); }
  distMedian = median3();
}

// ---------------------------------------------------------------- loop
void loop() {
  uint32_t now = millis();
  gpsPoll();
  mpuUpdate();

  if (now - lastFast >= FAST_PERIOD) {
    lastFast = now;

    distRaw = readDistanceCm();
    ring[ringIdx] = distRaw;
    ringIdx = (ringIdx + 1) % 3;
    distMedian = median3();

    // ---- hardware reflex: independent of the Pi -------------------------
    reflex = (distMedian <= STOP_CM);
    digitalWrite(PIN_MOTOR, reflex ? HIGH : LOW);
    digitalWrite(PIN_LED, reflex ? HIGH : LOW);

    // FAST payload is 4 bytes: seq:u8, dist_cm:u16, flags:u8
    uint8_t payload[4];
    payload[0] = seq++;
    payload[1] = (uint8_t)(distMedian & 0xFF);
    payload[2] = (uint8_t)(distMedian >> 8);
    payload[3] = (uint8_t)(reflex ? 0x01 : 0x00);
    sendFrame(0x01, payload, 4);
  }

  if (now - lastSlow >= SLOW_PERIOD) {
    lastSlow = now;
    uint8_t payload[10];
    payload[0] = gpsFix ? 1 : 0;
    payload[1] = gpsSats;
    memcpy(&payload[2], &gpsLat, 4);
    memcpy(&payload[6], &gpsLon, 4);
    sendFrame(0x02, payload, 10);
  }
}
