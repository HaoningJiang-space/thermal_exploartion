// Thin callback/consumer adapter. DRAM state, commands and scheduling belong to
// pinned Ramulator, not to this driver. No power/thermal behavior is invented.
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include "ramulator/base/config.h"
#include "ramulator/base/factory.h"
#include "ramulator/base/request.h"
#include "ramulator/frontend/i_frontend.h"
#include "ramulator/memory_system/i_memory_system.h"

struct Work {
  int id, source, bytes; long long ready, address, flops;
  Ramulator::AddrVec_t vec; std::vector<int> deps;
  long long accepted=-1, completed=-1, depart=-1, consumed=-1, finish=-1;
};

int main(int argc,char** argv) {
 try {
  if(argc!=6)throw std::runtime_error("config.json requests.tsv out-prefix outstanding-limit consumer-FLOP/tile/tick");
  const int limit=std::stoi(argv[4]);const double rate=std::stod(argv[5]);
  if(limit<=0||!std::isfinite(rate)||rate<=0)throw std::runtime_error("invalid integration controls");
  std::ifstream input(argv[2]);std::string line;std::vector<Work> works;
  while(std::getline(input,line)) {
   Work w;std::istringstream s(line);int n;
   if(!(s>>w.id>>w.ready>>w.source>>w.address>>w.bytes>>w.flops))throw std::runtime_error("invalid trace row");
   w.vec.resize(7);for(auto& v:w.vec)if(!(s>>v))throw std::runtime_error("invalid address vector");
   if(!(s>>n)||n<0)throw std::runtime_error("invalid dependency count");
   for(int i=0;i<n;i++){int d;if(!(s>>d)||d<0||d>=w.id)throw std::runtime_error("invalid dependency");w.deps.push_back(d);}
   if(w.id!=int(works.size())||w.source<0||w.source>=16||w.bytes!=32||w.ready<0||w.flops<0)
    throw std::runtime_error("invalid request id/source/size/time/work");
   works.push_back(w);
  }
  if(works.empty())throw std::runtime_error("empty trace");
  auto cfg=Ramulator::Config::parse_config_file(argv[1]);
  auto* frontend=Ramulator::Factory::create_frontend(cfg);
  auto* memory=Ramulator::Factory::create_memory_system(cfg);
  frontend->connect_memory_system(memory);memory->connect_frontend(frontend);
  if(memory->get_tx_bytes()!=32)throw std::runtime_error("unexpected DRAM transaction size");
  std::string prefix(argv[3]);std::ofstream samples(prefix+"-cycles.csv");
  samples<<"clock,outstanding,returned_waiting_consumer,eligible_unissued,state\n";
  std::map<std::string,long long> states;std::vector<long long> tile_finish(16,0);
  long long clk=0,active=0,done=0,accepted=0,returned=0,total_bytes=0,total_flops=0;
  long long queue_sum=0,queue_max=0,consumer_active_ticks=0,rejected=0;
  for(;clk<10000000;clk++) {
   for(auto& w:works)if(w.finish>=0&&w.finish<=clk&&w.consumed<0){w.consumed=w.finish;done++;active--;}
   if(done==int(works.size()))break;
   int eligible=0,sent=0,waiting_consumer=0;bool reject=false;
   for(auto& w:works){
    if(w.completed>=0&&w.consumed<0)waiting_consumer++;
    if(w.accepted>=0||w.ready>clk)continue;
    bool deps=true;for(int d:w.deps)if(works[d].consumed<0){deps=false;break;}
    if(!deps)continue;eligible++;
    if(active>=limit||sent>=16)continue;
    Ramulator::Request req(w.vec,Ramulator::Request::Type::Read);
    req.addr=w.address;req.source_id=w.source;req.size_bytes=w.bytes;
    const int rid=w.id;
    req.callback=[&,rid](Ramulator::Request& r){
      auto& x=works[rid];
      if(x.completed>=0||x.accepted<0)throw std::runtime_error("duplicate or unaccepted completion");
      x.completed=clk+1;x.depart=r.depart;
      if(x.depart>x.completed)throw std::runtime_error("callback precedes response readiness");
      auto duration=static_cast<long long>(std::ceil(x.flops/rate));
      x.finish=std::max(x.completed,tile_finish[x.source])+duration;
      tile_finish[x.source]=x.finish;consumer_active_ticks+=duration;
      returned++;total_bytes+=x.bytes;total_flops+=x.flops;
    };
    if(memory->send(req)){w.accepted=clk;accepted++;active++;sent++;}
    else{reject=true;rejected++;}
   }
   std::string state;
   if(eligible==0 && accepted<int(works.size()))state="dependency_or_release_wait";
   else if(active>=limit && waiting_consumer>0)state="consumer_buffer_backpressure";
   else if(active>=limit)state="inflight_capacity_full";
   else if(reject)state="controller_reject";
   else state="service_or_return_progress";
   states[state]++;queue_sum+=active;queue_max=std::max(queue_max,active);
   samples<<clk<<","<<active<<","<<waiting_consumer<<","<<eligible<<","<<state<<"\n";
   memory->tick();
  }
  if(done!=int(works.size())||accepted!=done||returned!=done||active!=0)
   throw std::runtime_error("trace did not drain exactly once");
  for(const auto& w:works){
    if(w.completed<=w.accepted||w.consumed<w.completed)throw std::runtime_error("noncausal request");
    for(int d:w.deps)if(w.accepted<works[d].consumed)throw std::runtime_error("dependency violated");
  }
  memory->update_stats_recursive();std::ofstream stats(prefix+"-stats.yaml");memory->print_stats(stats);
  memory->finalize();frontend->finalize();
  std::ofstream ev(prefix+"-events.csv");ev<<"id,accepted,completed,depart,consumed,source,address,size,useful_flops\n";
  for(const auto& w:works)ev<<w.id<<","<<w.accepted<<","<<w.completed<<","<<w.depart<<","<<w.consumed<<","<<w.source<<","<<w.address<<","<<w.bytes<<","<<w.flops<<"\n";
  std::ofstream report(prefix+"-driver.json");
  report<<"{\"ticks\":"<<clk<<",\"accepted\":"<<accepted<<",\"returned\":"<<returned
        <<",\"consumed\":"<<done<<",\"useful_bytes\":"<<total_bytes<<",\"useful_flops\":"<<total_flops
        <<",\"outstanding_max\":"<<queue_max<<",\"outstanding_sum\":"<<queue_sum
        <<",\"consumer_active_tile_ticks\":"<<consumer_active_ticks<<",\"controller_send_rejects\":"<<rejected
        <<",\"frontend_cycle_states\":{";
  bool first=true;for(auto [name,value]:states){if(!first)report<<",";first=false;report<<"\""<<name<<"\":"<<value;}
  report<<"}}\n";delete memory;delete frontend;
  return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}
}
