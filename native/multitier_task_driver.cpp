// Task joins and finite prefetch storage around unmodified Ramulator commands.
// Reuse the transaction plugins; the legacy streaming main is not called.
#define main legacy_streaming_main
#include "ramulator_trace_driver.cpp"
#undef main
#include <deque>
#include <array>

struct Task {
 int tile,phase,first,count,parent=-1,received=0,previous=-1;
 long long flops,first_return=-1,last_return=-1,start=-1,finish=-1;
 int last_request=-1; bool admitted=false,done=false; std::string cause;
};
struct Packet {long long accepted=-1,depart=-1,delivered=-1;};

int main(int argc,char** argv){try{
 if(argc!=8)throw std::runtime_error("config out-prefix task-bytes mapping ordered buffer-bytes rows-per-bank");
 auto cfg=Ramulator::Config::parse_config_file(argv[1]);std::string prefix=argv[2];
 int quantum=std::stoi(argv[3]);std::string mapping=argv[4];bool ordered=std::stoi(argv[5]);
 long long budget=std::stoll(argv[6]);int rows=std::stoi(argv[7]);
 if(quantum<1024||quantum>65536||quantum%1024||budget<quantum||budget>524288||rows<2||rows>6144||rows%6)
  throw std::runtime_error("Invalid finite execution contract");
 if(mapping!="striped"&&mapping!="compact")throw std::runtime_error("Unknown placement");
 const long long phase_bytes[2]={16LL*(rows/6)*4096,16LL*(rows-rows/6)*4096}; // per tile
 if(phase_bytes[0]%quantum||phase_bytes[1]%quantum)throw std::runtime_error("Task does not partition problem");
 std::vector<Task> tasks;std::array<std::vector<int>,16> local;
 int packet_count=0;long long flops=0;int kv_left=0;
 for(int phase=0;phase<2;phase++)for(int block=0;block<phase_bytes[phase]/quantum;block++)for(int tile=0;tile<16;tile++){
  Task t;t.tile=tile;t.phase=phase;t.first=packet_count;t.count=quantum/1024;t.flops=quantum*(phase==0?2:1);
  // One FP16 output row is16KiB. Finer tasks accumulate the same output;
  // partial-sum dependencies cannot be bypassed by the ready-task scheduler.
  if(phase==1&&quantum<16384&&block%(16384/quantum))t.parent=tasks.size()-16;
  local[tile].push_back(tasks.size());tasks.push_back(t);packet_count+=t.count;flops+=t.flops;if(!phase)kv_left++;
 }
 std::vector<Packet> packets(packet_count);std::vector<int> owner(packet_count);
 for(int i=0;i<int(tasks.size());i++)for(int j=0;j<tasks[i].count;j++)owner[tasks[i].first+j]=i;
 auto vec_for=[&](int rid){auto& t=tasks[owner[rid]];
  // Row/bank interleave locally, preserving all weights/KV and no replicas.
  int phase_start=t.phase?int(phase_bytes[0]/quantum)*16:0;
  long long block=(owner[rid]-phase_start)/16;
  long long byte=(t.phase?phase_bytes[0]:0)+block*quantum+(rid-t.first)*1024LL;
  int bank=(byte/4096)%16, rowblock=byte/(4096*16),column=(byte%4096)/1024;
  int row=mapping=="compact"?rowblock:((bank+rowblock)%8)*4096+rowblock/8;
  return Ramulator::AddrVec_t{t.tile,bank/8,0,(bank%8)/2,bank%2,row,column*8};};
 auto* frontend=Ramulator::Factory::create_frontend(cfg);auto* memory=Ramulator::Factory::create_memory_system(cfg);
 frontend->connect_memory_system(memory);memory->connect_frontend(frontend);
 if(memory->get_tx_bytes()!=1024)throw std::runtime_error("Transaction payload differs");
 std::array<size_t,16> admit{},front{};std::array<long long,16> reserved{},high{},busy_until{};
 std::array<int,16> running,last_task;running.fill(-1);last_task.fill(-1);
 std::array<std::deque<int>,16> supply;std::array<std::set<int>,16> returned_tasks;
 std::array<double,16> hb_finish{},compute_finish{};
 using Event=std::pair<long long,int>;std::priority_queue<Event,std::vector<Event>,std::greater<Event>> delivery,done_events;
 std::map<std::string,long long> states;long long accepted=0,returned=0,done=0,clk=0,rejected=0,barrier=-1;
 for(;clk<10000000;clk++){
  while(!done_events.empty()&&done_events.top().first<=clk){auto [time,id]=done_events.top();done_events.pop();auto& t=tasks[id];
   if(t.done)throw std::runtime_error("Duplicate task finish");t.done=true;done++;reserved[t.tile]-=quantum;running[t.tile]=-1;
   if(t.phase==0&&--kv_left==0)barrier=time;
  }
  while(!delivery.empty()&&delivery.top().first<=clk){auto [time,rid]=delivery.top();delivery.pop();auto& t=tasks[owner[rid]];
   if(t.first_return<0)t.first_return=time;t.last_return=time;t.last_request=rid;t.received++;
   if(t.received==t.count)returned_tasks[t.tile].insert(owner[rid]);
  }
  if(done==int(tasks.size()))break;
  for(int tile=0;tile<16;tile++){
   while(admit[tile]<local[tile].size()&&reserved[tile]+quantum<=budget){auto id=local[tile][admit[tile]++];auto& t=tasks[id];
    t.admitted=true;reserved[tile]+=quantum;high[tile]=std::max(high[tile],reserved[tile]);
    for(int rid=t.first;rid<t.first+t.count;rid++)supply[tile].push_back(rid);
   }
   while(front[tile]<local[tile].size()&&tasks[local[tile][front[tile]]].done)front[tile]++;
   if(running[tile]>=0){states["compute_busy"]++;continue;}
   int chosen=-1;
   for(int id:returned_tasks[tile]){auto& t=tasks[id];
    if(ordered&&id!=local[tile][front[tile]])break;
    if((t.parent<0||tasks[t.parent].done)&&(t.phase==0||barrier>=0)){chosen=id;break;}}
   if(chosen>=0){auto& t=tasks[chosen];t.start=clk;t.previous=last_task[tile];
    long long parent_time=t.parent<0?0:tasks[t.parent].finish;
    long long previous_time=t.previous<0?0:tasks[t.previous].finish;
    long long dependency_time=std::max(parent_time,t.phase?barrier:0LL);
    t.cause=t.last_return>=std::max(previous_time,dependency_time)?"critical_input_return":(dependency_time>=previous_time?"dependency":"tile_compute");
    // Fractional compute ledger preserves identical total FLOP service for
    // every task granularity. Round only event time, not each task's service.
    if(t.previous<0||clk>tasks[t.previous].finish)compute_finish[tile]=clk;
    compute_finish[tile]+=double(t.flops)/2000.;
    t.finish=std::ceil(compute_finish[tile]);busy_until[tile]=t.finish;running[tile]=chosen;last_task[tile]=chosen;
    returned_tasks[tile].erase(chosen);done_events.emplace(t.finish,chosen);states["compute_busy"]++;
   }else if(front[tile]==local[tile].size())states["no_remaining_work"]++;
   else{auto& next=tasks[local[tile][front[tile]]];
    if((next.phase&&barrier<0)||(next.parent>=0&&!tasks[next.parent].done))states["dependency_wait"]++;
    else states["missing_critical_data"]++;}
  }
  for(int attempt=0;attempt<16;attempt++){int tile=(clk+attempt)%16;if(supply[tile].empty())continue;
   int rid=supply[tile].front();auto vec=vec_for(rid);
   Ramulator::Request req(vec,Ramulator::Request::Type::Read);req.source_id=tile;req.ingress_id=rid;req.size_bytes=1024;
   req.addr=((static_cast<long long>(vec[5])*256+(vec[1]*8+vec[3]*2+vec[4])*16+tile)*4+vec[6]/8)*1024;
   req.callback=[&,rid,tile](Ramulator::Request& r){if(r.ingress_id!=rid||packets[rid].accepted<0||packets[rid].delivered>=0)throw std::runtime_error("Transaction identity or multiplicity error");
    auto& p=packets[rid];p.depart=r.depart*2;hb_finish[tile]=std::max(double(clk+1),hb_finish[tile])+1024./500.;
    p.delivered=std::ceil(hb_finish[tile]);delivery.emplace(p.delivered,rid);returned++;};
   if(memory->send(req)){packets[rid].accepted=clk;accepted++;supply[tile].pop_front();}else rejected++;
  }
  if(clk%2==1)memory->tick();
 }
 if(done!=int(tasks.size())||accepted!=packet_count||returned!=packet_count||!delivery.empty())throw std::runtime_error("Incomplete task/request execution");
 memory->update_stats_recursive();std::ofstream stats(prefix+"-stats.yaml");memory->print_stats(stats);memory->finalize();frontend->finalize();
 std::ofstream ev(prefix+"-events.csv");ev<<"id,task,tile,phase,address,accepted,depart,delivered,consumed,tier\n";
 for(int rid=0;rid<packet_count;rid++){auto& p=packets[rid];auto& t=tasks[owner[rid]];auto v=vec_for(rid);
  if(p.accepted<0||p.depart<=p.accepted||p.delivered<p.depart||t.start<t.last_return||t.finish<t.start)throw std::runtime_error("Noncausal data consumption");
  long long address=((static_cast<long long>(v[5])*256+(v[1]*8+v[3]*2+v[4])*16+v[0])*4+v[6]/8)*1024;
  ev<<rid<<","<<owner[rid]<<","<<t.tile<<","<<t.phase<<","<<address<<","<<p.accepted<<","<<p.depart<<","<<p.delivered<<","<<t.finish<<","<<v[5]/4096<<"\n";
 }
 std::ofstream tv(prefix+"-tasks.csv");tv<<"id,tile,phase,first,count,parent,flops,first_return,last_return,last_request,start,finish,previous,cause\n";
 for(int id=0;id<int(tasks.size());id++){auto& t=tasks[id];tv<<id<<","<<t.tile<<","<<t.phase<<","<<t.first<<","<<t.count<<","<<t.parent<<","<<t.flops<<","<<t.first_return<<","<<t.last_return<<","<<t.last_request<<","<<t.start<<","<<t.finish<<","<<t.previous<<","<<t.cause<<"\n";}
 std::ofstream report(prefix+"-driver.json");report<<"{\"ticks\":"<<clk<<",\"accepted\":"<<accepted<<",\"returned\":"<<returned<<",\"tasks\":"<<tasks.size()<<",\"completed_tasks\":"<<done<<",\"useful_bytes\":"<<packet_count*1024LL<<",\"useful_flops\":"<<flops<<",\"kv_barrier_tick\":"<<barrier<<",\"task_bytes\":"<<quantum<<",\"buffer_budget_bytes_per_tile\":"<<budget<<",\"buffer_high_water_bytes\":"<<*std::max_element(high.begin(),high.end())<<",\"controller_send_rejects\":"<<rejected<<",\"tile_cycle_partition\":{";
 bool first=true;for(auto [name,value]:states){if(!first)report<<",";first=false;report<<"\""<<name<<"\":"<<value;}report<<"}}\n";
 delete memory;delete frontend;return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
