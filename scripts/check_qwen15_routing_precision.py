"""Small paired prompt/dtype control; no production representativeness claim."""
import argparse,hashlib,json,time
from pathlib import Path
from scripts.capture_qwen15_routes import MODEL,REVISION
PROMPTS={
 'topic_short':['Explain linear algebra with a concrete example.','Explain gardening with a concrete example.','Explain ocean tides with a concrete example.','Explain music theory with a concrete example.'],
 'code_math':['Write a Python function for binary search and explain its invariants.','Solve 3*x + 7 = 31 and verify the answer step by step.','Explain how a hash table resolves collisions using a worked example.','Prove why the sum of the first n odd numbers is n squared.']}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--cache',required=True);ap.add_argument('--steps',type=int,default=8);a=ap.parse_args()
 import torch
 from transformers import AutoTokenizer,AutoModelForCausalLM
 from huggingface_hub import snapshot_download
 torch.set_num_threads(4);torch.set_num_interop_threads(1)
 out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
 root=Path(snapshot_download(MODEL,revision=REVISION,cache_dir=a.cache,local_files_only=True));tok=AutoTokenizer.from_pretrained(root);tok.padding_side='left'
 model=AutoModelForCausalLM.from_pretrained(root,torch_dtype=torch.float32,low_cpu_mem_usage=True,attn_implementation='eager').eval();records=[];teacher={}
 with torch.inference_mode():
  for dtype in ('FP32','BF16'):
   if dtype=='BF16':model.to(torch.bfloat16)
   for family,texts in PROMPTS.items():
    inp=tok(texts,return_tensors='pt',padding='max_length',truncation=True,max_length=128)
    z=model.model(**inp,output_router_logits=False,use_cache=True);past=z.past_key_values;mask=inp['attention_mask'];token=model.lm_head(z.last_hidden_state[:,-1:]).argmax(-1);del z
    routes=[[] for _ in range(24)];prob=[[] for _ in range(24)];generated=[];inputs=[];started=time.time()
    for step in range(a.steps):
     if dtype=='BF16':token=torch.tensor(teacher[family][step],dtype=torch.long).reshape(4,1)
     inputs.append(token.flatten().tolist());mask=torch.cat((mask,torch.ones((4,1),dtype=mask.dtype)),1)
     z=model.model(input_ids=token,attention_mask=mask,past_key_values=past,output_router_logits=True,use_cache=True)
     for l,logits in enumerate(z.router_logits):
      scores,ids=logits.float().softmax(-1).topk(4,-1);routes[l].extend(ids.tolist());prob[l].extend((scores/scores.sum(-1,keepdim=True)).tolist())
     past=z.past_key_values;token=model.lm_head(z.last_hidden_state[:,-1:]).argmax(-1);generated.append(token.flatten().tolist());del z
     print(dtype,family,step+1,flush=True)
    if dtype=='FP32':teacher[family]=inputs
    record=dict(schema=1,model=MODEL,checkpoint_revision=REVISION,model_matched_capture=True,execution_dtype=dtype,architecture_dtype='BF16',capture_context=128,steps=a.steps,max_batch=4,layers=24,experts=60,topk=4,routes=routes,route_probabilities=prob,generated_token_ids=generated,input_token_ids=inputs,source='Public short prompts; paired FP32/BF16 teacher-forced input IDs',prompt_family=family,prompts=texts,prompt_sha256=hashlib.sha256(json.dumps(texts).encode()).hexdigest(),elapsed_cpu_s=time.time()-started,limitations=['Eight-step four-prompt control, not a production workload','BF16 sees FP32 generated IDs; test isolates dtype given identical inputs','Not the same context/prompt distribution as primary512-token capture'])
    path=out/f'{family}-{dtype}.json';path.write_text(json.dumps(record,separators=(',',':')));records.append(record)
 paired=[]
 for family in PROMPTS:
  fp=next(r for r in records if r['prompt_family']==family and r['execution_dtype']=='FP32');bf=next(r for r in records if r['prompt_family']==family and r['execution_dtype']=='BF16')
  choices=[(x,y) for l in range(24) for x,y in zip(fp['routes'][l],bf['routes'][l])]
  paired.append(dict(family=family,route_records=len(choices),ordered_top4_equal=sum(x==y for x,y in choices)/len(choices),top4_set_equal=sum(set(x)==set(y) for x,y in choices)/len(choices),mean_top4_overlap=sum(len(set(x)&set(y))/4 for x,y in choices)/len(choices),same_inputs=fp['input_token_ids']==bf['input_token_ids'],generated_argmax_equal=sum(x==y for rows in zip(fp['generated_token_ids'],bf['generated_token_ids']) for x,y in zip(*rows))/(a.steps*4)))
 (out/'precision-summary.json').write_text(json.dumps(dict(model=MODEL,revision=REVISION,records=paired,scope='Small paired control, not universal BF16 routing identity'),indent=2))
if __name__=='__main__':main()
