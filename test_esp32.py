"""Comprehensive ESP32 diagnostic script.

Tests:
  1. Reachability (GET /)
  2. Yellow phase (/yellow?direction=NORTH)
  3. Green phase  (/set?direction=NORTH&seconds=5)
  4. Status poll  (/status) x5
  5. Stop         (/stop)
"""
import time
import iot_controller

SEP = '-' * 55

def _ok(label, result):
    icon = '✅' if result else '❌'
    print(f'  {icon}  {label}: {"OK" if result else "FAILED"}')
    return result

def run_diagnostics():
    print(SEP)
    print('  ESP32 Traffic Signal — Diagnostic Test')
    print(f'  Target IP : {iot_controller.get_esp32_ip()}')
    print(SEP)

    # 1. Reachability
    print('\n[1] Checking reachability...')
    reachable = iot_controller.check_connection(timeout=3.0)
    _ok('ESP32 root page responds', reachable)
    if not reachable:
        print()
        print('  ⚠  Could not reach the ESP32. Troubleshooting tips:')
        print('     • Is the ESP32 powered on and connected to Wi-Fi?')
        print('     • Are laptop and ESP32 on the SAME network/SSID?')
        print('     • Open Serial Monitor at 115200 baud and check the IP.')
        print(f'     • Edit iot_controller.py or use the GUI toolbar to set the correct IP.')
        print(f'     • Current IP: {iot_controller.get_esp32_ip()}')
        print()
        return

    # 2. Yellow phase
    print('\n[2] Sending YELLOW for NORTH...')
    _ok('send_yellow(NORTH)', iot_controller.send_yellow('NORTH'))
    time.sleep(1)

    # 3. Green phase
    print('\n[3] Sending GREEN for NORTH (5 seconds)...')
    _ok('send_signal(NORTH, 5)', iot_controller.send_signal('NORTH', 5))

    # 4. Status poll
    print('\n[4] Polling /status every second (5×)...')
    all_ok = True
    for i in range(5):
        st = iot_controller.get_status()
        ok = isinstance(st, dict) and 'direction' in st
        _ok(f'Status poll {i+1}: {st}', ok)
        all_ok = all_ok and ok
        time.sleep(1)

    # 5. Stop
    print('\n[5] Sending STOP...')
    _ok('stop_signal()', iot_controller.stop_signal())

    print()
    print(SEP)
    if all_ok:
        print('  🎉  All tests PASSED. ESP32 is ready!')
    else:
        print('  ⚠   Some tests FAILED. Check Serial Monitor for errors.')
    print(SEP)
    print()

if __name__ == '__main__':
    run_diagnostics()
