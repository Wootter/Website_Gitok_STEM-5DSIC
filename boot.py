encoded_ssid = 'VFAtTElOS19GNjI4'
encoded_password = 'MzEzMDg0NTg='

import ubinascii

def get_wifi():
    ssid = ubinascii.a2b_base64(encoded_ssid).decode('utf-8')
    password = ubinascii.a2b_base64(encoded_password).decode('utf-8')
    return ssid, password