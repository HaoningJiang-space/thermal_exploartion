// H2-A causal frontend around pinned Ramulator. No new DRAM controller.
#define main legacy_streaming_main
#include "ramulator_trace_driver.cpp"
#undef main
#include <array>
#include <deque>
#include <iomanip>
#include <cmath>

struct TensorTask {
 int id,tile,mstart,mcount,kstart,kcount,parent,group,final;
 long long flops,start=-1,finish=-1; std::vector<int> requests;
 bool admitted=false,done=false;
};
struct TensorRead {
 int id,tile,refs,remaining; long long address,accepted=-1,depart=-1,hb_first=-1,hb_done=-1,last_use=-1;
 Ramulator::AddrVec_t vec; int transferred=0; bool allocated=false;
};
struct TensorTree {
 int id,root,bytes,row,mask; std::array<int,16> parent;
 std::array<std::vector<int>,16> children;
 std::array<int,16> received{};
 std::array<std::vector<bool>,16> seen;
 std::array<long long,16> input_last{};
};
struct ReduceNode {
 bool local=false,slot=false,queued=false,complete=false,arrived=false;
 int next_flit=0,stage=0; long long ready=-1,start=-1,finish=-1;
 int read_left=0,ops_left=0,write_left=0,reserved=0;
 std::array<int,16> received{};
 std::array<std::vector<bool>,16> seen;
};
struct Flit {int kind,group,index,child;};
struct ArrivingFlit {long long time;int node,port,vc;Flit data;};
struct LaterFlit {
 bool operator()(const ArrivingFlit& a,const ArrivingFlit& b) const {return a.time>b.time;}
};
struct RouterQueue {std::deque<Flit> data;int incoming=0;};

