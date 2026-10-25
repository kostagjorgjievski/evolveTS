"""Loopback-only transport pinning output_config.effort, logging metadata only."""
import datetime,hashlib,http.server,json,threading,urllib.error,urllib.request

def set_effort(payload,provider='minimax',effort='max'):
    if effort not in ('low','medium','high','max') and not (provider=='gpt_proxy' and effort=='xhigh'):raise ValueError('Unsupported effort')
    if provider in ('kimi_proxy','luna_proxy','gpt_proxy'):payload['thinking']={'type':'adaptive'}
    if provider=='minimax' and payload.get('model','').removesuffix('[1m]')=='MiniMax-M3':
        payload['thinking']={'type':'adaptive'}
        output={k:v for k,v in payload.get('output_config',{}).items() if k!='effort'}
        if output:payload['output_config']=output
        else:payload.pop('output_config',None)
        return payload
    payload['output_config']={**payload.get('output_config',{}),'effort':effort}
    if provider=='gpt_proxy':payload['reasoning_effort']=effort
    if provider in ('glm','glm_proxy'):
        payload['thinking']={'type':'enabled'}
        payload['reasoning_effort']=effort
    return payload

def start(token,ledger,provider='minimax',upstream=None,history_audit=None,effort='max',model=None):
    if effort not in ('low','medium','high','max') and not (provider=='gpt_proxy' and effort=='xhigh'):raise ValueError('Unsupported effort')
    expected={'minimax':'https://api.minimaxi.com/anthropic','glm':'https://open.bigmodel.cn/api/anthropic','kimi_proxy':'https://yyt.s-flag.com','luna_proxy':'https://yyt.s-flag.com','gpt_proxy':'https://yyt.s-flag.com','glm_proxy':'https://yyt.s-flag.com'}
    if provider not in expected:raise ValueError('Unsupported provider')
    upstream=upstream or expected[provider]
    if upstream!=expected[provider]:raise ValueError('Unexpected provider endpoint')
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            if self.headers.get('Authorization')!='Bearer '+token and self.headers.get('x-api-key')!=token:
                self.send_error(401);return
            if self.path.split('?')[0] not in ('/v1/messages','/v1/messages/count_tokens'):
                self.send_error(404);return
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=64*2**20:self.send_error(413);return
            body=self.rfile.read(length);data=json.loads(body)
            if self.path.split('?')[0]=='/v1/messages':
                if model is not None:data['model']=model
                set_effort(data,provider,effort);body=json.dumps(data).encode()
                if history_audit is not None:
                    assistants=[]
                    for message in data.get('messages',[]):
                        if message.get('role')!='assistant':continue
                        content=message.get('content',[])
                        if not isinstance(content,list):content=[]
                        assistants.append({'types':[b.get('type') for b in content],
                            'thinking':[{'thinking_sha256':hashlib.sha256(b.get('thinking','').encode()).hexdigest(),'signature_sha256':hashlib.sha256(b.get('signature','').encode()).hexdigest()} for b in content if b.get('type')=='thinking']})
                    with history_audit.open('a') as audit:audit.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'assistants':assistants,'model':data.get('model'),'thinking_type':data.get('thinking',{}).get('type'),'max_tokens':data.get('max_tokens')})+'\n')
                with ledger.open('a') as log:log.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'provider':provider,'model':data.get('model'),'effort':data.get('output_config',{}).get('effort'),'reasoning_effort':data.get('reasoning_effort'),'thinking_type':data.get('thinking',{}).get('type'),'max_tokens':data.get('max_tokens'),'stream':data.get('stream'),'tools':[x.get('name') for x in data.get('tools',[])]})+'\n')
            headers={key:value for key,value in self.headers.items() if key.lower() not in ('host','content-length','connection','accept-encoding','transfer-encoding')}
            request=urllib.request.Request(upstream+self.path,data=body,headers=headers,method='POST')
            try:response=urllib.request.urlopen(request,timeout=600)
            except urllib.error.HTTPError as error:response=error
            except Exception:
                self.send_error(502);return
            audit_buffer=b'';audit_blocks={};audit_delta_types={}
            try:
                self.send_response(response.status)
                for key,value in response.headers.items():
                    if key.lower() in ('content-type','retry-after','request-id','x-request-id'):self.send_header(key,value)
                self.send_header('Connection','close');self.end_headers()
                while chunk:=response.read1(65536):
                    if history_audit is not None:
                        audit_buffer+=chunk
                        while b'\n' in audit_buffer:
                            line,audit_buffer=audit_buffer.split(b'\n',1)
                            if not line.startswith(b'data:'):continue
                            try:event=json.loads(line[5:].strip())
                            except (ValueError,UnicodeError):continue
                            index=event.get('index')
                            if event.get('type')=='content_block_start':
                                block=event.get('content_block',{})
                                audit_blocks[index]={'type':block.get('type'),'thinking':block.get('thinking',''),'signature':block.get('signature','')}
                            elif event.get('type')=='content_block_delta':
                                delta=event.get('delta',{});kind=delta.get('type','unknown')
                                audit_delta_types[kind]=audit_delta_types.get(kind,0)+1
                                if index in audit_blocks:
                                    if kind=='thinking_delta':audit_blocks[index]['thinking']+=delta.get('thinking','')
                                    if kind=='signature_delta':audit_blocks[index]['signature']+=delta.get('signature','')
                    self.wfile.write(chunk);self.wfile.flush()
            except (BrokenPipeError,ConnectionResetError):pass
            finally:
                if history_audit is not None:
                    blocks=[{'type':b['type'],'thinking_sha256':hashlib.sha256(b['thinking'].encode()).hexdigest(),'signature_sha256':hashlib.sha256(b['signature'].encode()).hexdigest(),'thinking_chars':len(b['thinking'])} for b in audit_blocks.values()]
                    with history_audit.open('a') as audit:audit.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'response_blocks':blocks,'delta_types':audit_delta_types,'http_status':response.status})+'\n')
                response.close();self.close_connection=True
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server,'http://127.0.0.1:'+str(server.server_port)
