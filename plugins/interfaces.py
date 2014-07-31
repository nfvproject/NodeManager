"""
Configure interfaces inside a container by pulling down files via URL.
"""

import logger
import os
import curlwrapper
import xmlrpclib
try:
    from hashlib import sha1 as sha
except ImportError:
    from sha import sha
import subprocess

def checksum(path):
    try:
        f = open(path)
        try: return sha(f.read()).digest()
        finally: f.close()
    except IOError: 
        return None

def start():
    logger.log("interfaces: plugin starting up...")

def GetSlivers(data, config=None, plc=None):

    if 'slivers' not in data:
        logger.log_missing_data("interfaces.GetSlivers",'slivers')
        return

    for sliver in data['slivers']:
        slicename = sliver['name']
        for tag in sliver['attributes']:
            if tag['tagname'] == 'interface':
                interfaces = eval(tag['value'])

                if not isinstance(interfaces, (list,tuple)):
                    # if interface is not a list, then make it into a singleton list
                    interfaces = [interfaces]

                for mydict in interfaces:
                    contents=""
                    # First look for filename/url combination for custom config files
                    if 'filename' in mydict and 'url' in mydict:
                        dest = "/vservers/%s/%s" % (slicename, mydict['filename'])
                        url = mydict['url']
                        try:
                            contents = curlwrapper.retrieve(url)
                        except xmlrpclib.ProtocolError,e:
                            logger.log('interfaces (%s): failed to retrieve %s' % (slicename, url))
                            continue
                    else:
                        # Otherwise generate /etc/sysconfig/network-scripts/ifcfg-<device>
                        try:
                            dest = "/vservers/%s/etc/sysconfig/network-scripts/ifcfg-%s" % (slicename, mydict['DEVICE'])
                        except:
                            logger.log('interfaces (%s): no DEVICE specified' % slicename)
                            continue

                        for key, value in mydict.items():
                            if key in ['bridge', 'vlan']:
                                continue
                            contents += '%s="%s"\n' % (key, value)

                    if sha(contents).digest() == checksum(dest):
                        logger.log('interfaces (%s): no changes to %s' % (slicename, dest))
                        continue

                    logger.log('interfaces (%s): installing file %s' % (slicename, dest))
                    try:
                        os.makedirs(os.path.dirname(dest))
                    except OSError:
                        pass

                    try:
                        f = open (dest, "w")
                        f.write(contents)
                        f.close()
                    except:
                        logger.log('interfaces (%s): error writing file %s' % (slicename, dest))
                        continue

                    try:
                        subprocess.check_call(['/usr/sbin/lxcsu', slicename, '/sbin/service',
                                               'network', 'restart'])
                    except:
                        logger.log('interfaces (%s): error restarting network service' % slicename)
                    
