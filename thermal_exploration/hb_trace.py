"""Local, bank-interleaved 1024-byte traces for the assumed HB organization."""
TX=1024


def address_vector(address,paths):
    if address<0 or address%TX:raise ValueError("Unaligned assumed HB address")
    txn=address//TX;column=txn%4;bank=(txn//4)%256;row=txn//1024
    if row>=32768:raise ValueError("Outside 32 GiB assumed memory")
    channel=bank%16;local=bank//16;bp=16//paths
    return [channel,local//bp,0,(local%bp)//(4//paths),local%(4//paths),row,column*8]


def encoded(channel,bank,row,column):
    return ((row*256+bank*16+channel)*4+column)*TX


def hb_request(rid,address,paths,source,deps=(),flops=0,kind="stream"):
    vec=address_vector(address,paths)
    return dict(id=rid,timestamp=0,source_tile=source,address=address,size=TX,rw="read",
        dependency=list(deps),target_bank=vec[:5],addr_vec=vec,useful_flops=flops,kind=kind)


def streaming_trace(paths,count=32768):
    return [hb_request(i,i*TX,paths,address_vector(i*TX,paths)[0]) for i in range(count)]


def gemv_trace(paths):
    req=[hb_request(i,i*TX,paths,0,kind="input") for i in range(8)]
    # Weights use rows 64..95. All fit the 4 GiB fast tier; placement is the
    # same optimized local interleaving policy for every organization.
    for row in range(4096):
        previous=None
        for column in range(8):
            deps=list(range(8))
            if previous is not None:deps.append(previous)
            address=encoded(row%16,(row//16)%16,64+(row//256)*2+column//4,column%4)
            rid=len(req);req.append(hb_request(rid,address,paths,row%16,deps,1024,"weight"));previous=rid
    return req


def validate(req,paths):
    for i,r in enumerate(req):
        if r["id"]!=i or r["size"]!=TX or r["rw"]!="read":raise ValueError("Request id/transaction mismatch")
        if r["addr_vec"]!=address_vector(r["address"],paths):raise ValueError("Bank/row/port map mismatch")
        if any(d>=i or d<0 for d in r["dependency"]):raise ValueError("Invalid dependency")
        if r["kind"]=="weight" and r["source_tile"]!=r["addr_vec"][0]:raise ValueError("Remote compute-memory access is forbidden")
    return dict(request_count=len(req),read_bytes=sum(r["size"] for r in req),useful_flops=sum(r["useful_flops"] for r in req))


def ramulator_config(root,out,paths,refresh=True,relax_row_retention=False):
    # Reuse the frozen HBM3 state/controller definitions as an explicitly
    # assumed internal service surrogate. This is not standard HBM3 or Mono3D.
    from .run_g4 import device_and_config
    _,config=device_and_config(out,refresh)
    controller=config["memory_system"]["controllers"][0]
    import ramulator
    base=ramulator.dram.HBM3
    # Only Python configuration generation is specialized; native commands and
    # controller remain unchanged. The generated complete timing constraints
    # are rebuilt, rather than changing a timing vector with stale constraints.
    class InternalSurrogate(base):
        name="HBM3"
        data_payload_bytes=TX
        @classmethod
        def resolve_secondary_timings(cls,t,org):
            base.resolve_secondary_timings(t,org)
            t.update(nCCDL=2,nCCDR=2,nRFC=700,nRFCpb=400,nRFMab=700,nRFMpb=400,
                     nREFI=7800,nREFIpb=7800//(16//paths),nRREFD=16)
            if relax_row_retention:
                t["nRAS"]=t["nRCDRD"]+8  # keep four 1ns reads after ACT
                t["nRC"]=t["nRAS"]+t["nRP"]
    from math import ceil
    timing={name:ceil(ns/.5) for name,ns in dict(nRCDRD=2.29,nRCDWR=2.29,nRP=4.77,nRAS=29.79,
        nRRDS=2.5,nRRDL=3.125,nFAW=15.,nCL=4.,nCWL=4.).items()}
    dram=InternalSurrogate(org_preset="HBM3_16Gb_8hi",timing_preset="HBM3_6400Mbps",
        pseudochannel=paths,sid=1,bankgroup=4,bank=4//paths,row=32768,column=32,
        dq=1024,channel_width=8192*paths,rate=16000,tCK_ps=500,nBL=2,nCCDS=2,**timing)
    controller["dram"]=dram.to_config()
    controllers=[]
    import copy
    for channel in range(16):
        c=copy.deepcopy(controller)
        c["controller_plugins"][0]["path"]=str(out/"commands.csv")
        c["controller_plugins"][1]["path"]=str(out/f"transaction-commands.ch{channel}.csv")
        controllers.append(c)
    config["memory_system"]["controllers"]=controllers
    return dram,config
