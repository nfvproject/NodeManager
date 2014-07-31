"""
Update /etc/hosts in slivers to contain the contents of the sliver_hostmap tag.
"""

import logger
import os
import curlwrapper
import re
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

PREFIX = "# ----- This section added by nodemanager hostmap module. Do not edit. -----"
SUFFIX = "# ----- End -----"

def GetSlivers(data, config=None, plc=None):

    if 'slivers' not in data:
        logger.log_missing_data("hostmap.GetSlivers",'slivers')
        return

    if 'hostname' not in data:
        logger.log_missing_data("hostmap.GetSlivers", 'hostname')

    hostname = data['hostname']

    for sliver in data['slivers']:
        slicename = sliver['name']
        for tag in sliver['attributes']:
            if tag['tagname'] == 'slice_hostmap':
                fn = "/vservers/%s/etc/hosts" % slicename
                if not os.path.exists(fn):
                    continue

                contents = file(fn,"r").read()

                hostmap = []
                for index, entry in enumerate(tag["value"].split("\n")):
                    parts = entry.split(" ")
                    if len(parts)==2:
                       line = "%s pvt.%s private%d" % (parts[0], parts[1], index)

                       if (index==0):
                           line = line + " headnode"

                       if parts[1] == hostname:
                           line = line + " pvt.self"

                       hostmap.append(line)

                hostmap = "\n".join(hostmap)
                hostmap = PREFIX + "\n" + hostmap + "\n" + SUFFIX + "\n"

                if (hostmap in contents):
                    # it's already there
                    continue

                # remove anything between PREFIX and SUFFIX from contents

                pattern = PREFIX + ".*" + SUFFIX + "\n"
                regex = re.compile(pattern, re.DOTALL)
                if regex.search(contents) != None:
                    contents = regex.sub(hostmap, contents)
                else:
                    contents = contents + hostmap

                try:
                    file(fn, "w").write(contents)
                except:
                    logger.log_exc("hostmap (%s): failed to write %s" % (slicename, fn))


