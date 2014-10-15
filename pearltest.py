from suds.client import Client
url = "http://192.168.1.43:8080?wsdl"
client = Client(url)
print client
vrp=client.factory.create('ns1:creatVirtualRouterParam')
vrp.name='vm_slice9'
vrp.memory=1024*1024
vrp.currentMemory=512*1024
vrp.vcpu=1
vrp.ip='192.168.122.253'  #130-254
vrp.mac='24:3f:d0:39:52:02' #*:52:xx
vrp.disksize=2
###########create virtual machine############
#parms: creatVirtualRouterParam
res1=client.service.creatVirtualMachine(vrp)
print "the result of creat virtual machine:\n"+str(res1)
res2=client.service.getVirtualMachinesInfo()
print res2
res3=client.service.startVirtualMachine(vrp.name)
print "the result of start virtual machine:\n"+str(res3)

###########assign virtual router#############
pkfile=open("/home/pearl2/huang/ningjing.key.pub")
pklines=pkfile.readlines()
pkstr=""
for i in pklines:
    pkstr+=i
vrname='vr_slice9'
res4=client.service.assignVirtualRouter(vrname,vrp.name,pkstr)
print "the result of assign virtual router:\n"+str(res4)

############start virtual router###############
sysfile=open("/home/pearl2/huang/sys.xml")
syslines=sysfile.readlines()
sysstr=""
for i in syslines:
    sysstr+=i
# start virtual router
# params: vroutername,vmname,dpid,vlanid,sysdefxml
dpid=1
vlanid=4000
res5=client.service.startVirtualRouter(vrname,vrp.name,dpid,vlanid,sysstr)
print "the result of start virturl router:\n"+str(res5)
res6=client.service.getVirtualMachinesInfo()
print res6

##############stop virtual router############
res7=client.service.stopVirtualRouter(vrname,vrp.name)
print "the result of stop virtual router:\n"+str(res7)

##############stop virtual machine###########
res8=client.service.stopVirtualMachine(vrp.name)
print "the result of stop virtual machine:\n"+str(res8)
##############destroy Virtual Machine########
dvrp=client.factory.create('ns1:destroyVirtualRouterParam')
dvrp.name=vrp.name
dvrp.ip=vrp.ip
dvrp.mac=vrp.mac
res9=client.service.destroyVirtualMachine(dvrp)
print "the result of destroy virtual machine:\n"+str(res9)
