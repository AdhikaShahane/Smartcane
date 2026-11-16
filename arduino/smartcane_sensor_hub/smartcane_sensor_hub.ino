/*
 * Sahayak Drishti - Arduino Uno, GROVE ULTRASONIC RANGER V2.0
 * ===========================================================
 *
 * The sensor on this build is a Seeed Grove Ultrasonic Ranger V2.0, not an
 * HC-SR04. They are NOT interchangeable:
 *
 *   HC-SR04  : 4 pins, separate TRIG and ECHO lines
 *   Grove    : 3 pins (GND, VCC, SIG), TRIGGER AND ECHO SHARE ONE WIRE
 *
 * Because the pins are marked GND / VCC / NC / SIG, the NC pin does nothing
 * and everything happens on SIG.
 *
 * ONE-WIRE PROTOCOL (this is what the Grove Ranger expects)
 *   1. Drive SIG HIGH for >= 10 us   -> this is the trigger ping
 *   2. Release SIG to INPUT
 *   3. Measure how long SIG stays HIGH -> that pulse width is the echo
 *   4. distance_cm = pulse_us / 58   (Seeed's formula: us * 0.034 / 2)
 *
 * The module needs at least 60 ms between pings or it returns junk, so this
 * sketch measures every 80 ms and streams a frame to the Pi every 50 ms,
 * reusing the last good reading in between.
 *
 * ============================================================================
 * WIRING  (4 wires on the Grove cable)
 * ============================================================================
 *   Grove wire   Board label   Arduino Uno
 *   ----------   -----------   -----------
 *   Black        GND           GND      (POWER header, pin 5 or 6)
 *   Red          VCC           5V       (POWER header, pin 4 - NOT RESET)
 *   White        NC            leave unconnected
 *   Yellow       SIG           D7       (DIGITAL header)
 *
 * D13 is the Uno's onboard LED and lights when something is within STOP_CM.
 * No wiring needed for it.
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
 *   flags bit2 = SENSOR FAULT - 1 s of unusable readings
 *
 *   crc8 is CRC-8, polynomial 0x07, over the 4 header bytes plus the payload.
 *
 * ============================================================================
 * INVALID READINGS
 * ============================================================================
 * A reading of 0 us means no echo. It is discarded rather than turned into a
 * distance: a 0 read as "close" causes constant false STOP warnings, and a 0
 * read as "far" would let the user walk into an obstacle. The median keeps
 * the last valid values.
 */

// No #include lines: only Arduino core functions are used.

// ---------------------------------------------------------------- wiring
static const uint8_t PIN_SIG = 7;     // Grove yellow wire
static const uint8_t PIN_LED = 13;    // onboard LED, no wiring

// ---------------------------------------------------------------- tuning
static const uint16_t STOP_CM        = 60;   // "close" threshold
static const uint16_t RANGER_MIN_CM  = 2;    // Grove Ranger minimum range
static const uint16_t RANGER_MAX_CM  = 350;  // Grove Ranger maximum range
static const uint32_t FRAME_PERIOD   = 50;   // ms -> 20 Hz to the Pi
static const uint32_t MEASURE_PERIOD = 80;   // ms -> Grove needs >= 60 ms
static const uint16_t FAULT_AFTER    = 13;   // ~1 s of bad readings

// ---------------------------------------------------------------- state
static uint8_t  seq = 0;
static uint16_t ring[3] = {RANGER_MAX_CM, RANGER_MAX_CM, RANGER_MAX_CM};
static uint8_t  ringIdx = 0;
static uint16_t distMedian = RANGER_MAX_CM;
static uint16_t invalidRun = 0;
static bool     close = false;
static bool     sensorFault = false;
static uint32_t lastFrame = 0;
static uint32_t lastMeasure = 0;

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

// ---------------------------------------------------------------- ranger
// Returns 0 when the reading is unusable. The caller must discard 0.
static uint16_t readDistanceCm() {
  // 1. trigger: drive SIG HIGH for 10 us
  pinMode(PIN_SIG, OUTPUT);
  digitalWrite(PIN_SIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_SIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_SIG, LOW);

  // 2. release the wire so the module can drive it
  pinMode(PIN_SIG, INPUT);

  // 3. time the echo. 30 ms covers the module's full 3.5 m range.
  unsigned long us = pulseIn(PIN_SIG, HIGH, 30000UL);
  if (us == 0) return 0;

  // 4. Seeed's conversion: cm = us * 0.034 / 2, i.e. us / 58.8
  uint16_t cm = (uint16_t)(us / 58UL);
  if (cm < RANGER_MIN_CM) return 0;
  if (cm > RANGER_MAX_CM) return 0;
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

  pinMode(PIN_SIG, INPUT);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);

  delay(300);                          // let the module settle after power-up

  // Prime the median with three real readings.
  for (uint8_t i = 0; i < 3; i++) {
    uint16_t d = readDistanceCm();
    if (d > 0) ring[i] = d;
    delay(100);
  }
  distMedian = median3();
}

// ---------------------------------------------------------------- loop
void loop() {
  uint32_t now = millis();

  // ---- measure at the rate the module tolerates -------------------------
  if (now - lastMeasure >= MEASURE_PERIOD) {
    lastMeasure = now;

    uint16_t reading = readDistanceCm();
    if (reading > 0) {
      ring[ringIdx] = reading;
      ringIdx = (ringIdx + 1) % 3;
      invalidRun = 0;
      sensorFault = false;
    } else {
      if (invalidRun < 60000) invalidRun++;
      if (invalidRun >= FAULT_AFTER) sensorFault = true;
    }
    distMedian = median3();
  }

  // ---- stream to the Pi at 20 Hz ---------------------------------------
  if (now - lastFrame >= FRAME_PERIOD) {
    lastFrame = now;

    close = (distMedian <= STOP_CM);
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
}
