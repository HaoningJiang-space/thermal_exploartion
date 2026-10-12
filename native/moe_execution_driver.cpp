// Full captured-MoE causal frontend around pinned Ramulator. Program contains
// work and dependencies, no measured arrival times or joint-kernel durations.
#define main legacy_trace_main
#include "ramulator_trace_driver.cpp"
#undef main
#include <array>
#include <iomanip>
struct Op {int id,kind,tile,rid,tier,context,phase,master,target,vc;long long work,ticks,address,read,fifo,start=-1,finish=-1,left;int state=0,remain;std::vector<int> deps,children;};
struct Lease {int first,last,rid,tile;long long bytes;};
struct Credit {int first,tile,port,vc,left;bool reserved=false;std::vector<int> users;};
int main(int argc,char** argv){try {
 if(argc!=5)throw std::runtime_error("config.json program-directory output-prefix native|fluid");
 std::string dir=argv[2],prefix=argv[3],backend=argv[4];bool fluid=backend=="fluid";
 if(!fluid&&backend!="native")throw std::runtime_error("Invalid memory backend");
 std::vector<Op> nodes;std::array<std::array<std::set<int>,16>,9> ready;
 {std::ifstream f(dir+"/nodes.tsv");std::string line;while(std::getline(f,line)){Op n;int count;std::istringstream s(line);
  if(!(s>>n.id>>n.kind>>n.tile>>n.work>>n.ticks>>n.rid>>n.tier>>n.address>>n.context>>n.phase>>n.master>>n.read>>n.fifo>>n.target>>n.vc>>count))throw std::runtime_error("Invalid operation");
  if(n.id!=int(nodes.size())||n.tile<0||n.tile>=16||n.kind<0||n.kind>=9)throw std::runtime_error("Operation identity");
  for(int j=0;j<count;j++){int d;s>>d;if(d<0||d>=n.id)throw std::runtime_error("Noncausal operation");n.deps.push_back(d);}n.remain=count;n.left=n.work;nodes.push_back(n);
 }}
 std::vector<std::vector<Lease>> leases(nodes.size()),releases(nodes.size());std::vector<Lease> all_leases;
 {std::ifstream f(dir+"/leases.tsv");Lease l;while(f>>l.first>>l.last>>l.rid>>l.tile>>l.bytes){leases[l.first].push_back(l);releases[l.last].push_back(l);all_leases.push_back(l);}}
 std::vector<Credit> credits;std::vector<std::vector<int>> credit_for(nodes.size()),credit_users(nodes.size());
 {std::ifstream f(dir+"/router.tsv");Credit c;int count;while(f>>c.first>>c.tile>>c.port>>c.vc>>count){c.users.clear();for(int j=0;j<count;j++){int i;f>>i;c.users.push_back(i);}c.left=count;c.reserved=false;int id=credits.size();credits.push_back(c);credit_for[c.first].push_back(id);for(int i:c.users)credit_users[i].push_back(id);}}
 std::vector<std::array<int,3>> contexts;{std::ifstream f(dir+"/contexts.tsv");std::array<int,3> a;while(f>>a[0]>>a[1]>>a[2])contexts.push_back(a);}
 int resources;long long private_budget;std::array<long long,16> fixed;
 std::map<int,long long> caps;{std::ifstream f(dir+"/resources.tsv");f>>resources>>private_budget;for(auto& v:fixed)f>>v;int key;long long value;while(f>>key>>value)caps[key]=value;}
 std::vector<long long> busy(resources,0),used(resources,0);std::array<long long,16> private_used{},private_high{},mac_until{},mac_read{},mac_fifo{},mac_flops{};
 std::array<int,16> mac,vector;mac.fill(-1);vector.fill(-1);std::array<double,16> memory_until{};
 std::array<std::array<std::array<int,2>,5>,16> router_used{};int router_high=0;
 std::vector<std::vector<int>> slaves(nodes.size());for(auto& n:nodes)if(n.master>=0)slaves[n.master].push_back(n.id);
 std::priority_queue<std::pair<long long,int>,std::vector<std::pair<long long,int>>,std::greater<std::pair<long long,int>>> events;
 std::set<int> joins;long long clock=0,completed=0;std::map<std::string,long long> activity,wait;
 std::ofstream nodeout(prefix+"-nodes.csv"),portout(prefix+"-ports.csv"),leaseout(prefix+"-leases.csv"),routerout(prefix+"-router.csv"),requestout(prefix+"-requests.csv"),serviceout(prefix+"-service.csv");
 nodeout<<"id,start,finish\n";portout<<"tick,tile,read,write,vector,hb,fifo\n";leaseout<<"tick,resource,tile,delta\n";routerout<<"tick,tile,port,vc,delta,credit\n";requestout<<"id,accepted,depart,address\n";serviceout<<"tick,id,kind,amount\n";
 auto enqueue=[&](int i){auto& n=nodes[i];if(n.master>=0)return;if(n.kind==0)joins.insert(i);else ready[n.kind][n.tile].insert(i);};
 for(auto& n:nodes){for(int d:n.deps)nodes[d].children.push_back(n.id);if(n.deps.empty())enqueue(n.id);}
 auto finish=[&](int i,long long time){auto& n=nodes[i];if(n.state==3)throw std::runtime_error("Duplicate completion");n.state=3;n.finish=time;completed++;nodeout<<i<<","<<n.start<<","<<time<<"\n";if(n.kind==4)activity["mac"]+=n.work;
  for(auto& l:releases[i]){used[l.rid]-=l.bytes;private_used[l.tile]-=l.bytes;leaseout<<time<<","<<l.rid<<","<<l.tile<<","<<-l.bytes<<"\n";if(used[l.rid]<0)throw std::runtime_error("Unbalanced private lease");}
  for(int child:n.children)if(--nodes[child].remain==0)enqueue(child);
 };
 auto admissible=[&](int i){std::map<int,long long> need;std::array<long long,16> bytile{};
  for(auto& l:leases[i]){need[l.rid]+=l.bytes;bytile[l.tile]+=l.bytes;}
  for(auto [key,value]:need)if(used[key]+value>caps.at(key)){wait["byte_credit"]++;return false;}
  for(int t=0;t<16;t++)if(private_used[t]+fixed[t]+bytile[t]>private_budget){wait["private_credit"]++;return false;}
  for(int ri:credit_for[i]){auto& c=credits[ri];if(router_used[c.tile][c.port][c.vc]>=8){wait["router_credit"]++;return false;}}
  return true;
 };
 auto begin=[&](int i){auto& n=nodes[i];if(n.state)return;n.state=1;n.start=clock;ready[n.kind][n.tile].erase(i);
  for(auto& l:leases[i]){used[l.rid]+=l.bytes;private_used[l.tile]+=l.bytes;private_high[l.tile]=std::max(private_high[l.tile],private_used[l.tile]+fixed[l.tile]);leaseout<<clock<<","<<l.rid<<","<<l.tile<<","<<l.bytes<<"\n";}
  for(int ri:credit_for[i]){auto& c=credits[ri];auto& u=router_used[c.tile][c.port][c.vc];u++;router_high=std::max(router_high,u);c.reserved=true;routerout<<clock<<","<<c.tile<<","<<c.port<<","<<c.vc<<",1,"<<ri<<"\n";}
  for(int ri:credit_users[i]){auto& c=credits[ri];if(!c.reserved)throw std::runtime_error("Consumer without reserved flit");if(--c.left==0){router_used[c.tile][c.port][c.vc]--;routerout<<clock<<","<<c.tile<<","<<c.port<<","<<c.vc<<",-1,"<<ri<<"\n";}}
 };
 auto schedule=[&](int i,long long time){nodes[i].state=2;events.emplace(time,i);};
 auto cfg=Ramulator::Config::parse_config_file(argv[1]);auto* frontend=Ramulator::Factory::create_frontend(cfg);auto* memory=Ramulator::Factory::create_memory_system(cfg);frontend->connect_memory_system(memory);memory->connect_frontend(frontend);
 if(memory->get_tx_bytes()!=1024)throw std::runtime_error("Changed native transaction width");
 const double rcd[8]={2.29,3.92,5.99,8.50,11.44,14.82,18.63,22.88};
 for(;clock<2000000;clock++){
  while(!events.empty()&&events.top().first<=clock){auto [time,i]=events.top();events.pop();auto& n=nodes[i];finish(i,time);
   if(n.kind==4){for(int j:slaves[i]){nodes[j].start=n.start;nodes[j].state=2;finish(j,time);}mac[n.tile]=-1;}
   if(n.context>=0&&n.phase==2)vector[n.tile]=-1;
  }
  std::vector<int> deferred;
  while(!joins.empty()){int i=*joins.begin();joins.erase(i);if(!admissible(i)){deferred.push_back(i);continue;}begin(i);finish(i,clock);}
  for(int i:deferred)joins.insert(i);
  if(completed==int(nodes.size()))break;
  std::array<int,16> rb,wb,vb,hb,fr{};rb.fill(256);wb.fill(128);vb.fill(16);hb.fill(500);
  for(int tile=0;tile<16;tile++){
   if(mac[tile]<0){for(int i:ready[4][tile])if(admissible(i)){auto& n=nodes[i];begin(i);mac[tile]=i;mac_until[tile]=clock+n.ticks;mac_read[tile]=n.read;mac_fifo[tile]=n.fifo;mac_flops[tile]=n.work;schedule(i,mac_until[tile]);break;}}
   if(mac[tile]>=0){long long left=mac_until[tile]-clock;int read=(mac_read[tile]+left-1)/left,fifo=(mac_fifo[tile]+left-1)/left;long long fma=(mac_flops[tile]+left-1)/left;mac_flops[tile]-=fma;serviceout<<clock<<","<<mac[tile]<<",4,"<<fma<<"\n";for(int sid:slaves[mac[tile]])serviceout<<clock<<","<<sid<<","<<nodes[sid].kind<<","<<(nodes[sid].kind==1?read:fifo)<<"\n";mac_read[tile]-=read;mac_fifo[tile]-=fifo;rb[tile]-=read;fr[tile]=fifo;activity["sram_read"]+=read;activity["fifo_read"]+=fifo;if(rb[tile]<0||fifo>500)throw std::runtime_error("MAC port overrun");}
   if(vector[tile]<0){for(int i:ready[1][tile]){auto& n=nodes[i];if(n.context>=0&&n.phase==0&&admissible(i)){vector[tile]=n.context;break;}}}
   if(vector[tile]>=0){for(int i:contexts[vector[tile]]){auto& n=nodes[i];if(n.finish>=0)continue;if(n.state==2||n.remain)break;if(!n.state){if(!admissible(i))break;begin(i);}if(!n.left){finish(i,clock);if(n.phase==2)vector[tile]=-1;continue;}int& budget=n.kind==1?rb[tile]:n.kind==2?wb[tile]:vb[tile];int take=std::min<long long>(n.left,budget);n.left-=take;budget-=take;serviceout<<clock<<","<<i<<","<<n.kind<<","<<take<<"\n";activity[n.kind==1?"sram_read":n.kind==2?"sram_write":"vector"]+=take;if(!n.left)schedule(i,clock+1);break;}}
   for(int kind:{2,1,6}){int& budget=kind==2?wb[tile]:kind==1?rb[tile]:hb[tile];std::vector<int> candidates(ready[kind][tile].begin(),ready[kind][tile].end());for(int i:candidates){auto& n=nodes[i];if(n.context>=0)continue;if(budget<=0)break;if(!n.state){if(!admissible(i))continue;begin(i);ready[kind][tile].insert(i);}int take=std::min<long long>(n.left,budget);n.left-=take;budget-=take;serviceout<<clock<<","<<i<<","<<kind<<","<<take<<"\n";activity[kind==6?"hb":kind==2?"sram_write":"sram_read"]+=take;if(!n.left){ready[kind][tile].erase(i);schedule(i,clock+1);}}}
   std::vector<int> links(ready[5][tile].begin(),ready[5][tile].end());for(int i:links){auto& n=nodes[i];if(busy[n.rid]>clock){wait["link_serial"]++;continue;}if(!admissible(i))continue;begin(i);busy[n.rid]=clock+4;schedule(i,clock+8);activity["link"]+=32;}
   if(!ready[7][tile].empty()){int i=*ready[7][tile].begin();auto& n=nodes[i];if(admissible(i)){
    auto txn=n.address/1024;int column=txn%4,bank=(txn/4)%256,row=txn/1024,ch=bank%16,local=bank/16;
    Ramulator::AddrVec_t vec={ch,local/8,0,(local%8)/2,local%2,row,column*8};Ramulator::Request req(vec,Ramulator::Request::Type::Read);req.addr=n.address;req.source_id=tile;req.size_bytes=1024;req.ingress_id=i;
    req.callback=[&,i](Ramulator::Request& r){if(nodes[i].state!=2||r.ingress_id!=i)throw std::runtime_error("Native response identity");schedule(i,r.depart);requestout<<i<<","<<nodes[i].start<<","<<r.depart<<","<<nodes[i].address<<"\n";};
    if(fluid||memory->send(req)){begin(i);n.state=2;activity["dram"]+=n.work;if(fluid){double rate=std::min(26.599/16*1000*.25,16*4096/std::ceil((rcd[n.tier]+27.5+4.77)/.25));memory_until[tile]=std::max(double(clock),memory_until[tile])+n.work/rate;long long depart=std::ceil(memory_until[tile])+std::ceil((rcd[n.tier]+4)/.25);schedule(i,depart);requestout<<i<<","<<clock<<","<<depart<<","<<n.address<<"\n";}}
    else wait["native_controller_reject"]++;
   }}
   portout<<clock<<","<<tile<<","<<256-rb[tile]<<","<<128-wb[tile]<<","<<16-vb[tile]<<","<<500-hb[tile]<<","<<fr[tile]<<"\n";
  }
  memory->tick();
 }
 if(completed!=int(nodes.size()))throw std::runtime_error("Full MoE failed to drain");
 for(auto [key,cap]:caps)if(used[key])throw std::runtime_error("Leaked private bytes");for(auto& c:credits)if(c.left||!c.reserved)throw std::runtime_error("Leaked flit credit");
 for(auto& n:nodes){for(int d:n.deps)if(n.start<nodes[d].finish)throw std::runtime_error("Early operand consumption");}
 memory->update_stats_recursive();std::ofstream stats(prefix+"-stats.yaml");memory->print_stats(stats);memory->finalize();frontend->finalize();
 std::ofstream out(prefix+"-driver.json");out<<"{\"ticks\":"<<clock<<",\"nodes\":"<<nodes.size()<<",\"private_peak\":"<<*std::max_element(private_high.begin(),private_high.end())<<",\"router_peak\":"<<router_high<<",\"activity\":{";
 bool first=true;for(auto [k,v]:activity){if(!first)out<<",";first=false;out<<"\""<<k<<"\":"<<v;}out<<"},\"wait\":{";first=true;for(auto [k,v]:wait){if(!first)out<<",";first=false;out<<"\""<<k<<"\":"<<v;}out<<"}}\n";
 delete memory;delete frontend;return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}}
