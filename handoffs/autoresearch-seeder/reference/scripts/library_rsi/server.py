"""Library test MCP: scoped advisor plus existing sandbox/retrieval tools."""
import asyncio,importlib.util,json,signal,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/library_rsi'))
import advisor
spec=importlib.util.spec_from_file_location('acceptance_tools',ROOT/'scripts/literature_acceptance/server.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
original_call=base.call
base.SCHEMAS.pop('ask_researcher');base.DESCRIPTIONS.pop('ask_researcher')
base.SCHEMAS['ask_advisor']={'type':'object','properties':{'question':{'type':'string','maxLength':12000}},'required':['question'],'additionalProperties':False}
base.DESCRIPTIONS['ask_advisor']='Ask the GPT literature advisor whether to continue, pivot or explore. Include your current approach, bottleneck and failures. Returns scoped advice, sources and cheapest tests, or pending research with immediate library retrieval. Repeating a question retrieves its answer. Advice is optional; verify claims.'

async def call(context,params):
    if params.name!='ask_advisor':return await original_call(context,params)
    try:
        if set(params.arguments or {})!={'question'}:raise ValueError('Exactly question is required')
        result=await advisor.ask(RUN,BRANCH,params.arguments['question'])
        with (base.CACHE/'advisor-ledger.jsonl').open('a') as log:log.write(json.dumps(result)+'\n')
        return base.types.CallToolResult(content=[base.types.TextContent(text=json.dumps(result))],structuredContent=result)
    except Exception as e:return base.types.CallToolResult(isError=True,content=[base.types.TextContent(text=str(e))])

if __name__=='__main__':
    attempt=Path(sys.argv[1]).absolute();RUN=attempt.parents[2];BRANCH=attempt.parent.name
    base.configure(attempt);base.call=call
    def stop(sig,frame):base.stop_children();raise SystemExit(128+sig)
    signal.signal(signal.SIGTERM,stop)
    try:asyncio.run(base.main())
    finally:base.stop_children()
