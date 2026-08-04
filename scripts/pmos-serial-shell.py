import serial, sys, time
cmd = sys.argv[1]; wait = float(sys.argv[2]) if len(sys.argv)>2 else 4
s = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
s.write(b'\n'); time.sleep(0.4); s.reset_input_buffer()
s.write(cmd.encode()+b'\n')
t0=time.time(); out=b''
while time.time()-t0 < wait:
    d = s.read(4096)
    if d: out += d
print(out.decode(errors='replace'))
s.close()
