import network
import socket
import time
import dht
import random
import machine
import boot
from machine import Pin, ADC

ssid, password = boot.get_wifi()

html_templates = {}
try:
    html_files_to_load = ["index.html", "Control.html"]

    for filename in html_files_to_load:
        filepath = filename[1:] if filename.startswith('/') else filename
        try:
            with open(filepath, "r") as f:
                html_templates[filename] = f.read()
                print(f" - Successfully loaded {filename}")
        except OSError as e:
            print(f" - ERROR loading {filepath}: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")

def get_content_type(filename):
    if filename.endswith(".css"):
        return "text/css"
    elif filename.endswith(".html"):
        return "text/html"
    elif filename.endswith(".png"):
        return "image/png"
    elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
        return "image/jpeg"
    elif filename.endswith(".js"):
        return "application/javascript"
    else:
        return "text/plain"

def serve_static_file(client, filepath):
    try:
        content_type = get_content_type(filepath)
        mode = "rb" if content_type.startswith("image/") else "r"
        with open(filepath, mode) as file:
            content = file.read()
        client.send(f'HTTP/1.0 200 OK\r\nContent-Type: {content_type}\r\nCache-Control: max-age=600000\r\n\r\n'.encode())
        if mode == "rb":
            client.send(content)
        else:
            client.send(content.encode())
    except Exception as e:
        print(f"Error serving file {filepath}: {e}")
        client.send(b'HTTP/1.0 404 Not Found\r\n\r\n')

def parse_query_params(path):
    params = {}
    if '?' in path:
        query_string = path.split('?', 1)[1]
        pairs = query_string.split('&')
        for pair in pairs:
            if '=' in pair:
                key, value = pair.split('=', 1)
                params[key] = value
    return params

def serve_webpage(client, path):
    filename_key = path.lstrip('/')
    if filename_key == "" or filename_key == "index.html":
        filename_key = "index.html"
    elif filename_key == "Control.html":
        filename_key = "Control.html"

    try:
        with open(filename_key, "r") as f:
            client.send(b'HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nCache-Control: no-store, no-cache, must-revalidate\r\nPragma: no-cache\r\n\r\n')
            for line in f:
                line = line.replace("{control_state}", control_state)
                line = line.replace("{ventilator_state}", ventilator_state)
                line = line.replace("{lights_state}", lights_state)
                line = line.replace("{pomp_state}", pomp_state)
                line = line.replace("{temp}", f"{temp:.1f}" if isinstance(temp, (int, float)) else str(temp))
                line = line.replace("{hum}", f"{hum:.1f}" if isinstance(hum, (int, float)) else str(hum))
                line = line.replace("{ldr}", f"{licht:.1f}" if isinstance(licht, (int, float)) else str(licht))
                line = line.replace("{bodem}", f"{bodem:.1f}" if isinstance(bodem, (int, float)) else str(bodem))
                line = line.replace("{DHT_Pin}", str(DHT_Pin))
                line = line.replace("{SMS_Pin}", str(SMS_Pin))
                line = line.replace("{LDR_Pin}", str(LDR_Pin))

                client.send(line.encode())
    except Exception as e:
        print("Failed to stream HTML file:", e)
        client.send(b'HTTP/1.0 500 Internal Server Error\r\n\r\n')

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(ssid, password)

timeout = 10
while timeout > 0:
    if wlan.isconnected() and wlan.status() >= 3:
        break
    timeout -= 1
    print(f'Waiting for Wi-Fi connection... ({timeout}s left)')
    time.sleep(1)

if not wlan.isconnected() or wlan.status() != 3:
    raise RuntimeError('Failed to establish a network connection')
else:
    print('Connection successful!')
    status = wlan.ifconfig()
    print('IP address:', status[0])

addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(addr)
s.listen(5)

print('Listening on', addr)

lights_pin = Pin(20, Pin.OUT)
pomp_pin = Pin(18, Pin.OUT)
ventilator_pin = Pin(19, Pin.OUT)

ventilator_state = "OFF"
lights_state = "OFF"
pomp_state = "OFF"
control_state = "OFF" 

lights_pin.off()
pomp_pin.off()
ventilator_pin.off()

DHT_Pin = 22
LDR_Pin = 26
SMS_Pin = 27
DHT, LDR, SMS = None, None, None
try:
    DHT = dht.DHT22(Pin(DHT_Pin))
    LDR = ADC(Pin(LDR_Pin))
    SMS = ADC(Pin(SMS_Pin))
except Exception as e:
    print(f"Error initializing sensors: {e}")


temp, hum, licht, bodem = "N/A", "N/A", "N/A", "N/A"

def LDR_State(sensor):
    if sensor is None: return "Error"
    try:
        raw_value = sensor.read_u16()
        procent_LDR = 100.0 - (raw_value / 65535.0 * 100.0)
        return max(0.0, min(100.0, procent_LDR))
    except Exception as e:
        return "Error"

