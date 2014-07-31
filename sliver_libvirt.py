"""LibVirt slivers"""

import sys
import os, os.path
import subprocess
import pprint

import libvirt

from account import Account
import logger
import plnode.bwlimit as bwlimit
import cgroups

STATES = {
    libvirt.VIR_DOMAIN_NOSTATE:  'no state',
    libvirt.VIR_DOMAIN_RUNNING:  'running',
    libvirt.VIR_DOMAIN_BLOCKED:  'blocked on resource',
    libvirt.VIR_DOMAIN_PAUSED:   'paused by user',
    libvirt.VIR_DOMAIN_SHUTDOWN: 'being shut down',
    libvirt.VIR_DOMAIN_SHUTOFF:  'shut off',
    libvirt.VIR_DOMAIN_CRASHED:  'crashed',
}

connections = dict()

# Common Libvirt code

class Sliver_Libvirt(Account):

    # Helper methods

    @staticmethod
    def getConnection(sliver_type):
        # TODO: error checking
        # vtype is of the form sliver.[LXC/QEMU] we need to lower case to lxc/qemu
        vtype = sliver_type.split('.')[1].lower()
        uri = vtype + '://'
        return connections.setdefault(uri, libvirt.open(uri))

    @staticmethod
    def debuginfo(dom):
        ''' Helper method to get a "nice" output of the info struct for debug'''
        [state, maxmem, mem, ncpu, cputime] = dom.info()
        return '%s is %s, maxmem = %s, mem = %s, ncpu = %s, cputime = %s' % (dom.name(), STATES.get(state, state), maxmem, mem, ncpu, cputime)

    def __init__(self, rec):
        self.name = rec['name']
        logger.verbose ('sliver_libvirt: %s init'%(self.name))

        # Assume the directory with the image and config files
        # are in place

        self.keys = ''
        self.rspec = {}
        self.slice_id = rec['slice_id']
        self.enabled = True
        self.conn = Sliver_Libvirt.getConnection(rec['type'])
        self.xid = bwlimit.get_xid(self.name)

        dom = None
        try:
            dom = self.conn.lookupByName(self.name)
        except:
            logger.log('sliver_libvirt: Domain %s does not exist. ' \
                       'Will try to create it again.' % (self.name))
            self.__class__.create(rec['name'], rec)
            dom = self.conn.lookupByName(self.name)
        self.dom = dom

    def start(self, delay=0):
        ''' Just start the sliver '''
        logger.verbose('sliver_libvirt: %s start'%(self.name))

        # Check if it's running to avoid throwing an exception if the
        # domain was already running, create actually means start
        if not self.is_running():
            self.dom.create()
        else:
            logger.verbose('sliver_libvirt: sliver %s already started'%(self.name))

        # After the VM is started... we can play with the virtual interface
        # Create the ebtables rule to mark the packets going out from the virtual
        # interface to the actual device so the filter canmatch against the mark
        bwlimit.ebtables("-A INPUT -i veth%d -j mark --set-mark %d" % \
            (self.xid, self.xid))

    def stop(self):
        logger.verbose('sliver_libvirt: %s stop'%(self.name))

        # Remove the ebtables rule before stopping 
        bwlimit.ebtables("-D INPUT -i veth%d -j mark --set-mark %d" % \
            (self.xid, self.xid))

        try:
            self.dom.destroy()
        except:
            logger.verbose('sliver_libvirt: Domain %s not running ' \
                           'UNEXPECTED: %s'%(self.name, sys.exc_info()[1]))
            print 'sliver_libvirt: Domain %s not running ' \
                  'UNEXPECTED: %s'%(self.name, sys.exc_info()[1])

    def is_running(self):
        ''' Return True if the domain is running '''
        logger.verbose('sliver_libvirt: %s is_running'%self.name)
        try:
            [state, _, _, _, _] = self.dom.info()
            if state == libvirt.VIR_DOMAIN_RUNNING:
                logger.verbose('sliver_libvirt: %s is RUNNING'%self.name)
                return True
            else:
                info = debuginfo(self.dom)
                logger.verbose('sliver_libvirt: %s is ' \
                               'NOT RUNNING...\n%s'%(self.name, info))
                return False
        except:
            logger.verbose('sliver_libvirt: UNEXPECTED ERROR in ' \
                           '%s: %s'%(self.name, sys.exc_info()[1]))
            print 'sliver_libvirt: UNEXPECTED ERROR in ' \
                  '%s: %s'%(self.name, sys.exc_info()[1])
            return False

    def configure(self, rec):

        #sliver.[LXC/QEMU] tolower case
        #sliver_type = rec['type'].split('.')[1].lower() 

        #BASE_DIR = '/cgroup/libvirt/%s/%s/'%(sliver_type, self.name)

        # Disk allocation
        # No way through cgroups... figure out how to do that with user/dir quotas.
        # There is no way to do quota per directory. Chown-ing would create
        # problems as username namespaces are not yet implemented (and thus, host
        # and containers share the same name ids

        # Btrfs support quota per volumes

        if rec.has_key("rspec") and rec["rspec"].has_key("tags"):
            if cgroups.get_cgroup_path(self.name) == None:
                # If configure is called before start, then the cgroups won't exist
                # yet. NM will eventually re-run configure on the next iteration.
                # TODO: Add a post-start configure, and move this stuff there
                logger.log("Configure: postponing tag check on %s as cgroups are not yet populated" % self.name)
            else:
                tags = rec["rspec"]["tags"]
                # It will depend on the FS selection
                if tags.has_key('disk_max'):
                    disk_max = tags['disk_max']
                    if disk_max == 0:
                        # unlimited
                        pass
                    else:
                        # limit to certain number
                        pass

                # Memory allocation
                if tags.has_key('memlock_hard'):
                    mem = str(int(tags['memlock_hard']) * 1024) # hard limit in bytes
                    cgroups.write(self.name, 'memory.limit_in_bytes', mem, subsystem="memory")
                if tags.has_key('memlock_soft'):
                    mem = str(int(tags['memlock_soft']) * 1024) # soft limit in bytes
                    cgroups.write(self.name, 'memory.soft_limit_in_bytes', mem, subsystem="memory")

                # CPU allocation
                # Only cpu_shares until figure out how to provide limits and guarantees
                # (RT_SCHED?)
                if tags.has_key('cpu_share'):
                    cpu_share = tags['cpu_share']
                    cgroups.write(self.name, 'cpu.shares', cpu_share)

        # Call the upper configure method (ssh keys...)
        Account.configure(self, rec)

    # A placeholder until we get true VirtualInterface objects
    @staticmethod
    def get_interfaces_xml(rec):
        xml = """
    <interface type='network'>
      <source network='default'/>
    </interface>
"""
        try:
            tags = rec['rspec']['tags']
            if 'interface' in tags:
                interfaces = eval(tags['interface'])
                if not isinstance(interfaces, (list, tuple)):
                    # if interface is not a list, then make it into a singleton list
                    interfaces = [interfaces]
                tag_xml = ""
                for interface in interfaces:
                    if 'vlan' in interface:
                        vlanxml = "<vlan><tag id='%s'/></vlan>" % interface['vlan']
                    else:
                        vlanxml = ""
                    if 'bridge' in interface:
                        tag_xml = tag_xml + """
        <interface type='bridge'>
          <source bridge='%s'/>
          %s
          <virtualport type='openvswitch'/>
        </interface>
    """ % (interface['bridge'], vlanxml)
                    else:
                        tag_xml = tag_xml + """
        <interface type='network'>
          <source network='default'/>
        </interface>
    """
                xml = tag_xml
                logger.log('sliver_libvirty.py: interface XML is: %s' % xml)

        except:
            logger.log('sliver_libvirt.py: ERROR parsing "interface" tag for slice %s' % rec['name'])
            logger.log('sliver_libvirt.py: tag value: %s' % tags['interface'])

        return xml