int main(int argc,char** argv){try {
 if(argc!=4)throw std::runtime_error("config.json contract-directory output-prefix");
 std::string dir=argv[2],prefix=argv[3];
 int m,n,batch,pr,pc,mb,kb,wbudget,rbudget,redbudget,window,pbytes,ideal,barrier,ideal_memory;
 int stream_fifo=0,command_domains=1;
 double mac_rate=2000,fluid_service=26.599;int private_sram=2359296,fluid_memory=0;
 std::array<int,16> fixed;
 {std::ifstream f(dir+"/resources.tsv");
  if(!(f>>m>>n>>batch>>pr>>pc>>mb>>kb>>wbudget>>rbudget>>redbudget>>window>>pbytes>>ideal>>barrier>>ideal_memory))
   throw std::runtime_error("Invalid resource contract");
  for(auto& x:fixed)if(!(f>>x))throw std::runtime_error("Missing private SRAM");
  if(!(f>>stream_fifo))stream_fifo=0;
  if(!(f>>command_domains))command_domains=1;
  if(!(f>>mac_rate>>private_sram>>fluid_memory>>fluid_service)){mac_rate=2000;private_sram=2359296;fluid_memory=0;fluid_service=26.599;}
 }
 if(pr*pc!=16||wbudget<8192||wbudget>4194304||rbudget>wbudget||pbytes%32||window<1)
  throw std::runtime_error("Unsafe resource configuration");
 std::vector<TensorTask> tasks;std::array<std::vector<int>,16> local;
 {std::ifstream f(dir+"/tasks.tsv");std::string line;while(std::getline(f,line)){
   TensorTask t;int count;std::istringstream s(line);
   if(!(s>>t.id>>t.tile>>t.mstart>>t.mcount>>t.kstart>>t.kcount>>t.flops>>t.parent>>t.group>>t.final>>count))
    throw std::runtime_error("Invalid MAC task");
   if(t.id!=int(tasks.size())||t.tile<0||t.tile>=16||t.parent>=t.id)throw std::runtime_error("Task identity");
   for(int i=0;i<count;i++){int x;if(!(s>>x))throw std::runtime_error("Missing task weights");t.requests.push_back(x);}
   local[t.tile].push_back(t.id);tasks.push_back(t);
 }}
 std::vector<TensorRead> reads;
 {std::ifstream f(dir+"/requests.tsv");std::string line;while(std::getline(f,line)){
   TensorRead r;std::istringstream s(line);r.vec.resize(7);
   if(!(s>>r.id>>r.tile>>r.address>>r.refs))throw std::runtime_error("Invalid physical read");
   for(auto& x:r.vec)if(!(s>>x))throw std::runtime_error("Invalid physical address");
   if(r.id!=int(reads.size())||r.vec[0]!=r.tile||r.refs<1)throw std::runtime_error("Read owner/identity");
   r.remaining=r.refs;reads.push_back(r);
 }}
 auto read_trees=[&](std::string name){
  std::vector<TensorTree> groups;std::ifstream f(dir+"/"+name+".tsv");std::string line;
  while(std::getline(f,line)){
   TensorTree g;std::istringstream s(line);
   if(!(s>>g.id>>g.root>>g.bytes>>g.row>>g.mask))throw std::runtime_error("Invalid data tree");
   for(auto& x:g.parent)if(!(s>>x))throw std::runtime_error("Missing tree parent");
   if(g.id!=int(groups.size())||g.bytes%32)throw std::runtime_error("Unaligned tree");
   for(int node=0;node<16;node++){
    if(g.parent[node]>=0)g.children[g.parent[node]].push_back(node);
    g.seen[node].resize(g.bytes/32);g.input_last[node]=-1;
   }
   groups.push_back(g);
  }return groups;
 };
 auto inputs=read_trees("inputs");auto reductions=read_trees("reductions");
 std::vector<std::array<ReduceNode,16>> rn(reductions.size());
 std::vector<std::array<int,16>> local_remaining(reductions.size());
 for(auto& g:reductions)for(int tile=0;tile<16;tile++)if(g.mask&(1<<tile)){
  long long lo=1LL*g.id*pbytes,hi=lo+g.bytes,coverage=0;
  for(auto& t:tasks)if(t.tile==tile&&t.final){
   long long a=1LL*t.mstart*batch*4,b=1LL*(t.mstart+t.mcount)*batch*4;
   if(a<hi&&b>lo){local_remaining[g.id][tile]++;coverage+=std::min(b,hi)-std::max(a,lo);}
  }
  if(coverage!=g.bytes)throw std::runtime_error("Incomplete output packet coverage");
 }
 std::array<std::set<int>,16> x_pending,out_pending,vec_ready;
 std::array<int,16> vrunning,mac_running;vrunning.fill(-1);mac_running.fill(-1);
 std::array<long long,16> mac_until{};std::array<int,16> mac_rleft{},mac_wleft{},fifo_rleft{};
 std::array<std::set<int>,16> admitted,unsent;
 std::array<std::deque<int>,16> hb;
 std::array<int,16> wused{},response_used{},redused{},whigh{},rhigh{},redhigh{};
 std::array<size_t,16> admit_index{};
 std::array<int,16> x_next{};
 std::vector<int> input_next(inputs.size(),0);
 for(auto& g:inputs){
  if(g.mask&(1<<g.root)){g.received[g.root]=g.bytes;std::fill(g.seen[g.root].begin(),g.seen[g.root].end(),true);g.input_last[g.root]=0;}
  if(!g.children[g.root].empty())x_pending[g.root].insert(g.id);
 }
 auto has_node=[&](const TensorTree& g,int tile){return g.root==tile||(g.mask&(1<<tile))||!g.children[tile].empty();};
 auto expected_slot=[&](int gid,int tile){auto& g=reductions[gid];return int(g.children[tile].size()+1)*g.bytes;};
 auto reserve=[&](int gid,int tile){
  auto& a=rn[gid][tile];if(a.slot)return true;
  if(reductions[gid].children[tile].empty())return true;
  int need=expected_slot(gid,tile);if(redused[tile]+need>redbudget)return false;
  a.slot=true;a.reserved=need;redused[tile]+=need;redhigh[tile]=std::max(redhigh[tile],redused[tile]);return true;
 };
 auto ready=[&](int gid,int tile){
  auto& g=reductions[gid];auto& a=rn[gid][tile];
  if(!has_node(g,tile)||a.queued||a.complete)return false;
  if((g.mask&(1<<tile))&&!a.local)return false;
  for(int child:g.children[tile])if(a.received[child]!=g.bytes)return false;
  return true;
 };
 long long clk=0,mac_done=0,roots_done=0,accepted=0,returned=0,weight_bytes=0,flops=0,adds=0,casts=0;
 long long first_mac=-1,last_mac=-1,first_vector=-1,last_vector=-1,last_dram=-1,last_hb=-1,last_x=0;
 std::array<std::array<std::array<RouterQueue,2>,5>,16> fifo;
 std::array<std::array<long long,16>,16> link_until{};
 std::priority_queue<ArrivingFlit,std::vector<ArrivingFlit>,LaterFlit> arrivals;
 std::map<std::string,long long> states,counters;
 std::array<double,16> fluid_until{};
 std::priority_queue<std::pair<long long,int>,std::vector<std::pair<long long,int>>,std::greater<std::pair<long long,int>>> fluid_returns;
 std::ofstream noc(prefix+"-noc.csv"),inject(prefix+"-inject.csv"),sink(prefix+"-sink.csv"),jobs(prefix+"-vector.csv"),ports(prefix+"-ports.csv");
 noc<<"kind,group,flit,source,target,bytes,start,finish\n";
 inject<<"kind,group,flit,tile,tick\n";sink<<"kind,group,flit,child,tile,tick\n";
 jobs<<"group,tile,start,finish,read_bytes,ops,write_bytes,root\n";
 ports<<"tick,tile,read_bytes,write_bytes,vector_ops,weight_used,response_used,reduce_used,router_flits,fifo_ingress_bytes,fifo_operand_bytes\n";
 auto port_for=[](int node,int from){
  if(from==node)return 4;
  if(from==node-1&&node%4)return 0;
  if(from==node+1&&node%4!=3)return 1;
  if(from==node-4)return 2;
  if(from==node+4)return 3;
  throw std::runtime_error("Nonlocal physical link");
 };
 auto cfg=Ramulator::Config::parse_config_file(argv[1]);
 auto* frontend=Ramulator::Factory::create_frontend(cfg);auto* memory=Ramulator::Factory::create_memory_system(cfg);
 frontend->connect_memory_system(memory);memory->connect_frontend(frontend);
 if(memory->get_tx_bytes()!=1024)throw std::runtime_error("Changed transaction size");
 auto deliver=[&](const Flit& f,int tile){
  if(f.kind==0){auto& g=inputs[f.group];
   if(!(g.mask&(1<<tile))||g.seen[tile][f.index])throw std::runtime_error("Repeated/unneeded input");
   g.seen[tile][f.index]=true;g.received[tile]+=32;g.input_last[tile]=clk;last_x=std::max(last_x,clk);
  }else{auto& a=rn[f.group][tile];auto& g=reductions[f.group];
   if(g.parent[f.child]!=tile||!a.slot)throw std::runtime_error("Unreserved reduction return");
   if(a.seen[f.child].empty())a.seen[f.child].resize(g.bytes/32);
   if(a.seen[f.child][f.index])throw std::runtime_error("Repeated partial flit");
   a.seen[f.child][f.index]=true;a.received[f.child]+=32;
   if(ready(f.group,tile))vec_ready[tile].insert(f.group);
  }
  sink<<(f.kind==0?"X":"R")<<","<<f.group<<","<<f.index<<","<<f.child<<","<<tile<<","<<clk<<"\n";
 };
 auto release_output=[&](int gid,int tile){
  auto& g=reductions[gid];auto& a=rn[gid][tile];
  if(tile==g.root){roots_done++;if(a.slot){redused[tile]-=a.reserved;a.slot=false;}}
  else out_pending[tile].insert(gid);
 };
 for(;clk<2000000;clk++){
  while(!fluid_returns.empty()&&fluid_returns.top().first<=clk){
   auto [when,rid]=fluid_returns.top();fluid_returns.pop();auto& r=reads[rid];
   if(r.depart>=0||r.accepted<0)throw std::runtime_error("Fluid response identity");
   r.depart=when;last_dram=std::max(last_dram,when);hb[r.tile].push_back(rid);returned++;weight_bytes+=1024;
  }
  while(!arrivals.empty()&&arrivals.top().time<=clk){
   auto f=arrivals.top();arrivals.pop();auto& q=fifo[f.node][f.port][f.vc];
   if(q.incoming<=0)throw std::runtime_error("Unreserved router FIFO");
   q.incoming--;q.data.push_back(f.data);
  }
  for(int tile=0;tile<16;tile++)if(mac_running[tile]>=0&&mac_until[tile]<=clk){
   int id=mac_running[tile];auto& t=tasks[id];
   if(mac_rleft[tile]||mac_wleft[tile]||fifo_rleft[tile])throw std::runtime_error("MAC finished before SRAM/FIFO service");
   t.done=true;t.finish=clk;mac_done++;flops+=t.flops;last_mac=clk;
   for(int rid:t.requests){auto& r=reads[rid];if(r.hb_done<0||--r.remaining<0)throw std::runtime_error("Weight use");
    r.last_use=clk;if(!r.remaining){wused[tile]-=1024;r.allocated=false;}}
   admitted[tile].erase(id);mac_running[tile]=-1;
   if(t.final)for(auto& g:reductions)if(1LL*g.id*pbytes<1LL*(t.mstart+t.mcount)*batch*4&&1LL*g.id*pbytes+g.bytes>1LL*t.mstart*batch*4&&(g.mask&(1<<tile))){
    if(--local_remaining[g.id][tile]<0)throw std::runtime_error("Repeated packet microtile completion");
    if(local_remaining[g.id][tile])continue;
    auto& a=rn[g.id][tile];if(a.local)throw std::runtime_error("Duplicate output block");
    a.local=true;a.ready=clk;
    if(g.children[tile].empty()&&tile!=g.root){a.complete=true;a.finish=clk;release_output(g.id,tile);}
    else if(ready(g.id,tile))vec_ready[tile].insert(g.id);
   }
  }
  if(mac_done==int(tasks.size())&&roots_done==int(reductions.size()))break;
  std::array<int,16> rb,wb,vb;rb.fill(256);wb.fill(128);vb.fill(16);
  std::array<int,16> fifo_read{};
  for(int tile=0;tile<16;tile++){
   // Admit complete task footprints atomically; never fill the cache with
   // unreachable fragments of a task that cannot fit.
   while(admit_index[tile]<local[tile].size()&&admitted[tile].size()<size_t(window)){
    auto& t=tasks[local[tile][admit_index[tile]]];int missing=0;
    for(int rid:t.requests)if(!reads[rid].allocated)missing+=1024;
    if(missing+wused[tile]>wbudget)break;
    for(int rid:t.requests)if(!reads[rid].allocated){auto& r=reads[rid];
     if(r.remaining<=0||r.accepted>=0)throw std::runtime_error("Released physical data reread");
     r.allocated=true;wused[tile]+=1024;unsent[tile].insert(rid);}
    t.admitted=true;admitted[tile].insert(t.id);admit_index[tile]++;
   }
   whigh[tile]=std::max(whigh[tile],wused[tile]);
   if(mac_running[tile]<0){
    int chosen=-1;std::string why="no_remaining_work";bool first_dependency_ready=false;
    for(int id:admitted[tile]){auto& t=tasks[id];bool weights=true;
     for(int rid:t.requests)if(reads[rid].hb_done<0){weights=false;break;}
     if(t.parent>=0&&!tasks[t.parent].done){if(!first_dependency_ready)why="partial_sum_dependency";continue;}
     bool input=inputs[t.group].received[tile]==inputs[t.group].bytes;
     if(!first_dependency_ready){why=!input?(!weights?"missing_input_and_weight":"missing_input"):"missing_weight";first_dependency_ready=true;}
     if(!input||!weights)continue;
     chosen=id;break;
    }
    if(chosen>=0){auto& t=tasks[chosen];t.start=clk;
     mac_rleft[tile]=(stream_fifo?0:t.mcount*t.kcount*2)+t.kcount*batch*2+(t.parent>=0?t.mcount*batch*4:0);
     mac_wleft[tile]=t.mcount*batch*4;
     fifo_rleft[tile]=stream_fifo?t.mcount*t.kcount*2:0;
     long long duration=std::max<long long>({1LL,(long long)std::ceil(t.flops/mac_rate),(mac_rleft[tile]+255)/256,(mac_wleft[tile]+127)/128,stream_fifo?(t.mcount*t.kcount*2+499)/500:0});
     mac_until[tile]=clk+duration;mac_running[tile]=chosen;
     if(first_mac<0)first_mac=clk;
    }else{if(why=="no_remaining_work"&&admit_index[tile]<local[tile].size())why="weight_cache_credit";
     states[why]++;}
   }
   if(mac_running[tile]>=0){
    long long left=mac_until[tile]-clk;
    int read=(mac_rleft[tile]+left-1)/left,write=(mac_wleft[tile]+left-1)/left;
    rb[tile]-=read;wb[tile]-=write;mac_rleft[tile]-=read;mac_wleft[tile]-=write;
    fifo_read[tile]=(fifo_rleft[tile]+left-1)/left;fifo_rleft[tile]-=fifo_read[tile];
    if(fifo_read[tile]>500)throw std::runtime_error("FIFO operand port overrun");
    if(std::min(rb[tile],wb[tile])<0)throw std::runtime_error("MAC SRAM overrun");
    states["mac_occupied"]++;
   }
   // Vector packets preserve all child/local contributions. No in-router add.
   if(vrunning[tile]<0&&(!barrier||mac_done==int(tasks.size()))){
    for(auto it=vec_ready[tile].begin();it!=vec_ready[tile].end();++it){
     int gid=*it;if(!reserve(gid,tile))continue;
     auto& a=rn[gid][tile];auto& g=reductions[gid];int count=g.children[tile].size()+bool(g.mask&(1<<tile));
     if(count<1)throw std::runtime_error("Reduction without contribution");
     a.start=clk;a.queued=true;a.read_left=count*g.bytes;
     a.ops_left=(count-1)*g.bytes/4+(tile==g.root?g.bytes/4:0);
     a.write_left=tile==g.root?g.bytes/2:g.bytes;
     if(first_vector<0)first_vector=clk;
     vrunning[tile]=gid;vec_ready[tile].erase(it);break;
    }
   }
   if(vrunning[tile]>=0){auto& a=rn[vrunning[tile]][tile];
    if(a.read_left){int x=std::min(rb[tile],a.read_left);a.read_left-=x;rb[tile]-=x;}
    else if(a.ops_left){int x=std::min(vb[tile],a.ops_left);a.ops_left-=x;vb[tile]-=x;}
    else if(a.write_left){int x=std::min(wb[tile],a.write_left);a.write_left-=x;wb[tile]-=x;}
    if(!a.read_left&&!a.ops_left&&!a.write_left){
     int gid=vrunning[tile];auto& g=reductions[gid];int count=g.children[tile].size()+bool(g.mask&(1<<tile));
     a.complete=true;a.finish=clk+1;last_vector=clk+1;
     adds+=(count-1)*g.bytes/4;if(tile==g.root)casts+=g.bytes/4;
     jobs<<gid<<","<<tile<<","<<a.start<<","<<a.finish<<","<<count*g.bytes<<","<<(count-1)*g.bytes/4+(tile==g.root?g.bytes/4:0)<<","<<(tile==g.root?g.bytes/2:g.bytes)<<","<<(tile==g.root)<<"\n";
     // Completion becomes visible next tick; outgoing SRAM read is gated.
     release_output(gid,tile);vrunning[tile]=-1;
    }
   }
  }
  // Real routers share full-duplex physical links across two virtual networks.
  if(!ideal)for(int node=0;node<16;node++)for(int attempt=0;attempt<10;attempt++){
   int selector=(clk+attempt)%10,port=selector/2,vc=selector%2;
   if(port==4&&vc==1)continue; // Local reduction injection is sent below.
   auto& q=fifo[node][port][vc];if(q.data.empty())continue;
   const Flit f=q.data.front();std::vector<int> targets;
   bool need_write=false;
   if(f.kind==0){targets=inputs[f.group].children[node];
    need_write=(inputs[f.group].mask&(1<<node))&&!inputs[f.group].seen[node][f.index];
   }else need_write=true;
   if(need_write&&wb[node]<32){counters["noc_sram_backpressure"]++;continue;}
   bool possible=true;
   for(int target:targets){auto& other=fifo[target][port_for(target,node)][vc];
    if(link_until[node][target]>clk||other.data.size()+other.incoming>=8)possible=false;}
   if(!possible){counters["noc_link_or_fifo_backpressure"]++;continue;}
   if(need_write){wb[node]-=32;deliver(f,node);}
   for(int target:targets){auto& other=fifo[target][port_for(target,node)][vc];other.incoming++;
    link_until[node][target]=clk+4;arrivals.push({clk+8,target,port_for(target,node),vc,f});
    noc<<(f.kind==0?"X":"R")<<","<<f.group<<","<<f.index<<","<<node<<","<<target<<",32,"<<clk<<","<<clk+8<<"\n";
   }
   q.data.pop_front();
  }
  // Injection reads use the SAME SRAM read budget as MAC and vectors.
  for(int tile=0;tile<16;tile++){
   for(int attempt=0;attempt<8&&rb[tile]>=32;attempt++){
    bool sent=false;
    if(!x_pending[tile].empty()){
     int gid=*x_pending[tile].begin();auto& g=inputs[gid];int index=input_next[gid];
     auto& q=fifo[tile][4][0];bool possible=ideal||q.data.size()+q.incoming<8;
     if(ideal)for(int target=0;target<16;target++)if((g.mask&(1<<target))&&target!=tile&&wb[target]<32)possible=false;
     if(possible){Flit f{0,gid,index,tile};rb[tile]-=32;
      if(ideal){for(int target=0;target<16;target++)if((g.mask&(1<<target))&&target!=tile){wb[target]-=32;deliver(f,target);}
       for(int node=0;node<16;node++)for(int target:g.children[node])noc<<"X,"<<gid<<","<<index<<","<<node<<","<<target<<",32,"<<clk<<","<<clk<<"\n";
      }else q.data.push_back(f);
      inject<<"X,"<<gid<<","<<index<<","<<tile<<","<<clk<<"\n";
      if(++input_next[gid]==g.bytes/32)x_pending[tile].erase(gid);sent=true;
     }
    }
    if(!sent&&!out_pending[tile].empty()){
     for(auto it=out_pending[tile].begin();it!=out_pending[tile].end();++it){
      int gid=*it;auto& a=rn[gid][tile];auto& g=reductions[gid];int parent=g.parent[tile];
      if(a.finish>clk||parent<0||!reserve(gid,parent))continue;
      auto& q=fifo[tile][4][1];
      if(!ideal&&q.data.size()+q.incoming>=8)break;
      if(ideal&&wb[parent]<32)continue;
      Flit f{1,gid,a.next_flit,tile};rb[tile]-=32;
      inject<<"R,"<<gid<<","<<a.next_flit<<","<<tile<<","<<clk<<"\n";
      if(ideal){wb[parent]-=32;deliver(f,parent);noc<<"R,"<<gid<<","<<a.next_flit<<","<<tile<<","<<parent<<",32,"<<clk<<","<<clk<<"\n";}
      else{
       // Reduction is hop-local: parent accumulates before forwarding.
       q.data.push_back(f);
      }
      if(++a.next_flit==g.bytes/32){out_pending[tile].erase(it);if(a.slot){redused[tile]-=a.reserved;a.slot=false;}}
      sent=true;break;
     }
    }
    if(!sent)break;
   }
  }
  // Reduction packets travel one reverse-tree edge, then actually eject.
  if(!ideal)for(int tile=0;tile<16;tile++){
   auto& q=fifo[tile][4][1];
   if(q.data.empty())continue;auto f=q.data.front();int target=reductions[f.group].parent[tile];
   auto& other=fifo[target][port_for(target,tile)][1];
   if(link_until[tile][target]<=clk&&other.data.size()+other.incoming<8){
    link_until[tile][target]=clk+4;other.incoming++;
    arrivals.push({clk+8,target,port_for(target,tile),1,f});
    noc<<"R,"<<f.group<<","<<f.index<<","<<tile<<","<<target<<",32,"<<clk<<","<<clk+8<<"\n";q.data.pop_front();
   }
  }
  // HB and SRAM consume only returned bytes, bounded by reserved credits.
  for(int tile=0;tile<16;tile++){
   int bandwidth=500;
   while(bandwidth>0&&(stream_fifo||wb[tile]>0)&&!hb[tile].empty()){
    auto& r=reads[hb[tile].front()];if(r.depart>clk)break;
    int transfer=std::min({bandwidth,stream_fifo?500:wb[tile],1024-r.transferred});
    if(r.hb_first<0)r.hb_first=clk;
    r.transferred+=transfer;bandwidth-=transfer;if(!stream_fifo)wb[tile]-=transfer;
    if(r.transferred==1024){r.hb_done=clk+1;last_hb=clk+1;response_used[tile]-=1024;hb[tile].pop_front();}
   }
   if(!unsent[tile].empty()&&response_used[tile]+1024<=rbudget){
    int rid=*unsent[tile].begin();auto& r=reads[rid];
    auto physical=r.vec;
    if(command_domains==2){physical[0]=tile*2+physical[1];physical[1]=0;}
    Ramulator::Request request(physical,Ramulator::Request::Type::Read);request.addr=r.address;request.source_id=tile;request.ingress_id=rid;request.size_bytes=1024;
    request.callback=[&,rid,tile](Ramulator::Request& response){auto& r=reads[rid];
     if(response.ingress_id!=rid||r.accepted<0||r.depart>=0)throw std::runtime_error("Duplicate/wrong DRAM response");
     // HBM3 serializes0.5ns CK into two0.25ns native ticks. Generated device
     // timing and this driver's Logic period therefore use the SAME unit.
     r.depart=response.depart;last_dram=std::max(last_dram,r.depart);hb[tile].push_back(rid);returned++;weight_bytes+=1024;
    };
    if(ideal_memory||fluid_memory||memory->send(request)){
     r.accepted=clk;accepted++;response_used[tile]+=1024;unsent[tile].erase(rid);rhigh[tile]=std::max(rhigh[tile],response_used[tile]);
     if(ideal_memory){r.depart=clk+1;last_dram=clk+1;hb[tile].push_back(rid);returned++;weight_bytes+=1024;}
     else if(fluid_memory){
      // Measured long-stream service guard, no parameter fitting. Shared
      // executor intentionally keeps identical input groups, ports and MACs.
      // This backend cannot validate any DRAM command or Bank/Tier behavior.
      fluid_until[tile]=std::max(fluid_until[tile],double(clk))+1024/(fluid_service*1000*.25/16);
      fluid_returns.push({(long long)std::ceil(fluid_until[tile])+26,rid});
     }
    }
    else counters["controller_reject"]++;
   }else if(!unsent[tile].empty())counters["response_credit_stall"]++;
   int queued=0;for(int port=0;port<5;port++)for(int vc=0;vc<2;vc++){
    auto& q=fifo[tile][port][vc];if(q.data.size()+q.incoming>8)throw std::runtime_error("Router credit overflow");queued+=q.data.size()+q.incoming;}
   if(std::min({rb[tile],wb[tile],vb[tile],wused[tile],response_used[tile],redused[tile]})<0||wused[tile]>wbudget||response_used[tile]>rbudget||redused[tile]>redbudget||
      fixed[tile]+65536+wused[tile]+response_used[tile]+redused[tile]>private_sram)throw std::runtime_error("Physical resource overflow");
   ports<<clk<<","<<tile<<","<<256-rb[tile]<<","<<128-wb[tile]<<","<<16-vb[tile]<<","<<wused[tile]<<","<<response_used[tile]<<","<<redused[tile]<<","<<queued<<","<<(stream_fifo?500-bandwidth:0)<<","<<fifo_read[tile]<<"\n";
  }
  memory->tick();
 }
 if(mac_done!=int(tasks.size())||roots_done!=int(reductions.size())||accepted!=int(reads.size())||returned!=accepted||
    flops!=2LL*m*n*batch||adds!=1LL*(pc-1)*m*batch||casts!=1LL*m*batch)
  throw std::runtime_error("Incomplete tensor execution");
 // Final vector writes ended at clk (exclusive endpoint), even if root
 // completion was registered while consuming the previous tick's port.
 clk=std::max(clk,last_vector);
 memory->update_stats_recursive();std::ofstream stats(prefix+"-stats.yaml");memory->print_stats(stats);memory->finalize();frontend->finalize();
 std::ofstream taskout(prefix+"-tasks.csv");
 taskout<<"id,tile,m_start,k_start,parent,flops,start,finish,final\n";
 for(auto& t:tasks)taskout<<t.id<<","<<t.tile<<","<<t.mstart<<","<<t.kstart<<","<<t.parent<<","<<t.flops<<","<<t.start<<","<<t.finish<<","<<t.final<<"\n";
 std::ofstream readout(prefix+"-reads.csv");
 readout<<"id,tile,address,accepted,depart,hb_first,hb_done,last_use,refs\n";
 for(auto& r:reads)readout<<r.id<<","<<r.tile<<","<<r.address<<","<<r.accepted<<","<<r.depart<<","<<r.hb_first<<","<<r.hb_done<<","<<r.last_use<<","<<r.refs<<"\n";
 std::ofstream xout(prefix+"-inputs.csv");xout<<"group,tile,bytes,last_tick\n";
 for(auto& g:inputs)for(int tile=0;tile<16;tile++)if(g.mask&(1<<tile)){
  if(g.received[tile]!=g.bytes)throw std::runtime_error("Incomplete input distribution");
  xout<<g.id<<","<<tile<<","<<g.bytes<<","<<g.input_last[tile]<<"\n";}
 std::ofstream report(prefix+"-driver.json");
 report<<"{\"ticks\":"<<clk<<",\"requests\":"<<accepted<<",\"returned\":"<<returned<<",\"dram_bytes\":"<<weight_bytes<<",\"mac_flops\":"<<flops<<",\"reduction_adds\":"<<adds<<",\"output_casts\":"<<casts
       <<",\"first_mac\":"<<first_mac<<",\"last_mac\":"<<last_mac<<",\"first_vector\":"<<first_vector<<",\"last_vector\":"<<last_vector<<",\"last_dram_return\":"<<last_dram<<",\"last_hb_write\":"<<last_hb<<",\"last_input\":"<<last_x
       <<",\"weight_high\":"<<*std::max_element(whigh.begin(),whigh.end())<<",\"response_high\":"<<*std::max_element(rhigh.begin(),rhigh.end())<<",\"reduce_high\":"<<*std::max_element(redhigh.begin(),redhigh.end())<<",\"mac_states\":{";
 bool first=true;for(auto [key,value]:states){if(!first)report<<",";first=false;report<<"\""<<key<<"\":"<<value;}report<<"},\"backpressure\":{";
 first=true;for(auto [key,value]:counters){if(!first)report<<",";first=false;report<<"\""<<key<<"\":"<<value;}report<<"}}\n";
 delete memory;delete frontend;return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
