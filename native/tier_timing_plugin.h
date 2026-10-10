#pragma once
// Conservative deadline extension for row-addressed timing tiers. It never
// introduces additional banks or independent subarray state, and never
// shortens the underlying model's deadlines. No temperature feedback curve.
namespace Ramulator {
class TierTiming : public IControllerPlugin, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IControllerPlugin,TierTiming,"TierTiming")
  ControllerBase* ctrl=nullptr;
  int rows_per_tier=4096;
  std::vector<int> rcd,ras,rc;
  std::string path;std::ofstream output;
 public:
  void init() override {
    RAMULATOR_PARSE_PARAM(rows_per_tier,int,"rows_per_tier").required();
    RAMULATOR_PARSE_PARAM(rcd,std::vector<int>,"rcd_ticks").required();
    RAMULATOR_PARSE_PARAM(ras,std::vector<int>,"ras_ticks").required();
    RAMULATOR_PARSE_PARAM(rc,std::vector<int>,"rc_ticks").required();
    RAMULATOR_PARSE_PARAM(path,std::string,"path").required();
    if(rows_per_tier<=0||rcd.size()!=8||ras.size()!=8||rc.size()!=8)throw std::runtime_error("invalid timing tiers");
  }
  void setup(IFrontEnd*,IMemorySystem*) override {
    ctrl=cast_parent<ControllerBase>();
    if(ctrl->m_device.m_spec->get_level_size("Sid")!=1)throw std::runtime_error("Timing tiers must share the same physical bank state");
    output.open(path);output<<"clock,transaction_id,channel,pc,bg,bank,row,tier,rcd_ticks,ras_ticks,rc_ticks\n";
    auto& s=*ctrl->m_device.m_spec;
    for(int i=0;i<8;i++)if(rcd[i]<s.get_timing_value("nRCDRD")||ras[i]<s.get_timing_value("nRAS")||rc[i]<s.get_timing_value("nRC"))
      throw std::runtime_error("Tier plugin cannot reduce base deadlines");
  }
  void on_issue(const Request& req) override {
    auto& d=ctrl->m_device;auto& s=*d.m_spec;
    if(req.command!=s.get_command_id("ACT"))return;
    int row=req.addr_vec[s.get_level_id("Row")];int tier=row/rows_per_tier;
    if(tier<0||tier>=8)throw std::runtime_error("Row outside timing-tier capacity");
    auto* bank=d.m_bank_nodes[d.get_flat_bank_id(req.addr_vec)];
    auto extend=[&](const std::string& name,int delay){if(s.has_command(name)){
      auto id=s.get_command_id(name);
      // Like upstream codegen: timings are between command-receipt endings;
      // traces timestamp their beginnings. Use serialized command durations
      // (HBM3 ACT1.5CK, RD1CK, PRE0.5CK), not a guessed whole-CK framing.
      int offset=s.command_cycles[req.command]-s.command_cycles[id];
      bank->m_cmd_ready_clk[id]=std::max(bank->m_cmd_ready_clk[id],ctrl->m_clk+delay+offset);}};
    for(auto name:{"RD","RDA","WR","WRA"})extend(name,rcd[tier]);
    for(auto name:{"PREpb","PREab"})extend(name,ras[tier]);
    for(auto name:{"ACT","REFab","REFpb"})extend(name,rc[tier]);
    output<<ctrl->m_clk<<","<<req.ingress_id<<","<<req.addr_vec[0]<<","<<req.addr_vec[1]<<","<<req.addr_vec[3]<<","<<req.addr_vec[4]
          <<","<<row<<","<<tier<<","<<rcd[tier]<<","<<ras[tier]<<","<<rc[tier]<<"\n";
  }
  void finalize() override {output.close();}
};
}
