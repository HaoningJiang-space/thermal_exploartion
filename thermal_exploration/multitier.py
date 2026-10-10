"""D2 frozen workload, address map and conservative timing-tier extensions.

Tiers share each physical bank and all column/ACT domains. They do not create
eight sets of banks. This is an architecture assumption, not Stratum replay.
"""
from math import ceil
from . import hb_trace

TIER_RCD_NS=(2.29,3.92,5.99,8.50,11.44,14.82,18.63,22.88)
CASES={
    'ordinary_striped':dict(task_bytes=65536,mapping='striped',ordered=1,buffer_bytes=131072,uniform=False),
    'mapped_prefetched':dict(task_bytes=4096,mapping='compact',ordered=0,buffer_bytes=524288,uniform=False),
    'fine_streaming_probe':dict(task_bytes=1024,mapping='compact',ordered=0,buffer_bytes=524288,uniform=False),
    'prefetched_striped':dict(task_bytes=4096,mapping='striped',ordered=0,buffer_bytes=524288,uniform=False),
    'uniform_prefetched':dict(task_bytes=4096,mapping='compact',ordered=0,buffer_bytes=524288,uniform=True),
    'uniform_fine_probe':dict(task_bytes=1024,mapping='compact',ordered=0,buffer_bytes=524288,uniform=True),
}


def contract(quantum=4096,rows=6144):
    if quantum not in (1024,4096,65536) or rows<=0 or rows>6144 or rows%6:
        raise ValueError('Invalid workload partition')
    kv_tile=16*(rows//6)*4096;weight_tile=16*(rows-rows//6)*4096
    if kv_tile%quantum or weight_tile%quantum:raise ValueError('Nonintegral tasks')
    return dict(kv_bytes=16*kv_tile,weight_bytes=16*weight_tile,
        total_bytes=16*(kv_tile+weight_tile),useful_flops=16*(2*kv_tile+weight_tile),
        requests=16*(kv_tile+weight_tile)//1024,kv_tasks=16*kv_tile//quantum,
        tasks=16*(kv_tile+weight_tile)//quantum,quantum=quantum,rows_per_bank=rows,
        capacity_bytes=32*2**30,fast_tier_capacity_bytes=4*2**30,
        sram_bytes_per_tile=36*2**20//16,available_prefetch_bytes_per_tile=524288,
        scope='10 FP16 32768x8192 expert projections (5GiB) after a 1GiB KV reduction; trace-level dependency/work model, no numerical LLM accuracy claim')


def request_identity(rid,quantum,mapping,rows=6144):
    c=contract(quantum,rows)
    if rid<0 or rid>=c['requests'] or mapping not in ('striped','compact'):raise ValueError('Invalid request/map')
    task=rid//(quantum//1024);tile=task%16;phase=int(task>=c['kv_tasks'])
    block=(task-(c['kv_tasks'] if phase else 0))//16
    byte=(c['kv_bytes']//16 if phase else 0)+block*quantum+(rid%(quantum//1024))*1024
    bank=(byte//4096)%16;rowblock=byte//(4096*16);column=(byte%4096)//1024
    row=rowblock if mapping=='compact' else ((bank+rowblock)%8)*4096+rowblock//8
    vec=[tile,bank//8,0,(bank%8)//2,bank%2,row,column*8]
    address=((row*256+bank*16+tile)*4+column)*1024
    return dict(task=task,tile=tile,phase=phase,address=address,vec=vec,tier=row//4096)


def tier_timings(uniform=False):
    # The native device uses0.25ns ticks. Base fastest row is rounded to2.5,
    #30,5,35ns; extend slow rows conservatively, never below these deadlines.
    rcd=[max(10,ceil(x/.25)) for x in TIER_RCD_NS]
    ras=[max(120,ceil((x+27.5)/.25)) for x in TIER_RCD_NS]
    rc=[x+20 for x in ras]
    if uniform:rcd=[rcd[0]]*8;ras=[ras[0]]*8;rc=[rc[0]]*8
    return dict(rcd_ticks=rcd,ras_ticks=ras,rc_ticks=rc)


def config(root,out,uniform=False,refresh=True):
    dram,cfg=hb_trace.ramulator_config(root,out,2,refresh=refresh)
    for ch,ctrl in enumerate(cfg['memory_system']['controllers']):
        ctrl['controller_plugins'].append(dict(impl='TierTiming',rows_per_tier=4096,
            path=str(out/f'tier-acts.ch{ch}.csv'),**tier_timings(uniform)))
    return dram,cfg


class TierLegality:
    """Independent extra-deadline checker, alongside upstream base replay."""
    def __init__(self,uniform=False):self.t=tier_timings(uniform);self.banks={}
    def issue(self,name,vec,clk):
        key=tuple(vec[:5]);tier=vec[5]//4096
        if not 0<=tier<8:raise ValueError('Tier capacity')
        if name=='PREab' or name=='REFab':
            for k,s in self.banks.items():
                if k[:2]==key[:2] and s.get('open') is not None:
                    needed=self.t['ras_ticks' if name=='PREab' else 'rc_ticks'][s['tier']]
                    if clk<s['act']+needed:raise ValueError('All-bank operation before tier restoration')
                    if name=='PREab':s.update(open=None,pre=clk)
            return
        s=self.banks.setdefault(key,dict(open=None,act=-10000,pre=-10000,tier=0))
        if name=='ACT':
            if s['open'] is not None or clk<s['pre']+20 or clk<s['act']+self.t['rc_ticks'][s['tier']]:
                raise ValueError('Bank/Tier row-cycle violation')
            s.update(open=vec[5],act=clk,tier=tier)
        elif name in ('RD','RDA','WR','WRA'):
            if s['open']!=vec[5] or clk<s['act']+self.t['rcd_ticks'][s['tier']]:raise ValueError('Tier activation-to-column violation')
            if name in ('RDA','WRA'):raise ValueError('Auto-precharge not supported by D2 checker')
        elif name=='PREpb':
            if s['open'] is not None and clk<s['act']+self.t['ras_ticks'][s['tier']]:raise ValueError('Tier restoration violation')
            s.update(open=None,pre=clk)
