// Thin callback/consumer adapter. DRAM state, commands and scheduling belong to
// pinned Ramulator, not to this driver. No power/thermal behavior is invented.
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <map>
#include <queue>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "ramulator/base/config.h"
#include "ramulator/base/factory.h"
#include "ramulator/base/request.h"
#include "ramulator/base/param.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/i_memory_system.h"
#include "ramulator/controller/controller_base.h"
#include "ramulator/controller/plugin/i_controller_plugin.h"
#include "tier_timing_plugin.h"

namespace Ramulator {
// External's default core count is one; controller per-source arrays must have
// the same size as our 16 consumers. DRAM logic stays entirely upstream.
class TraceConsumerFrontEnd : public IFrontEnd, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IFrontEnd,TraceConsumerFrontEnd,"TraceConsumer")
 public:
  void init() override {RAMULATOR_PARSE_PARAM(m_clock_ratio,unsigned int,"clock_ratio").required();}
  void tick() override {}
  bool is_finished() override {return false;}
  int get_num_cores() override {return 16;}
};

class TransactionTrace : public IControllerPlugin, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin,TransactionTrace,"TransactionTrace")
  std::string path; std::ofstream output; ControllerBase* ctrl=nullptr;
 public:
  void init() override {RAMULATOR_PARSE_PARAM(path,std::string,"path").required();}
  void setup(IFrontEnd*,IMemorySystem*) override {
    ctrl=cast_parent<ControllerBase>();output.open(path);
    output<<"clock,command,transaction_id,source";
    for(const auto& name:ctrl->m_device.m_spec->level_names)output<<","<<name;
    output<<"\n";
  }
  void on_issue(const Request& req) override {
    output<<ctrl->m_clk<<","<<ctrl->m_device.m_spec->command_names[req.command]<<","<<req.ingress_id<<","<<req.source_id;
    for(auto v:req.addr_vec)output<<","<<v;
    output<<"\n";
  }
  void finalize() override {output.close();}
};
}

struct Work {
  int id, source, bytes; long long ready, address, flops;
  Ramulator::AddrVec_t vec; std::vector<int> deps;
  long long accepted=-1, completed=-1, depart=-1, consumed=-1, finish=-1;
};

