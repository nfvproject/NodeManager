#
# Thierry Parmentelat - INRIA
import os
import sys
#
from PLC.Faults import *
from PLC.Parameter import Parameter
from PLC.Filter import Filter
from PLC.Table import Row, Table
# seems to cause import loops
#from PLC.Slices import Slice, Slices
from PLC.Nodes import Node, Nodes
from PLC.NodeGroups import NodeGroup, NodeGroups
from PLC.TagTypes import TagType, TagTypes
#wangyang
import pickle
import logger

class SliceTag(Row):
    """
    Representation of a row in the slice_tag table. To use,
    instantiate with a dict of values.
    """

    table_name = 'slice_tag'
    primary_key = 'slice_tag_id'
    fields = {
        'slice_tag_id': Parameter(int, "Slice tag identifier"),
        'slice_id': Parameter(int, "Slice identifier"),
        'name': Parameter(str, "Slice name"),
        'node_id': Node.fields['node_id'],
        'nodegroup_id': NodeGroup.fields['nodegroup_id'],
        'tag_type_id': TagType.fields['tag_type_id'],
        'tagname': TagType.fields['tagname'],
        'description': TagType.fields['description'],
        'category': TagType.fields['category'],
        'value': Parameter(str, "Slice attribute value"),
        }
    #wangyang
    VSLIVER_FILE = "/var/lib/myplc/vsliver.pickle"
    VIP_FILE = "/var/lib/myplc/vip.pickle"
    VMAC_FILE = "/var/lib/myplc/vmac.pickle"
    VLANID_FILE = "/var/lib/myplc/vlanid.pickle"
    PEARL_DPID = 1
    NODE_ID = 32

    PEARL_API_URL = "http://192.168.1.43:8080?wsdl"
    PEARL_DEFAULT_CONFIG = "/etc/planetlab/pearl_default_config.xml"
    

    #wangyang
    #@staticmethod 
    def GetPearlVip(self,slice_id,node_id):
        vip = self.getvip()
        vsliver = self.loadvsliver()
        flag = 0
        for vslivers in vsliver:
            if vslivers['slice_id'] == slice_id and vslivers['node_id'] == node_id and vslivers['vip'] != vip:
                self.updatevip(vslivers['vip'])
                vslivers['vip']=vip
                flag = 1
                break
        if flag == 0:    
            vslivers = self.initevsliver(slice_id,node_id,vip,'none','none')
            vsliver.append(vslivers)
        self.savevsliver(vsliver)  
        return vip
    #@staticmethod
    def GetPearlVmac(self,slice_id,node_id):
        vmac = self.getvmac()
        vsliver = self.loadvsliver()
        flag = 0
        for vslivers in vsliver:
            if vslivers['slice_id'] == slice_id and vslivers['node_id'] == node_id and vslivers['vmac'] != vmac:
                self.updatevmac(vslivers['vmac'])
                vslivers['vmac']=vmac
                flag = 1
                break
        if flag == 0:    
            vslivers = self.initevsliver(slice_id,node_id,'none',vmac,'none')
            vsliver.append(vslivers)
        self.savevsliver(vsliver)  
        return vmac
    #@staticmethod
    def GetPearlVlanid(self,slice_id):
        
        vlanid = self.getvlanid(slice_id)
        vsliver = self.loadvsliver()
        """ 
        flag = 0
        for vslivers in vsliver:
            if vslivers['slice_id'] == slice_id:
                #self.updatevlanid(vslivers['vlanid'],vslivers['slice_id'],vslivers['node_id'])
                vslivers['vlanid']=vlanid
                if vslivers['node_id'] == 'none':
                    flag = 1
        
        if flag == 0:    
            vslivers = self.initevsliver(slice_id,'none','none','none',vlanid)
            vsliver.append(vslivers)
            self.savevsliver(vsliver)  
        """
        return vlanid
    #@staticmethod
    def FreePearlTag(self,slice_id,node_id):
        vslivers = self.loadvsliver()
        for vsliver in vslivers[:]:
            if vsliver['slice_id'] == slice_id and vsliver['node_id'] == node_id:
                self.updatevip(vsliver['vip'])
                self.updatevmac(vsliver['vmac'])
                #self.updatevlanid(vsliver['slice_id'],vsliver['node_id'],vsliver['vlanid'])
                break
        vslivers.remove(vsliver)
        self.savevsliver(vslivers)
        return 0
    #@staticmethod
    def FreeVlanid(self,slice_id):
        vslivers = self.loadvsliver()
        for vsliver in vslivers[:]:
            if vsliver['slice_id'] == slice_id:
                if vsliver['node_id'] == 'none':
                    self.updatevlanid(vsliver['vlanid'])
                    vslivers.remove(vsliver)
                    continue
                vsliver['vlanid'] = 'none'
        self.savevsliver(vslivers)
        return 0
    def initevsliver(self,slice_id,node_id,vip,vmac,vlanid):
        if vlanid == 'none':
            #vlanid = self.GetPearlVlanid(self,slice_id)
            vlanid =vlanid = self.getvlanid(slice_id,'init')
        sliver = {}
        sliver['slice_id']=slice_id
        sliver['node_id']=node_id
        sliver['vip']=vip
        sliver['vmac']=vmac
        sliver['vlanid']=vlanid
        return sliver



    def getvip(self):
        vip = self.loadvip()
        for vips in vip:
             if vips['status'] == 'available':
             	vips['status'] = 'used'
             	#router.remove(routerid)
             	#router.append(routerid)
             	self.savevip(vip)
             	return vips['ip']

        return 0       
    def getvmac(self):
        vmac = self.loadvmac()
        
        for vmacs in vmac:
             if vmacs['status'] == 'available':
             	vmacs['status'] = 'used'
             	#router.remove(routerid)
             	#router.append(routerid)
             	self.savevmac(vmac)
             	return vmacs['mac']
        return 0       

    def getvlanid(self,slice_id,flag = 'none'):
        
        vsliver = self.loadvsliver()
        for vslivers in vsliver:
            if vslivers['slice_id'] == slice_id and vslivers['vlanid'] != 'none':
                return vslivers['vlanid']
        if flag == 'init':
            return "none"
        
        vlanids = self.loadvlanid()
        
        for vlanid in vlanids:
             if vlanid['status'] == 'available':
             	vlanid['status'] = 'used'
             	self.savevlanid(vlanids)
             	return vlanid['vlanid']
        
        return 0       
    def savevsliver(self,vsliver):
        #f = open(self.VSLIVER_FILE, "w")
        logger.log ("myplc: saving successfully vsliver in %s" % self.VIP_FILE)
        #pickle.dump(vsliver, f)
        #f.close()
        logger.log_router(vsliver,"vsliver.txt","This is writed to db")

    def savevip (self, vip):
        f = open(self.VIP_FILE, "w")
        logger.log ("myplc: saving successfully router id in %s" % self.VIP_FILE)
        pickle.dump(vip, f)
        f.close()
        logger.log_router(vip,"vip.txt","This is writed to db")
    def savevmac (self, vmac):
        f = open(self.VMAC_FILE, "w")
        logger.log ("myplc: saving successfully router mac in %s" % self.VMAC_FILE)
        pickle.dump(vmac, f)
        f.close()
        logger.log_router(vmac,"vmac.txt","This is writed to db")
   
    def savevlanid (self, vid):
        #fd = file(self.VLANID_FILE, 'w')
        #self.f = open('vlanid.txt', 'w+')
        #pickle.dump(vip,file("/var/myplc/vlanid.pickle",'wb'))
        #f = os.open("/var/myplc/vlanid.pickle", os.O_WRONLY, 0600)
        logger.log ("myplc: saving successfully vlan id in %s" % self.VLANID_FILE)
        #pickle.dump(vid, f)
        #f.close()
        logger.log_router(vid,"vlanid.txt","This is writed to db")
    def loadvsliver(self):
        try:
            f = open(self.VSLIVER_FILE, "r+")
            logger.log("myplc: restoring latest known vsliver from %s" % self.VSLIVER_FILE)
            vsliver = pickle.load(f)
            f.close()
            return vsliver
        except:
            logger.log("Could not restore vsliver from %s" % self.VSLIVER_FILE)
            vsliver=[]
            vslivers = {}
            vslivers['slice_id'] = None 
            vslivers['node_id'] = None
            vslivers['vip'] = None
            vslivers['vmac'] = None
            vslivers['vlanid'] = None 
            vsliver.append(vslivers)
            print "vsliver is %s"%vslivers['slice_id']
            return vsliver

    def loadvip(self):
        try:
            f = open(self.VIP_FILE, "r+")
            logger.log("myplc: restoring latest known vip from %s" % self.VIP_FILE)
            vips = pickle.load(f)
            f.close()
            return vips
        except:
            logger.log("Could not restore vip from %s" % self.VIP_FILE)
            vips = []    
            
            for i in range(128,254):
                vip = {}
                vip['ip'] = '192.168.122.'+str(i)
                vip['status'] = 'available'
                vips.append(vip)                
            return vips

    def loadvmac(self):
        try:
            f = open(self.VMAC_FILE, "r+")
            logger.log("myplc: restoring latest known vip from %s" % self.VMAC_FILE)
            vmacs = pickle.load(f)
            f.close()
            return vmacs
        except:
            logger.log("Could not restore vip from %s" % self.VMAC_FILE)
            vmacs = []    
            
            for i in range(1,15):
                vmac = {}
                vmac['mac'] = '24:3f:d0:39:52:0'+(str(hex(i)))[2:]
                vmac['status'] = 'available'
                vmacs.append(vmac)
            for i in range(16,128):
                vmac = {}
                vmac['mac'] = '24:3f:d0:39:52:'+(str(hex(i)))[2:]
                vmac['status'] = 'available'
                vmacs.append(vmac)
            return vmacs
    
    def loadvlanid(self):
        try:
            f = open(self.VLANID_FILE, "r+")
            logger.log("myplc: restoring latest known vlanid from %s" % self.VLANID_FILE)
            vids = pickle.load(f)
            f.close()
            return vids
        except:
            logger.log("Could not restore vip from %s" % self.VLANID_FILE)
            vids = []    
            
            for i in range(2000, 4095):
                vid = {}
                vid['vlanid'] = str(i)
                vid['status'] = 'available'
                vids.append(vid)
            return vids
    """ 
    def syncvlanid(self,slice_id,vid):
        vslivers = self.loadvsliver()
        for vsliver in vslivers:
            if vsliver['slice_id'] == slice_id:
                vsliver['vlanid'] == vid
        self.savevsliver(vslivers)
    """
    def updatevlanid(self,vid):
        vlanid = self.loadvlanid()
        for vlanids in vlanid:
            if vlanids['vlanid'] == vid:
                vlanids['status'] = 'available'
                self.savevlanid(vlanid)
                return 0
    def updatevip(self,ip):
        vip = self.loadvip()
        for vips in vip:
            if vips['ip'] == ip:
                vips['status'] = 'available'
                self.savevip(vip)
    def updatevmac(self,mac):
        vmac = self.loadvmac()
        for vmacs in vmac:
            if vmacs['mac'] == mac:
                 vmacs['status'] = 'available'
                 self.savevmac(vmac)

class SliceTags(Table):
    """
    Representation of row(s) from the slice_tag table in the
    database.
    """

    def __init__(self, api, slice_tag_filter = None, columns = None):
        Table.__init__(self, api, SliceTag, columns)

        sql = "SELECT %s FROM view_slice_tags WHERE True" % \
              ", ".join(self.columns)

        if slice_tag_filter is not None:
            if isinstance(slice_tag_filter, (list, tuple, set, int, long)):
                slice_tag_filter = Filter(SliceTag.fields, {'slice_tag_id': slice_tag_filter})
            elif isinstance(slice_tag_filter, dict):
                slice_tag_filter = Filter(SliceTag.fields, slice_tag_filter)
            else:
                raise PLCInvalidArgument, "Wrong slice tag filter %r"%slice_tag_filter
            sql += " AND (%s) %s" % slice_tag_filter.sql(api)

        self.selectall(sql)
