"""Authenticated local relay; task execution remains in its own sandbox."""
import os,secrets,signal,socket,subprocess,sys,threading

class MCPRelay:
    def __init__(self,command,stderr):
        self.command=command;self.stderr=stderr;self.secret=secrets.token_hex(32);self.processes=[];self.closed=False
        self.listener=socket.socket();self.listener.bind(('127.0.0.1',0));self.listener.listen(4);self.listener.settimeout(1);self.port=self.listener.getsockname()[1]
        threading.Thread(target=self._accept,daemon=True).start()
    def _accept(self):
        while not self.closed:
            try:conn,_=self.listener.accept()
            except socket.timeout:continue
            except OSError:return
            threading.Thread(target=self._connection,args=(conn,),daemon=True).start()
    def _connection(self,conn):
        process=None
        try:
            conn.settimeout(15);auth=b''
            while not auth.endswith(b'\n') and len(auth)<128:
                data=conn.recv(1)
                if not data:return
                auth+=data
            if auth.strip()!=self.secret.encode():return
            conn.settimeout(None)
            process=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,bufsize=0,start_new_session=True)
            self.processes.append(process)
            def outputs():
                try:
                    while True:
                        data=process.stdout.read(65536)
                        if not data:break
                        conn.sendall(data)
                except OSError:pass
                finally:
                    try:conn.shutdown(socket.SHUT_WR)
                    except OSError:pass
            threading.Thread(target=outputs,daemon=True).start()
            while True:
                data=conn.recv(65536)
                if not data:break
                process.stdin.write(data);process.stdin.flush()
        except (OSError,ValueError):pass
        finally:
            conn.close()
            if process is not None:self._stop(process)
    @staticmethod
    def _stop(process):
        if process.poll() is not None:return
        try:os.killpg(process.pid,signal.SIGTERM);process.wait(5)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        except ProcessLookupError:pass
    def close(self):
        self.closed=True;self.listener.close()
        for process in self.processes:self._stop(process)

def client(port):
    sock=socket.create_connection(('127.0.0.1',int(port)),timeout=30);sock.settimeout(None)
    sock.sendall(os.environ['CHEMISTRY_MCP_BRIDGE_SECRET'].encode()+b'\n')
    def receive():
        while True:
            data=sock.recv(65536)
            if not data:break
            os.write(1,data)
        os._exit(0)
    threading.Thread(target=receive,daemon=True).start()
    while True:
        data=os.read(0,65536)
        if not data:break
        sock.sendall(data)
    sock.shutdown(socket.SHUT_WR)
if __name__=='__main__':client(sys.argv[1])
