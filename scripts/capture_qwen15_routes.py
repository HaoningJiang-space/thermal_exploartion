"""Capture public, model-matched routing; CPU speed is NOT an accelerator result.

Pinned checkpoint and FP32 execution deliberately remain separate from the
BF16 structural architecture contract. No private prompts or weights exported.
"""
import argparse, hashlib, json, os, time
from pathlib import Path
REVISION='1a758c50ecb6350748b9ce0a99d2352fd9fc11c9'
MODEL='Qwen/Qwen1.5-MoE-A2.7B'
TOPICS=('linear algebra','gardening','astronomy','public libraries','bread baking','geometry','sorting algorithms','weather observations','ocean tides','music theory','probability','bicycle maintenance','botany','number theory','bridge construction','solar energy','language learning','database indexing','bird migration','chess','archaeology','photography','water treatment','volcanoes','public transportation','classical mechanics','computer networks','beekeeping','cartography','recycling','statistics','optics')
def prompts(training=False):
    return [(('Explain '+topic+' to a student. Give concrete examples and reasons. ')*(96 if not training else 80)) for topic in (('ceramic glazing','electrical motors','Roman history','fruit preservation') if training else TOPICS)]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--cache',required=True);ap.add_argument('--threads',type=int,default=8);ap.add_argument('--steps',type=int,default=128);ap.add_argument('--context',type=int,default=512);a=ap.parse_args()
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer,AutoModelForCausalLM
    torch.set_num_threads(a.threads);torch.set_num_interop_threads(1)
    out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    root=Path(snapshot_download(MODEL,revision=REVISION,cache_dir=a.cache,max_workers=4))
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file() and p.suffix in ('.json','.safetensors')}
    tokenizer=AutoTokenizer.from_pretrained(root);tokenizer.padding_side='left'
    model=AutoModelForCausalLM.from_pretrained(root,torch_dtype=torch.float32,low_cpu_mem_usage=True,attn_implementation='eager').eval()
    c=model.config
    assert (c.num_hidden_layers,c.num_experts,c.num_experts_per_tok,c.hidden_size)==(24,60,4,2048)
    def inputs(training):
        texts=prompts(training);tokens=tokenizer(texts,return_tensors='pt',padding='max_length',truncation=True,max_length=a.context)
        return texts,tokens
    with torch.inference_mode():
        texts,tokens=inputs(True);r=model(**tokens,output_router_logits=True,use_cache=False)
        prior=[]
        for logits in r.router_logits:
            chosen=logits.reshape(4,a.context,60)[:,-64:].softmax(-1).topk(4,dim=-1).indices
            prior.append(torch.bincount(chosen.flatten(),minlength=60).div(256).tolist())
        del r,tokens
        texts,tokens=inputs(False);r=model(**tokens,output_router_logits=False,use_cache=True)
        past=r.past_key_values;token=r.logits[:,-1:].argmax(-1);mask=tokens['attention_mask'];del r,tokens
        routes=[[] for _ in range(24)];probabilities=[[] for _ in range(24)];generated=[]
        started=time.time()
        for step in range(a.steps):
            mask=torch.cat((mask,torch.ones((32,1),dtype=mask.dtype)),dim=1)
            # The CausalLM wrapper's training auxiliary-loss mask is incompatible
            # with one-token cached router logits in Transformers4.51.3.
            # The underlying model computes identical hidden states/routers.
            r=model.model(input_ids=token,attention_mask=mask,past_key_values=past,output_router_logits=True,use_cache=True)
            for layer,logits in enumerate(r.router_logits):
                scores,ids=logits.float().softmax(-1).topk(4,dim=-1)
                routes[layer].extend(ids.tolist());probabilities[layer].extend((scores/scores.sum(-1,keepdim=True)).tolist())
            generated.append(token.flatten().tolist());past=r.past_key_values;token=model.lm_head(r.last_hidden_state[:,-1:]).argmax(-1);del r
            (out/'progress.json').write_text(json.dumps(dict(completed_steps=step+1,elapsed_s=time.time()-started)))
            print('captured',step+1,flush=True)
        record=dict(schema=1,model=MODEL,checkpoint_revision=REVISION,checkpoint_sha256=manifest,execution_dtype='FP32',architecture_dtype='BF16',model_matched_capture=True,
          capture_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),capture_api='Qwen2MoeModel plus original lm_head; bypass training-only auxiliary loss on cached Decode',source='Original public checkpoint inference; benign generated topic prompts',capture_context=a.context,steps=a.steps,max_batch=32,layers=24,experts=60,topk=4,
          prompt_sha256=hashlib.sha256(json.dumps(texts).encode()).hexdigest(),training_prompt_sha256=hashlib.sha256(json.dumps(prompts(True)).encode()).hexdigest(),
          training_scope='Four separate prompts, last64 prefill positions each;256 records; never holdout Decode',training_expected_activations=prior,routes=routes,route_probabilities=probabilities,generated_token_ids=generated,
          torch_version=torch.__version__,transformers_version=__import__('transformers').__version__,threads=a.threads,
          limitations=['FP32 routing is model-matched, not proof of BF16 identical top-k','B1/B8 sub-batches reuse a subset of32 routes; contexts other than512 are explicitly transfer sensitivities','Topic prompts are a controlled capture, not representative production traffic','CPU execution time is not simulated HB performance'])
        (out/'routes.json').write_text(json.dumps(record,separators=(',',':'))+'\n')
if __name__=='__main__':main()
