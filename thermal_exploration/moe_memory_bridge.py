"""Live pinned Ramulator device model, not an offline timing replay."""
import subprocess
from pathlib import Path

class NativeMemory:
 def __init__(self,exe,config,prefix):
  self.log=Path(str(prefix)+'-bridge.log').open('w');self.process=subprocess.Popen([str(exe),str(config),str(prefix)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,text=True,bufsize=1);self.accepted=set();self.returned=set();self.closed=False
 def command(self,value,tag):
  self.process.stdin.write(value+'\n');self.process.stdin.flush()
  while True:
   line=self.process.stdout.readline()
   if not line:raise ValueError('Online native memory process terminated')
   if line.startswith('@'+tag+' '):return [int(v) for v in line.split()[1:]]
   self.log.write(line)
 def send(self,id,address,tile):
  result=self.command(f'S {id} {address} {tile}','S')
  if result==[1]:
   if id in self.accepted:raise ValueError('Repeated online request')
   self.accepted.add(id);return True
  if result!=[0]:raise ValueError('Invalid native admission response')
  return False
 def tick(self,clock):
  reply=self.command(f'T {clock}','T');count=reply[0]
  if len(reply)!=1+2*count:raise ValueError('Invalid online completion response')
  result=[]
  for i in range(count):
   id,time=reply[1+2*i:3+2*i]
   if id not in self.accepted or id in self.returned:raise ValueError('Online completion identity mismatch')
   self.returned.add(id);result.append((id,time))
  return result
 def close(self):
  if self.closed:return
  self.command('Q','Q');self.process.stdin.close();self.process.stdout.close();status=self.process.wait();self.log.close();self.closed=True
  if status or self.accepted!=self.returned:raise ValueError('Undrained online native memory')
 def abort(self):
  if not self.closed:
   self.process.terminate();self.process.wait();self.log.close();self.closed=True