def SMS_state(sensor):
    if sensor is None: return "Error"
    try:
        raw_value = sensor.read_u16()
        procent_SMS = (raw_value / 65535.0) * 100.0
        return max(0.0, min(100.0, procent_SMS))
    except Exception as e:
        return "Error"

def refresh_values():
    global temp, hum, licht, bodem
    temp, hum = DHT_State(DHT)
    licht = LDR_State(LDR)
    bodem = SMS_state(SMS)

def check_values():
    global ventilator_state, lights_state, pomp_state
    
    sensor_values = {
        'temp': temp,
        'hum': hum,
        'licht': licht,
        'bodem': bodem
    }
        
    if control_state == "ON":
        if ((temp > 30) or (hum > 40)):
            ventilator_pin.on()
            ventilator_state = "ON"
            print("ventilator ON")
        else:
            ventilator_pin.off()
            ventilator_state = "OFF"
            print("ventilator OFF")

        if licht < 40:
            lights_pin.on()
            lights_state = "ON"
            print("lights ON")
        else:
            lights_pin.off()
            lights_state = "OFF"
            print("lights OFF")

        if bodem < 70:
            pomp_pin.on()
            pomp_state = "ON"
            print("pomp ON")
        else:
            pomp_pin.off()
            pomp_state = "OFF"
            print("pomp OFF")

while True:
    conn = None 
    try:
        conn, addr = s.accept()
        print('Got a connection from', addr)

        request = conn.recv(1024).decode()
        print('Request:', request)

        request_line = request.split('\r\n')[0]
        request_parts = request_line.split(' ')

        if len(request_parts) > 1:
            full_request_path = request_parts[1] 
        else:
            full_request_path = "/" 

        query_params = parse_query_params(full_request_path)
        base_path = full_request_path.split('?', 1)[0] 

        print(f"Base path: {base_path}, Params: {query_params}")

        if base_path == "/" or base_path == "/index.html":
            serve_webpage(conn, "/index.html")
        elif base_path == "/Control.html":
            refresh_values()
            check_values()
            serve_webpage(conn, "Control.html")
        elif base_path.startswith("/static/"):
            serve_static_file(conn, base_path[1:])

        elif base_path == "/lights_state":
            print(f"lights state: {lights_state}")
            conn.send(f'HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\n\r\n{lights_state}'.encode())
        elif base_path == "/pomp_state":
            print(f"pomp state: {pomp_state}")
            conn.send(f'HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\n\r\n{pomp_state}'.encode())
        elif base_path == "/ventilator_state":
            print(f"ventilator state: {ventilator_state}")
            conn.send(f'HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\n\r\n{ventilator_state}'.encode())
        elif base_path == "/control_state": 
            print(f"Control state: {control_state}")
            conn.send(f'HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\n\r\n{control_state}'.encode())

        elif base_path == "/control":
            new_state = query_params.get("state")
            if new_state == "ON":
                control_state = "ON"
                print("Control AUTO")

            elif new_state == "OFF":
                control_state = "OFF"
                print("Control MANUAL")
            else:
                print(f"Invalid state control mode: {new_state}")
                conn.send('HTTP/1.0 400 Bad Request\r\nContent-Type: text/plain\r\n\r\nInvalid state'.encode())
                conn.close()
                continue 
            conn.send('HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nOK'.encode())

        elif base_path == "/lights":
            new_state = query_params.get("state")
            if new_state == "ON":
                lights_state = "ON"
                lights_pin.on()
                print("lights ON")
            elif new_state == "OFF":
                lights_state = "OFF"
                lights_pin.off()
                print("lights OFF")
            else:
                 print(f"Invalid lights: {new_state}")
            conn.send('HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nOK'.encode())

        elif base_path == "/pomp":
            new_state = query_params.get("state")
            if new_state == "ON":
                pomp_state = "ON"
                pomp_pin.on()
                print("pomp ON")
            elif new_state == "OFF":
                pomp_state = "OFF"
                pomp_pin.off()
                print("pomp OFF")
            else:
                 print(f"Invalid pomp: {new_state}")
            conn.send('HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nOK'.encode())

        elif base_path == "/ventilator":
            new_state = query_params.get("state")
            if new_state == "ON":
                ventilator_state = "ON"
                ventilator_pin.on()
                print("ventilator ON")
            elif new_state == "OFF":
                ventilator_state = "OFF"
                ventilator_pin.off()
                print("ventilator OFF")
            else:
                 print(f"Invalid ventilator: {new_state}")
            conn.send('HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\nOK'.encode())

        else:
            print(f"Path not found: {base_path}")
            conn.send('HTTP/1.0 404 Not Found\r\n\r\n'.encode())

        conn.close()
        print("Connection closed")
        conn = None 
    except OSError as e:
        if conn: 
            try:
                conn.close()
            except Exception:
                pass 
        print('Connection error:', e)
    except Exception as e:
        print(f"Error in main loop: {e}")
        if conn: 
            try:
                conn.send('HTTP/1.0 500 Internal Server Error\r\n\r\n'.encode())
                conn.close()
            except Exception:
                pass