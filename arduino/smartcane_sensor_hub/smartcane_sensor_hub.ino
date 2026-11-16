/*
 * Sahayak Drishti - Arduino Uno, ULTRASONIC ONLY
 * ==============================================
 *
 * The Arduino is a SENSOR here, nothing else. One HC-SR04, no GPS, no MPU6050,
 * no motor, no external libraries. Everything used is built into the Arduino
 * IDE, so this compiles on a fresh install with nothing to download.
 *
 * WHAT IT DOES
 *   1. Pings the HC-SR04 20 times a second.
 *   2. Keeps the median of the last 3 valid readings, which rejects the single
 *      bad echo that otherwise causes spurious "stop" warnings.
 *   3. Blinks the Uno's own onboard LED (D13) when something is within STOP_CM.
 *      That needs no wiring and is useful for testing: wave your hand, watch
 *      the LED.
 *   4. Streams the distance to the Raspberry Pi over serial at 20 Hz.
 *
 * ============================================================================
 * WIRING  (4 wires, nothing else)
 * ============================================================================
 *   HC-SR04  VCC  -> 5V
 *            GND  -> GND
 *            TRIG -> D7
 *            ECHO -> D8
 *
 *   D13 is the Uno's onboard LED - already on the board, leave it alone.
 *   No other pins are used.
 *
 * ============================================================================
 * SERIAL PROTOCOL  115200 baud, binary, little-endian
 * ============================================================================
 *   frame: 0xAA 0x55 | type | len | payload... | crc8(body)
 *
 *   type 0x01 FAST @ 20 Hz :  seq:u8 | dist_cm:u16 | flags:u8    (4 bytes)
 *
 *   flags bit0 = obstacle closer than STOP_CM
 *   flags bit1 = reserved, always 0
 *   flags bit2 = SENSOR FAULT - 2 s of unusable readings, meaning the
 *                ultrasonic is unplugged, miswired, or getting no echo
 *
 *   crc8 is CRC-8, polynomial 0x07, computed over the 4 header bytes plus the
 *   payload, i.e. everything before the CRC byte.
 *
 * ============================================================================
 * WHY INVALID READINGS ARE THROWN AWAY
 * ============================================================================
 * The HC-SR04 returns nothing when there is no echo, and it sometimes hears
 * its own ping (a reading under 2 cm). Neither is a real distance:
 *   - treating 0 as "close" causes constant false STOP warnings
 *   - treating 0 as "far" would let a user walk into an obstacle
 * So invalid readings are discarded and the median keeps the last valid
 * values. After 2 seconds of nothing but invalid readings the fault flag is
 * set, so the Pi can say "sensor not responding" instead of quietly claiming
 * the path is clear.
 */

// No #include lines at all: this sketch uses only what the Arduino core
// already provides (Serial, pinMode, pulseIn, millis). Nothing to install.

// ---------------------------------------------------------------- wiring
static const uint8_t PIN_TRIG = 7;    // HC-SR04 TRIG
static const uint8_t PIN_ECHO = 8;    // HC-SR04 ECHO
static const uint8_t PIN_LED  = 13;   // onboard LED, no wiring needed

// ---------------------------------------------------------------- tuning
static const uint16_t STOP_CM       = 60;   // "close" threshold
static const uint16_t SENSOR_MAX_CM = 400;  // HC-SR04 usable range
static const uint32_t FAST_PERIOD   = 50;   // ms -> 20 Hz
static const uint16_t FAULT_AFTER   = 40;   // invalid readings before fault (2 s)

// ---------------------------------------------------------------- state
static uint8_t  seq = 0;
static uint16_t ring[3] = {SENSOR_MAX_CM, SENSOR_MAX_CM, SENSOR_MAX_CM};
static uint8_t  ringIdx = 0;
static uint16_t distMedian = SENSOR_MAX_CM;
static uint16_t invalidRun = 0;
static bool     close = false;
static bool     sensorFault = false;
static uint32_t lastFast = 0;

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
  uint8_t body[2 + 1 + 1 + 8];
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
// Returns 0 when the reading is unusable. The caller must discard 0.
static uint16_t readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(3);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  // 25 ms timeout covers ~4.3 m. Never call pulseIn() without a timeout:
  // the default is 1 second and would stall the entire 20 Hz loop.
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 25000UL);
  if (us == 0) return 0;                    // no echo at all

  uint16_t cm = (uint16_t)(us / 58UL);
  if (cm < 2) return 0;                     // crosstalk from its own ping
  if (cm > SENSOR_MAX_CM) return 0;         // out of usable range
  return cm;
}

static uint16_t median3() {
  uint16_t a = ring[0], b = ring[1], c = ring[2];
  if (a > b) { uint16_t t = a; a = b; b = t; }
  if (b > c) { uint16_t t = b; b = c; c = t; }
  if (a > b) { uint16_t t = a; a = b; b = t; }
  return b;
}

// ---------------------------------------------------------------- setup
void setup() {
  Serial.begin(115200);

  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_LED, OUTPUT);

  digitalWrite(PIN_TRIG, LOW);
  digitalWrite(PIN_LED, LOW);

  // Prime the median with three real readings so the first frame sent to the
  // Pi is already filtered. If the sensor is silent these are all invalid and
  // the ring keeps its safe "far" default.
  for (uint8_t i = 0; i < 3; i++) {
    uint16_t d = readDistanceCm();
    if (d > 0) ring[i] = d;
    delay(30);
  }
  distMedian = median3();
}

// ---------------------------------------------------------------- loop
void loop() {
  uint32_t now = millis();
  if (now - lastFast < FAST_PERIOD) return;
  lastFast = now;

  uint16_t reading = readDistanceCm();

  if (reading > 0) {
    ring[ringIdx] = reading;
    ringIdx = (ringIdx + 1) % 3;
    invalidRun = 0;
    sensorFault = false;
  } else {
    if (invalidRun < FAULT_AFTER) invalidRun++;
    if (invalidRun >= FAULT_AFTER) sensorFault = true;
  }

  distMedian = median3();
  close = (distMedian <= STOP_CM);

  // Visual feedback only - the onboard LED needs no wiring.
  digitalWrite(PIN_LED, close ? HIGH : LOW);

  uint8_t flags = 0;
  if (close)       flags |= 0x01;
  if (sensorFault) flags |= 0x04;

  uint8_t payload[4];
  payload[0] = seq++;
  payload[1] = (uint8_t)(distMedian & 0xFF);
  payload[2] = (uint8_t)(distMedian >> 8);
  payload[3] = flags;
  sendFrame(0x01, payload, 4);
}
