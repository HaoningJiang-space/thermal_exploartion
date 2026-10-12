// Online native memory ONLY. The Python frontend owns all logic/NoC/compute
// state. No recorded completion times enter this process or its caller.
#define main legacy_trace_main
#include "ramulator_trace_driver.cpp"
#undef main
int main(int argc,char** argv){try{
 if(argc!=3)throw std::runtime_error("config.json output-prefix");
 auto cfg=Ramulator::Config::parse_config_file(argv[1]);auto* frontend=Ramulator::Factory::create_frontend(cfg);auto* memory=Ramulator::Factory::create_memory_system(cfg);frontend->connect_memory_system(memory);memory->connect_frontend(frontend);
 if(memory->get_tx_bytes()!=1024)throw std::runtime_error("Changed transaction width");
 long long clock=0;std::vector<std::pair<int,long long>> returned;std::set<int> accepted,completed;std::string line;
 while(std::getline(std::cin,line)){
  std::istringstream input(line);char command;input>>command;
  if(command=='S'){
   int id,tile;long long address;input>>id>>address>>tile;
   if(address<0||address%1024||tile<0||tile>=16||accepted.count(id))throw std::runtime_error("Invalid online request");
   auto txn=address/1024;int column=txn%4,bank=(txn/4)%256,row=txn/1024,ch=bank%16,local=bank/16;
   if(ch!=tile)throw std::runtime_error("Remote DRAM ownership changed");
   Ramulator::AddrVec_t vec={ch,local/8,0,(local%8)/2,local%2,row,column*8};Ramulator::Request req(vec,Ramulator::Request::Type::Read);req.addr=address;req.source_id=tile;req.size_bytes=1024;req.ingress_id=id;
   req.callback=[&,id](Ramulator::Request& r){if(r.ingress_id!=id||!accepted.count(id)||completed.count(id))throw std::runtime_error("Online response identity");completed.insert(id);returned.emplace_back(id,r.depart);};
   bool ok=memory->send(req);if(ok)accepted.insert(id);std::cout<<"@S "<<int(ok)<<"\n"<<std::flush;
  }else if(command=='T'){
   long long requested;input>>requested;if(requested!=clock)throw std::runtime_error("Online clock drift");memory->tick();std::cout<<"@T "<<returned.size();for(auto [id,time]:returned)std::cout<<" "<<id<<" "<<time;std::cout<<"\n"<<std::flush;returned.clear();clock++;
  }else if(command=='Q'){
   if(accepted!=completed||!returned.empty())throw std::runtime_error("Undrained online native memory");memory->update_stats_recursive();std::ofstream stats(std::string(argv[2])+"-stats.yaml");memory->print_stats(stats);memory->finalize();frontend->finalize();std::cout<<"@Q "<<clock<<"\n"<<std::flush;delete memory;delete frontend;return 0;
  }else throw std::runtime_error("Invalid online memory protocol");
 }
 throw std::runtime_error("Truncated online memory protocol");
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