int main(int argc,char** argv) {
 try {
  if(argc!=6 && argc!=8 && argc!=9)throw std::runtime_error("config.json requests.tsv out-prefix outstanding-limit consumer-FLOP/tile/tick [HB-bytes/channel/tick terminal-idle-ticks [logic-ticks-per-DRAM-tick]]");
  const int limit=std::stoi(argv[4]);const double rate=std::stod(argv[5]);
  if(limit<=0||!std::isfinite(rate)||rate<=0)throw std::runtime_error("invalid integration controls");
  const double hb_rate=argc>=8?std::stod(argv[6]):0;
  const long long idle=argc>=8?std::stoll(argv[7]):0;
  const int dram_ratio=argc==9?std::stoi(argv[8]):1;
  if(dram_ratio<1)throw std::runtime_error("Invalid clock-domain ratio");
  if(hb_rate<0||idle<0)throw std::runtime_error("invalid HB or idle budget");
  std::ifstream input(argv[2]);std::string line;std::vector<Work> works;
  while(std::getline(input,line)) {
   Work w;std::istringstream s(line);int n;
   if(!(s>>w.id>>w.ready>>w.source>>w.address>>w.bytes>>w.flops))throw std::runtime_error("invalid trace row");
   w.vec.resize(7);for(auto& v:w.vec)if(!(s>>v))throw std::runtime_error("invalid address vector");
   if(!(s>>n)||n<0)throw std::runtime_error("invalid dependency count");
   for(int i=0;i<n;i++){int d;if(!(s>>d)||d<0||d>=w.id)throw std::runtime_error("invalid dependency");w.deps.push_back(d);}
   if(w.id!=int(works.size())||w.source<0||w.source>=16||w.bytes<=0||w.ready<0||w.flops<0)
    throw std::runtime_error("invalid request id/source/size/time/work");
   works.push_back(w);
  }
  if(works.empty())throw std::runtime_error("empty trace");
  auto cfg=Ramulator::Config::parse_config_file(argv[1]);
  auto* frontend=Ramulator::Factory::create_frontend(cfg);
  auto* memory=Ramulator::Factory::create_memory_system(cfg);
  frontend->connect_memory_system(memory);memory->connect_frontend(frontend);
  for(const auto& w:works)if(w.bytes>memory->get_tx_bytes())throw std::runtime_error("request exceeds DRAM transaction size");
  std::string prefix(argv[3]);std::ofstream samples(prefix+"-cycles.csv");
  samples<<"clock,outstanding,returned_waiting_consumer,eligible_examined,state\n";
  std::map<std::string,long long> states;std::vector<long long> tile_finish(16,0);
  std::vector<int> tile_outstanding(16,0);
  std::vector<double> hb_finish(16,0);
  std::set<int> returned_waiting;
  std::vector<std::set<int>> ready_by_channel(16);
  std::vector<int> unresolved(works.size(),0);
  std::vector<std::vector<int>> dependents(works.size());
  using Completion=std::pair<long long,int>;
  std::priority_queue<Completion,std::vector<Completion>,std::greater<Completion>> completions;
  std::priority_queue<Completion,std::vector<Completion>,std::greater<Completion>> releases;
  for(const auto& w:works){
    unresolved[w.id]=w.deps.size();
    for(int d:w.deps)dependents[d].push_back(w.id);
    if(w.deps.empty())releases.emplace(w.ready,w.id);
  }
  long long clk=0,active=0,done=0,accepted=0,returned=0,total_bytes=0,total_flops=0;
  long long queue_sum=0,queue_max=0,consumer_active_ticks=0,rejected=0;
  for(;clk<10000000;clk++) {
   while(!completions.empty()&&completions.top().first<=clk){
    auto [time,id]=completions.top();completions.pop();auto& w=works[id];
    if(w.consumed>=0)throw std::runtime_error("duplicate consumption");
    w.consumed=time;done++;active--;tile_outstanding[w.source]--;returned_waiting.erase(id);
    for(int successor:dependents[id])if(--unresolved[successor]==0)
      releases.emplace(std::max(works[successor].ready,clk),successor);
   }
   if(done==int(works.size()))break;
   while(!releases.empty()&&releases.top().first<=clk){
    auto [time,id]=releases.top();releases.pop();ready_by_channel[works[id].vec[0]].insert(id);
   }
   int eligible=0,sent=0,waiting_consumer=returned_waiting.size();bool reject=false;
   // One candidate per channel per round, rotating the first channel each
   // tick. A rejected channel is retried next tick rather than scanning all
   // future requests. Dependency completion releases identities exactly once.
   bool blocked[16]={};
   for(int attempt=0;attempt<256&&active<limit&&sent<16;attempt++){
    int channel=(clk+attempt)%16;
    if(blocked[channel]||ready_by_channel[channel].empty())continue;
    auto& w=works[*ready_by_channel[channel].begin()];eligible++;
    if(hb_rate>0&&tile_outstanding[w.source]>=limit/16){blocked[channel]=true;continue;}
    Ramulator::Request req(w.vec,Ramulator::Request::Type::Read);
    req.addr=w.address;req.source_id=w.source;req.size_bytes=w.bytes;req.ingress_id=w.id;
    const int rid=w.id;
    req.callback=[&,rid](Ramulator::Request& r){
      auto& x=works[rid];
      if(r.ingress_id!=rid)throw std::runtime_error("transaction identity changed in controller");
      if(x.completed>=0||x.accepted<0)throw std::runtime_error("duplicate or unaccepted completion");
      x.completed=clk+1;x.depart=r.depart*dram_ratio;
      if(x.depart>x.completed)throw std::runtime_error("callback precedes response readiness");
      if(hb_rate>0){
        int channel=x.vec[0];hb_finish[channel]=std::max(double(x.completed),hb_finish[channel])+x.bytes/hb_rate;
        x.completed=static_cast<long long>(std::ceil(hb_finish[channel]));
      }
      auto duration=static_cast<long long>(std::ceil(x.flops/rate));
      x.finish=std::max(x.completed,tile_finish[x.source])+duration;
      tile_finish[x.source]=x.finish;consumer_active_ticks+=duration;
      completions.emplace(x.finish,rid);returned_waiting.insert(rid);
      returned++;total_bytes+=x.bytes;total_flops+=x.flops;
    };
    if(memory->send(req)){w.accepted=clk;accepted++;active++;tile_outstanding[w.source]++;sent++;ready_by_channel[channel].erase(w.id);}
    else{reject=true;rejected++;blocked[channel]=true;}
   }
   std::string state;
   if(active>=limit && waiting_consumer>0)state="consumer_or_HB_buffer_backpressure";
   else if(active>=limit)state="inflight_capacity_full";
   else if(eligible==0 && accepted<int(works.size()))state="dependency_or_release_wait";
   else if(reject)state="controller_reject";
   else state="service_or_return_progress";
   states[state]++;queue_sum+=active;queue_max=std::max(queue_max,active);
   samples<<clk<<","<<active<<","<<waiting_consumer<<","<<eligible<<","<<state<<"\n";
   if(clk%dram_ratio==dram_ratio-1)memory->tick();
  }
  if(done!=int(works.size())||accepted!=done||returned!=done||active!=0)
   throw std::runtime_error("trace did not drain exactly once");
  for(const auto& w:works){
    if(w.completed<=w.accepted||w.consumed<w.completed)throw std::runtime_error("noncausal request");
    for(int d:w.deps)if(w.accepted<works[d].consumed)throw std::runtime_error("dependency violated");
  }
  const auto execution_ticks=clk;
  for(long long i=0;i<idle;i++)if((execution_ticks+i)%dram_ratio==dram_ratio-1)memory->tick();
  memory->update_stats_recursive();std::ofstream stats(prefix+"-stats.yaml");memory->print_stats(stats);
  memory->finalize();frontend->finalize();
  std::ofstream ev(prefix+"-events.csv");ev<<"id,accepted,completed,depart,consumed,source,address,size,useful_flops\n";
  for(const auto& w:works)ev<<w.id<<","<<w.accepted<<","<<w.completed<<","<<w.depart<<","<<w.consumed<<","<<w.source<<","<<w.address<<","<<w.bytes<<","<<w.flops<<"\n";
  std::ofstream report(prefix+"-driver.json");
  report<<"{\"ticks\":"<<execution_ticks<<",\"terminal_idle_ticks\":"<<idle<<",\"accepted\":"<<accepted<<",\"returned\":"<<returned
        <<",\"consumed\":"<<done<<",\"useful_bytes\":"<<total_bytes<<",\"useful_flops\":"<<total_flops
        <<",\"outstanding_max\":"<<queue_max<<",\"outstanding_sum\":"<<queue_sum
        <<",\"consumer_active_tile_ticks\":"<<consumer_active_ticks<<",\"controller_send_rejects\":"<<rejected
        <<",\"frontend_cycle_states\":{";
  bool first=true;for(auto [name,value]:states){if(!first)report<<",";first=false;report<<"\""<<name<<"\":"<<value;}
  report<<"}}\n";delete memory;delete frontend;
  return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
}
