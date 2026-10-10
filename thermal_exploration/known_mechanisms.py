"""Fixed K32 read-only mechanism probes. No claim of full SALP reproduction."""
from . import hb_trace

MECHANISMS={
    "baseline":dict(timing_scale=1.,subarrays=1,selector_ck=0),
    "timing_margin_10pct":dict(timing_scale=.9,subarrays=1,selector_ck=0),
    "timing_margin_20pct":dict(timing_scale=.8,subarrays=1,selector_ck=0),
    "subarray_overlap_2":dict(timing_scale=1.,subarrays=2,selector_ck=1),
    "row_cycle_oracle":dict(timing_scale=1.,subarrays=1,selector_ck=0,relax_row_retention=True)
}


def adapt(req,subarrays):
    for r in req:
        vec=hb_trace.address_vector(r["address"],2)
        vec[2]=vec[5]%subarrays;vec[5]//=subarrays
        r["addr_vec"]=vec;r["target_bank"]=vec[:5]
    return req


def validate(req,subarrays=1):
    for i,r in enumerate(req):
        v=hb_trace.address_vector(r["address"],2);v[2]=v[5]%subarrays;v[5]//=subarrays
        if r["id"]!=i or r["addr_vec"]!=v or r["size"]!=1024 or r["rw"]!="read":
            raise ValueError("Logical bank/subarray/capacity/transaction mismatch")
    return dict(request_count=len(req),read_bytes=1024*len(req),useful_flops=sum(r["useful_flops"] for r in req))


def trace(name,partial=False):
    subarrays=MECHANISMS[name]["subarrays"]
    if partial:
        req=[hb_trace.hb_request(i,i*4096,2,(i%256)%16) for i in range(262144)]
    else:req=hb_trace.streaming_trace(2,1048576)
    return adapt(req,subarrays)


def mechanism_audit(commands):
    # Count actual open-row closures and implicit subarray selections. Base
    # timing replay separately proves tRAS/tRP for every local subarray state.
    open_rows={};active={};selected={};overlap=0;selectors=0;closed=0
    for c in commands:
        key=tuple(int(c[k]) for k in ("Channel","PseudoChannel","Sid","BankGroup","Bank"))
        physical=(key[0],key[1],key[3],key[4]);name=c["command"]
        if name=="ACT":
            if active.get(physical,set())-{key[2]}:overlap+=1
            open_rows[key]=int(c["Row"])
            active.setdefault(physical,set()).add(key[2])
        elif name=="PREpb":
            open_rows.pop(key,None);active.setdefault(physical,set()).discard(key[2])
        elif name=="PREab":
            targets=[k for k in open_rows if k[:2]==key[:2]];closed+=len(targets)
            for k in targets:
                open_rows.pop(k);active.setdefault((k[0],k[1],k[3],k[4]),set()).discard(k[2])
        elif name in ("RD","RDA"):
            if open_rows.get(key)!=int(c["Row"]):raise ValueError("Column command has wrong local row buffer")
            if selected.get(physical)!=key[2]:selectors+=1;selected[physical]=key[2]
    return dict(overlapping_ACTs=overlap,selector_events=selectors,PREab_rows=closed,
                selector_scope="Implicit address-selected local row buffer; 0.5ns first-access delay plus charged area/energy; not literal MASA SA_SEL commands")
