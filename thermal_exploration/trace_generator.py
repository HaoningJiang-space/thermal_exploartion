"""Addressed, finite work traces for the isolated standard-HBM3 integration.

The bank-interleaved mapping below is a derived experimental policy, not a
Stratum map and not a manufacturer's physical address decoder.
"""
import json
from pathlib import Path

TX_BYTES=32
BANKS=64
ROW_BYTES=1024
ROWS=16384


def hbm3_address(address):
    if not isinstance(address,int) or address<0 or address%TX_BYTES:
        raise ValueError("HBM3 fixture addresses must be aligned, nonnegative bytes")
    txn=address//TX_BYTES; bank=txn%BANKS; column=(txn//BANKS)%32
    row=txn//(BANKS*32)
    if row>=ROWS:raise ValueError("Address exceeds the isolated one-channel geometry")
    return [0,bank%2,(bank//2)%2,(bank//4)%4,(bank//16)%4,row,column*8]


def inverse_hbm3_address(vec):
    ch,pc,sid,bg,bank,row,col=vec
    if ch!=0 or not (0<=pc<2 and 0<=sid<2 and 0<=bg<4 and 0<=bank<4
                     and 0<=row<ROWS and 0<=col<256 and col%8==0):
        raise ValueError("Invalid HBM3 fixture address vector")
    bank_id=pc+2*sid+4*bg+16*bank
    return ((row*32+col//8)*BANKS+bank_id)*TX_BYTES


def request(rid,address,source=0,deps=(),flops=0,kind="microbenchmark",**metadata):
    return dict(id=rid,timestamp=0,source_tile=source,address=address,size=TX_BYTES,
                rw="read",dependency=list(deps),target_bank=hbm3_address(address)[:5],
                addr_vec=hbm3_address(address),useful_flops=flops,kind=kind,**metadata)


def streaming(count=8192):
    return [request(i,i*TX_BYTES,i%16) for i in range(count)]


def row_conflict(count=256):
    # One dependent request at a time prevents FR-FCFS from grouping rows.
    return [request(i,(i%2)*BANKS*ROW_BYTES,deps=() if i==0 else (i-1,)) for i in range(count)]


def gemv(rows=128,columns=128):
    if rows<=0 or columns<=0 or columns%16:raise ValueError("FP16 columns must fill 32-byte transactions")
    n_input=columns*2//TX_BYTES
    req=[request(i,i*TX_BYTES,kind="input",column_start=i*16) for i in range(n_input)]
    base=2**20
    for row in range(rows):
        previous=None
        for column in range(0,columns,16):
            deps=list(range(n_input))
            if previous is not None:deps.append(previous)
            rid=len(req)
            req.append(request(rid,base+2*(row*columns+column),row%16,deps,32,
                               "weight",matrix_row=row,column_start=column))
            previous=rid
    validate_trace(req)
    return req


def validate_trace(req):
    if not req:raise ValueError("Empty work trace")
    ids=set()
    for i,r in enumerate(req):
        if r["id"]!=i or r["id"] in ids:raise ValueError("Request ids must be unique and contiguous")
        if any(d not in ids for d in r["dependency"]):raise ValueError("Dependency must reference an earlier request")
        if r["size"]!=TX_BYTES or r["rw"]!="read":raise ValueError("Minimal fixture currently supports complete 32-byte reads")
        if r["source_tile"] not in range(16) or r["timestamp"]<0 or r["useful_flops"]<0:
            raise ValueError("Invalid source/time/work")
        if inverse_hbm3_address(r["addr_vec"])!=r["address"]:
            raise ValueError("Address and target organization disagree")
        ids.add(i)
    return dict(request_count=len(req),read_bytes=sum(r["size"] for r in req),
                useful_flops=sum(r["useful_flops"] for r in req))


def write_trace(req,out):
    validate_trace(req);out=Path(out)
    (out/"requests.json").write_text(json.dumps(req,indent=2)+"\n")
    # Simple integer-only native interchange. The JSON preserves semantic fields.
    with (out/"requests.tsv").open("w") as f:
        for r in req:
            fields=[r["id"],r["timestamp"],r["source_tile"],r["address"],r["size"],r["useful_flops"]]
            fields+=r["addr_vec"]+[len(r["dependency"])]+r["dependency"]
            f.write("\t".join(map(str,fields))+"\n")


def verify_gemv_consumption(req,events,rows=128,columns=128):
    """Functional oracle outside Ramulator (which models timing, not values)."""
    import numpy as np
    w=((np.arange(rows)[:,None]*7+np.arange(columns)[None,:]*3)%23-11)/16
    x=((np.arange(columns)*5)%17-8)/16
    expected=w@x;actual=np.zeros(rows);coverage=np.zeros((rows,columns),dtype=int)
    for e in sorted(events,key=lambda e:(int(e["consumed"]),int(e["id"]))):
        r=req[int(e["id"])]
        if r["kind"]!="weight":continue
        i=r["matrix_row"];j=r["column_start"]
        actual[i]+=sum(w[i,k]*x[k] for k in range(j,j+16));coverage[i,j:j+16]+=1
    if not np.all(coverage==1) or not np.array_equal(actual,expected):
        raise ValueError("GEMV incomplete or duplicated arithmetic")
    return dict(rows=rows,columns=columns,batch=1,precision="FP16 values, FP64 independent oracle",
                useful_flops=2*rows*columns,input_bytes=2*columns,weight_bytes=2*rows*columns,
                output_bytes_resident_in_logic=2*rows,output_dram_writes=0,
                result_max_absolute_error=float(np.max(abs(actual-expected))),
                scope="Timing-only DRAM plus deterministic functional replay; output retained in Logic; broadcast/ports/array execution uncalibrated")
