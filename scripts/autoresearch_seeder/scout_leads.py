"""Short unverified leads; reproduction and official gates remain separate."""
import math
TASKS=('dfthcsos','dqi','invsqrt')
SCORE={'anyOf':[{'type':'null'},{'type':'object','properties':{'value':{'type':'number','exclusiveMinimum':0},'source_url':{'type':'string'},'basis':{'type':'string','enum':['baseline_improvement_ratio','portfolio_score','official_cost','unknown']}},'required':['value','source_url','basis'],'additionalProperties':False}]}
SCHEMA={'type':'object','properties':{'distinct_approach':{'type':'boolean'},'distinct_reason':{'type':'string','maxLength':1000},'source_url':{'type':'string'},'version':{'type':'string'},'summary':{'type':'string','maxLength':1500},'code_urls':{'type':'array','items':{'type':'string'}},'overall_score':SCORE,'benchmark_scores':{'type':'object','properties':{t:SCORE for t in TASKS},'required':list(TASKS),'additionalProperties':False}},'required':['source_url','version','summary','code_urls','overall_score','benchmark_scores'],'additionalProperties':False}
GUIDE='''ROLE: SCOUT, SHORT LEADS ONLY. Find original public sources and report a short lead with record_scout_lead, then finish immediately. No hypothesis, quotes, packet, method verification, compatibility tests or implementation required. Report the overall claimed portfolio score AND each benchmark claimed score from the source, with source URLs and score basis. Use null when not published; never derive or invent missing benchmark scores from the overall score. Use baseline_improvement_ratio only when the source explicitly reports the task improvement over its baseline; raw official costs are official_cost and are not comparable to ratios. Provide code/download links, source version (unknown if absent), and a few sentences explaining the lead. For lower-scoring leads optionally set distinct_approach and a short source-backed distinct_reason; do not mark every lead distinct. Existing fetch receipts are enough; do not polish or broaden a ready lead. Reproducer owns interpretation, dependencies and all scientific testing. Every reported score remains UNVERIFIED.'''

def record(store,args):
 from .models import utc,atomic_write
 from urllib.parse import urlparse
 def url(u):
  if urlparse(u).scheme!='https' or not urlparse(u).netloc:raise ValueError('Public HTTPS source URL required')
 url(args['source_url'])
 source=store.get_source(args['source_url'])
 if not source or source.get('status')!='accessed' or not source.get('content_sha256'):raise ValueError('Fetch the primary source first; no quotation or method audit required')
 for u in args['code_urls']:url(u)
 for score in [args['overall_score'],*args['benchmark_scores'].values()]:
  if score is not None:
   if isinstance(score['value'],bool) or not math.isfinite(score['value']) or score['value']<=0:raise ValueError('Finite positive reported score required')
   url(score['source_url'])
   receipt=store.get_source(score['source_url'])
   if not receipt or receipt.get('status')!='accessed' or not receipt.get('content_sha256'):raise ValueError('Fetch each reported score source or use null; no invented scores')
 lead={**args,'reported_only':True,'verification':'unverified_source_claim','created_utc':utc(),'source_sha256':source['content_sha256']}
 store.event('scout_lead',{'lead':lead});return {'recorded':True,'reproduction_eligible':True,'certified':False,'next_action':'Finish; reproducer performs source review and full verification'}

def task_score(scheduling,task=None):
 s=scheduling.get('benchmark_scores',{}).get(task or scheduling.get('task'))
 if isinstance(s,dict) and s.get('basis')=='baseline_improvement_ratio':
  v=s.get('value')
  if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0:return v
 return None
