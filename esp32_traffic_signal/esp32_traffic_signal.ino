#include <WebServer.h>
#include <WiFi.h>

// ===============================
// WiFi Configuration
// ===============================
const char *WIFI_SSID = "SAKURA0188";
const char *WIFI_PASSWORD = "Sakura69";

// ===============================
// Static IP Configuration
// ===============================
// Must match iot_controller.py ESP32_IP (192.168.137.3)
// Change if your network differs.
IPAddress local_IP(192, 168, 137, 3);
IPAddress gateway(192, 168, 137, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress primaryDNS(8, 8, 8, 8);
IPAddress secondaryDNS(8, 8, 4, 4);

WebServer server(80);

// ===============================
// Helper: send JSON with CORS
// ===============================
void sendJSON(int code, const String &body) {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(code, "application/json", body);
}

// ===============================
// Traffic Light Pins
// ===============================

// NORTH
const int NR = 13;
const int NY = 12;
const int NG = 14;

// EAST
const int ER = 27;
const int EY = 26;
const int EG = 25;

// SOUTH
const int SR = 33;
const int SY = 32;
const int SG = 23;

// WEST
const int WR = 19;
const int WY = 18;
const int WG = 5;

// ===============================
// Traffic Signal State
// ===============================
String currentDirection = "NONE";
String currentPhase = "NONE"; // "NONE" | "YELLOW" | "GREEN"

unsigned long endAt = 0;
bool running = false;

// ===============================
// Helper: get GREEN pin
// ===============================
int getGreenPin(const String &direction) {
  if (direction == "NORTH")
    return NG;
  if (direction == "EAST")
    return EG;
  if (direction == "SOUTH")
    return SG;
  if (direction == "WEST")
    return WG;
  return -1;
}

// ===============================
// Set ALL signals to RED
// ===============================
void allRed() {
  // NORTH
  digitalWrite(NR, HIGH);
  digitalWrite(NY, LOW);
  digitalWrite(NG, LOW);
  // EAST
  digitalWrite(ER, HIGH);
  digitalWrite(EY, LOW);
  digitalWrite(EG, LOW);
  // SOUTH
  digitalWrite(SR, HIGH);
  digitalWrite(SY, LOW);
  digitalWrite(SG, LOW);
  // WEST
  digitalWrite(WR, HIGH);
  digitalWrite(WY, LOW);
  digitalWrite(WG, LOW);
}

// ===============================
// Turn one direction YELLOW
// All others stay RED
// ===============================
void setYellow(String direction) {
  allRed();
  if (direction == "NORTH") {
    digitalWrite(NR, LOW);
    digitalWrite(NY, HIGH);
  } else if (direction == "EAST") {
    digitalWrite(ER, LOW);
    digitalWrite(EY, HIGH);
  } else if (direction == "SOUTH") {
    digitalWrite(SR, LOW);
    digitalWrite(SY, HIGH);
  } else if (direction == "WEST") {
    digitalWrite(WR, LOW);
    digitalWrite(WY, HIGH);
  }

  currentDirection = direction;
  currentPhase = "YELLOW";
}

// ===============================
// Turn one direction GREEN
// All others stay RED
// ===============================
void setGreen(String direction) {
  allRed();
  if (direction == "NORTH") {
    digitalWrite(NR, LOW);
    digitalWrite(NG, HIGH);
  } else if (direction == "EAST") {
    digitalWrite(ER, LOW);
    digitalWrite(EG, HIGH);
  } else if (direction == "SOUTH") {
    digitalWrite(SR, LOW);
    digitalWrite(SG, HIGH);
  } else if (direction == "WEST") {
    digitalWrite(WR, LOW);
    digitalWrite(WG, HIGH);
  }

  currentDirection = direction;
  currentPhase = "GREEN";
}

// ===============================
// API: GET /yellow?direction=NORTH
// Called by Python app at start of
// yellow phase. Python manages the
// 3-second YELLOW_SECS wait.
// ===============================
void handleYellow() {
  if (!server.hasArg("direction")) {
    sendJSON(400, "{\"status\":\"ERROR\",\"message\":\"Missing direction\"}");
    return;
  }

  String direction = server.arg("direction");
  direction.toUpperCase();

  if (direction != "NORTH" && direction != "EAST" && direction != "SOUTH" &&
      direction != "WEST") {
    sendJSON(400, "{\"status\":\"ERROR\",\"message\":\"Invalid direction\"}");
    return;
  }

  setYellow(direction);
  running = false;
  endAt = 0;

  String resp = "{";
  resp += "\"status\":\"OK\",";
  resp += "\"phase\":\"YELLOW\",";
  resp += "\"direction\":\"" + direction + "\"";
  resp += "}";
  sendJSON(200, resp);
}

// ===============================
// API: GET /set?direction=NORTH&seconds=30
// Called by Python after yellow phase.
// Switches to GREEN and starts timer.
// ===============================
void setSignal() {
  if (!server.hasArg("direction") || !server.hasArg("seconds")) {
    sendJSON(
        400,
        "{\"status\":\"ERROR\",\"message\":\"Missing direction or seconds\"}");
    return;
  }

  String direction = server.arg("direction");
  String secondsStr = server.arg("seconds");
  direction.toUpperCase();
  int seconds = secondsStr.toInt();

  if (direction != "NORTH" && direction != "EAST" && direction != "SOUTH" &&
      direction != "WEST") {
    sendJSON(400, "{\"status\":\"ERROR\",\"message\":\"Invalid direction\"}");
    return;
  }
  if (seconds < 1 || seconds > 300) {
    sendJSON(400,
             "{\"status\":\"ERROR\",\"message\":\"Seconds must be 1–300\"}");
    return;
  }

  setGreen(direction);
  endAt = millis() + ((unsigned long)seconds * 1000UL);
  running = true;

  String resp = "{";
  resp += "\"status\":\"OK\",";
  resp += "\"phase\":\"GREEN\",";
  resp += "\"direction\":\"" + direction + "\",";
  resp += "\"seconds\":" + String(seconds);
  resp += "}";
  sendJSON(200, resp);
}

// ===============================
// API: GET /stop  →  all RED
// ===============================
void stopSignal() {
  allRed();
  currentDirection = "NONE";
  currentPhase = "NONE";
  running = false;
  endAt = 0;

  sendJSON(200, "{\"status\":\"STOPPED\",\"phase\":\"NONE\","
                "\"direction\":\"NONE\",\"running\":false}");
}

// ===============================
// API: GET /status  →  JSON state
// ===============================
void statusHandler() {
  unsigned long remaining = 0;

  if (running) {
    unsigned long now = millis();
    if ((long)(endAt - now) > 0) {
      remaining = (endAt - now)/ 10000UL;
    } else {
      // Green timer expired — back to all RED
      allRed();
      currentDirection = "NONE";
      currentPhase = "NONE";
      running = false;
      endAt = 0;
    }
  }

  String resp = "{";
  resp += "\"direction\":\"" + currentDirection + "\",";
  resp += "\"phase\":\"" + currentPhase + "\",";
  resp += "\"remaining\":" + String(remaining) + ",";
  resp += "\"running\":" + String(running ? "true" : "false");
  resp += "}";
  sendJSON(200, resp);
}

// ===============================
// API: GET /ping  (alias: /verify)
// Fast health check & telemetry
// ===============================
void handlePing() {
  String resp = "{";
  resp += "\"status\":\"CONNECTED\",";
  resp += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  resp += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  resp += "\"direction\":\"" + currentDirection + "\",";
  resp += "\"phase\":\"" + currentPhase + "\",";
  resp += "\"running\":" + String(running ? "true" : "false") + ",";
  resp += "\"uptime_ms\":" + String(millis());
  resp += "}";
  sendJSON(200, resp);
}

// ===============================
// Root dashboard (auto-refreshes)
// ===============================
void handleRoot() {
  String phaseColor = "#cc2222";
  String phaseBg = "#1a0000";
  if (currentPhase == "YELLOW") {
    phaseColor = "#ffcc00";
    phaseBg = "#1a1500";
  } else if (currentPhase == "GREEN") {
    phaseColor = "#00ee44";
    phaseBg = "#001a0d";
  }

  String html = "<!DOCTYPE html><html><head>";
  html += "<title>ESP32 Traffic Signal</title>";
  html += "<meta http-equiv='refresh' content='2'>";
  html += "<style>";
  html += "body{font-family:sans-serif;background:#111;color:#eee;padding:24px;"
          "margin:0;}";
  html += "h1{color:#ddd;margin-bottom:4px;}";
  html += ".sub{color:#888;font-size:.9em;margin-bottom:24px;}";
  html += ".card{background:#1e1e1e;border:1px solid "
          "#333;border-radius:10px;padding:16px 24px;margin-bottom:16px;}";
  html += ".phase{font-size:2em;font-weight:bold;color:" + phaseColor + ";";
  html += "background:" + phaseBg +
          ";border-radius:8px;padding:6px 18px;display:inline-block;}";
  html += ".api{color:#aaa;font-size:.88em;}";
  html += "li{margin:4px 0;}";
  html += "code{background:#2a2a2a;padding:2px "
          "6px;border-radius:4px;font-family:monospace;}";
  html += "</style></head><body>";
  html += "<h1>&#x1F6A6; ESP32 Traffic Signal Controller</h1>";
  html += "<p class='sub'>Page auto-refreshes every 2 seconds.</p>";
  html += "<div class='card'>";
  html += "<p>Direction: <b>" + currentDirection + "</b></p>";
  html += "<p>Phase: <span class='phase'>" + currentPhase + "</span></p>";
  html += "<p>Running: <b>" + String(running ? "YES" : "NO") + "</b></p>";
  html += "</div>";
  html += "<div class='card api'><b>API Endpoints</b><ul>";
  html += "<li><code>GET /ping</code> (or <code>/verify</code>) &mdash; Health "
          "check</li>";
  html +=
      "<li><code>GET /yellow?direction=NORTH</code> &mdash; Yellow phase</li>";
  html += "<li><code>GET /set?direction=NORTH&amp;seconds=30</code> &mdash; "
          "Green phase</li>";
  html += "<li><code>GET /stop</code> &mdash; All RED</li>";
  html += "<li><code>GET /status</code> &mdash; JSON status</li>";
  html += "</ul></div></body></html>";

  server.send(200, "text/html", html);
}

// ===============================
// Setup
// ===============================
void setup() {
  Serial.begin(115200);

  // Configure all 12 LED pins as OUTPUT
  int pins[] = {NR, NY, NG, ER, EY, EG, SR, SY, SG, WR, WY, WG};
  for (int i = 0; i < 12; i++) {
    pinMode(pins[i], OUTPUT);
  }
  allRed(); // Safe initial state

  // ── Static IP ─────────────────────────────────────────────────
  if (!WiFi.config(local_IP, gateway, subnet, primaryDNS, secondaryDNS)) {
    Serial.println("Static IP config failed — falling back to DHCP");
  } else {
    Serial.println("Static IP configured: 192.168.137.3");
  }

  // ── Connect to WiFi ───────────────────────────────────────────
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.println("WiFi connected!");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());

  // ── Register API routes ────────────────────────────────────────
  server.on("/", HTTP_GET, handleRoot);
  server.on("/ping", HTTP_GET, handlePing);
  server.on("/verify", HTTP_GET, handlePing); // alias
  server.on("/yellow", HTTP_GET, handleYellow);
  server.on("/set", HTTP_GET, setSignal);
  server.on("/stop", HTTP_GET, stopSignal);
  server.on("/status", HTTP_GET, statusHandler);

  server.begin();
  Serial.println("HTTP server started — ready for Python app.py");
}

// ===============================
// Main Loop
// ===============================
void loop() {
  server.handleClient();

  // ── Green phase auto-expiry ────────────────────────────────────
  if (running && currentPhase == "GREEN") {
    if ((long)(endAt - millis()) <= 0) {
      allRed();
      currentDirection = "NONE";
      currentPhase = "NONE";
      running = false;
      endAt = 0;
      Serial.println("GREEN timer expired — ALL RED");
    }
  }
}