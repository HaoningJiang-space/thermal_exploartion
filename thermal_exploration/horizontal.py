"""Tensor-derived traffic and necessary capacity bounds, NOT a NoC simulator."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field

KINDS = ("Broadcast", "Reduction", "Redistribution", "All-to-all")


def route(source, target, side=4, order="xy"):
    if order not in ("xy", "yx") or not 0 <= source < side**2 or not 0 <= target < side**2:
        raise ValueError("Invalid route")
    x, y = source % side, source // side
    tx, ty = target % side, target // side
    nodes = [source]
    for axis in order:
        if axis == "x":
            while x != tx:
                x += 1 if tx > x else -1
                nodes.append(y * side + x)
        else:
            while y != ty:
                y += 1 if ty > y else -1
                nodes.append(y * side + x)
    return list(zip(nodes, nodes[1:]))


@dataclass
class Traffic:
    side: int = 4
    links: dict = field(default_factory=lambda: {k: Counter() for k in KINDS})
    vector_ops: Counter = field(default_factory=Counter)
    records: list = field(default_factory=list)

    def add(self, kind, edges, size, commodity):
        if kind not in KINDS or size < 0 or int(size) != size:
            raise ValueError("Unknown traffic kind or byte count")
        for source, target in sorted(edges):
            if len(route(source, target, self.side)) != 1:
                raise ValueError("Nonadjacent physical link")
            self.links[kind][source, target] += size
            self.records.append(dict(kind=kind,source=source,target=target,bytes=size,commodity=commodity))

    def broadcast(self, source, targets, size, commodity, order="xy"):
        edges = {edge for target in targets for edge in route(source, target, self.side, order)}
        self.add("Broadcast", edges, size, commodity)

    def reduce(self, producers, target, elements, commodity, order="xy"):
        producers = set(producers)
        edges = {edge for source in producers for edge in route(target, source, self.side, order)}
        children = defaultdict(list)
        for parent, child in edges:
            children[parent].append(child)
        # Each child subtree contributes one partial, plus a local producer.
        # Internal routers relay; additions are charged to their compute Tile.
        for node in set(children) | producers | {target}:
            self.vector_ops[node] += max(0, len(children[node]) + (node in producers) - 1) * elements
        self.add("Reduction", {(b,a) for a,b in edges}, elements * 4, commodity)
        if sum(max(0,len(children[n])+(n in producers)-1) for n in set(children)|producers|{target}) != max(0,len(producers)-1):
            raise ValueError("Reduction tree changed useful work")

    def unicast(self, kind, source, target, size, commodity):
        self.add(kind, route(source,target,self.side), size, commodity)

    def totals(self):
        return {k:sum(self.links[k].values()) for k in KINDS}


def gemm(m, n, batch, row_parts=16, column_parts=1, orientation="row", order="xy"):
    """Canonical input/output have 16 contiguous shards; W is static local."""
    if min(m,n,batch,row_parts,column_parts)<1 or row_parts * column_parts != 16 or m % 16 or n % 16 or orientation not in ("row", "column"):
        raise ValueError("Unbalanced matrix partition")
    traffic = Traffic()
    tile = lambda r,c: r*column_parts+c if orientation=="row" else c*row_parts+r
    # A canonical input shard fits entirely within one column partition.
    for source in range(16):
        c = source // row_parts
        traffic.broadcast(source, [tile(r,c) for r in range(row_parts)], n//16*batch*2,
                          f"x[{source*n//16}:{(source+1)*n//16},:]", order)
    # Output shards receive every contribution to that exact output range.
    for target in range(16):
        r = target // column_parts
        traffic.reduce([tile(r,c) for c in range(column_parts)], target, m//16*batch,
                       f"y[{target*m//16}:{(target+1)*m//16},:]", order)
    if sum(traffic.vector_ops.values()) != (column_parts-1)*m*batch:
        raise ValueError("Unconserved reduction work")
    work = dict(m=m,n=n,batch=batch,weight_bytes=m*n*2,mac_flops=2*m*n*batch,
                input_bytes=n*batch*2,output_bytes=m*batch*2,metric_work=2*m*n*batch,
                metric="TFLOP/s upper bound",metric_scale=1e12)
    partition = dict(row_parts=row_parts,column_parts=column_parts,orientation=orientation,tree_order=order)
    return traffic, work, partition


def redistribution(aligned=False):
    traffic = Traffic(); m,n=4096,32
    # Actual row-block -> column-block mapping of all elements, no dropped data.
    accounted = 0
    for source in range(16):
        for target in range(16):
            size = (m//16)*(n//16)*2
            accounted += size
            # Aligned relaxation changes initial DRAM ownership to the final
            # consumer layout. It does not change final output ownership.
            origin = target if aligned else source
            traffic.unicast("Redistribution", origin, target, size, f"tensor.rows{source}.cols{target}")
    if accounted != m*n*2:
        raise ValueError("Tensor permutation lost data")
    return traffic, dict(weight_bytes=accounted,mac_flops=0,input_bytes=accounted,output_bytes=accounted,
                         metric_work=accounted,metric="GB/s upper bound",metric_scale=1e9), dict(aligned=aligned)


def moe(expert_shift=0):
    traffic = Traffic(); tokens,dimension,topk,experts=256,4096,2,16
    assignments = Counter(); dispatch_bytes = 0
    for token in range(tokens):
        source = token % 16
        chosen = [(token//16 + source + branch*8) % experts for branch in range(topk)]
        if len(set(chosen)) != topk:
            raise ValueError("Repeated expert in top-k")
        for branch, expert in enumerate(chosen):
            target = (expert+expert_shift) % 16
            assignments[expert] += 1; dispatch_bytes += dimension*2
            traffic.unicast("All-to-all", source,target,dimension*2,f"dispatch.token{token}.expert{expert}")
            traffic.unicast("All-to-all", target,source,dimension*2,f"combine.token{token}.expert{expert}")
        traffic.vector_ops[source] += dimension*(topk-1)
    if set(assignments.values()) != {tokens*topk//experts}:
        raise ValueError("Frozen cohort must be balanced")
    return traffic,dict(weight_bytes=experts*2*dimension**2*2,mac_flops=4*tokens*topk*dimension**2,
                        input_bytes=tokens*dimension*2,output_bytes=tokens*dimension*2,
                        assignments=tokens*topk,logical_dispatch_bytes=dispatch_bytes,logical_combine_bytes=dispatch_bytes,
                        metric_work=4*tokens*topk*dimension**2,metric="TFLOP/s upper bound",metric_scale=1e12),dict(expert_shift=expert_shift)


def capacity_bounds(traffic, work, hb_tb_s, dram_tb_s, link_gb_s=32, relax="none"):
    if min(hb_tb_s,dram_tb_s,link_gb_s) <= 0 or relax not in ("none","infinite_noc","zero_collectives"):
        raise ValueError("Invalid capacity or relaxation")
    active = set(KINDS)
    if relax == "zero_collectives": active -= {"Broadcast","Reduction"}
    if relax == "infinite_noc": active.clear()
    loads = Counter()
    for kind in active: loads.update(traffic.links[kind])
    times = dict(dram_hb=work["weight_bytes"]/(min(hb_tb_s,dram_tb_s)*1e12),
                 mac=work["mac_flops"]/128e12,vector=max(traffic.vector_ops.values(),default=0)/64e9,
                 directed_link=max(loads.values(),default=0)/(link_gb_s*1e9))
    lower = max(times.values())
    cuts=[]
    for axis in ("x","y"):
        coordinate = lambda node: node%traffic.side if axis=="x" else node//traffic.side
        for direction in ("low_to_high","high_to_low"):
            edges=[(a,b) for a in range(traffic.side**2) for b in range(traffic.side**2)
                   if len(route(a,b,traffic.side))==1 and
                   (coordinate(a)<traffic.side//2<=coordinate(b) if direction=="low_to_high" else coordinate(b)<traffic.side//2<=coordinate(a))]
            by_kind={kind:sum(traffic.links[kind][edge] for edge in edges) for kind in KINDS}
            cuts.append(dict(axis=axis,direction=direction,links=len(edges),bytes_by_kind=by_kind,
                             bound_us=sum(by_kind[k] for k in active)/(len(edges)*link_gb_s*1e9)*1e6))
    if any(c["bound_us"] > times["directed_link"]*1e6+1e-10 for c in cuts):
        raise ValueError("Directed-link accounting violated a cut bound")
    return dict(completion_necessary_lower_us=lower*1e6,rate_upper=work["metric_work"]/lower/work["metric_scale"],
                metric=work["metric"],resource_lower_us={k:v*1e6 for k,v in times.items()},
                binding_resources=[k for k,v in times.items() if abs(v-lower)<=max(1e-15,lower*1e-9)],cuts=cuts,
                byte_hops_by_kind=traffic.totals(),vector_additions=sum(traffic.vector_ops.values()),
                noc_dynamic_energy_proxy_uj=sum(traffic.totals().values())*1e-6,
                energy_scope="Assumed 1 pJ/B-hop; original traffic retained in ideal timing controls; not a power/temperature prediction",relax=relax)


def scaling_example(side, vertical_bytes_cycle=64, link_bytes_cycle=32, crossing_fraction=.1):
    # One direction, matching the user's illustration; no full-duplex doubling.
    if side<2 or not 0<=crossing_fraction<=1:
        raise ValueError("Invalid density example")
    vertical=side**2*vertical_bytes_cycle; cut=side*link_bytes_cycle
    return dict(side=side,vertical_bytes_cycle=vertical,one_direction_cut_bytes_cycle=cut,
                crossing_demand_bytes_cycle=vertical*crossing_fraction,cut_pressure=vertical*crossing_fraction/cut,
                capacity_ratio=vertical/cut,critical_crossing_fraction=cut/vertical,
                fraction_scope="Traffic in one selected cut direction; not the sum of two full-duplex directions")
