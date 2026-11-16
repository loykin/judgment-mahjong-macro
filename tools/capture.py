import socket, time, sys, os
out = sys.argv[1]; dur = float(sys.argv[2])
s = socket.create_connection(('127.0.0.1', 8650)); r = s.makefile('rb')
def call(m):
    s.sendall((m + '\n').encode()); return r.readline()
def thumb():
    s.sendall(b'{"thumb":[]}\n'); h = r.readline().split(); return r.read(int(h[3]))
def diff(a, b):
    n = len(a) // 3; ch = sum(1 for i in range(n) if max(abs(a[3*i+c]-b[3*i+c]) for c in range(3)) > 40)
    return ch * 100 / n
prev = None; k = len([f for f in os.listdir(out) if f.endswith('.png')]); t0 = time.time()
while time.time() - t0 < dur:
    t = thumb()
    if prev is None or diff(prev, t) > 1.0:
        k += 1; call('{"snap":"%s/%03d.png"}' % (out, k)); prev = t
        print(k, round(time.time() - t0, 1), flush=True)
    time.sleep(0.7)
